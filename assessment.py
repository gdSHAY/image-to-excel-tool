"""Local auxiliary assessment. Never replace the cloud workbook's text."""
import threading
import re
import numpy as np
import cv2
from PIL import Image
import imaging

_engine = None
_lock = threading.Lock()


def normalize(text):
    return re.sub(r'\s+', '', text or '')


def attach_candidates(cells, candidates):
    result = []
    for c in cells:
        item = dict(c)
        candidate = candidates.get(c['id'])
        item.update(candidate_text=candidate['text'] if candidate else None,
                    candidate_score=candidate['score'] if candidate else None,
                    assessment_source='RapidOCR / PP-OCRv6 / CPU')
        result.append(item)
    return result


def assess(path, cells):
    global _engine
    from rapidocr import RapidOCR
    from rapidocr.ch_ppocr_rec import TextRecInput
    with _lock:
        if _engine is None:
            _engine = RapidOCR(params={'Global.text_score': 0.0,
                'Global.log_level': 'warning', 'EngineConfig.onnxruntime.intra_op_num_threads': 4})
        detected = _engine(path / 'processed.png', use_det=True, use_cls=True, use_rec=True)
        lines = [] if detected.boxes is None else [dict(polygon=b.reshape(-1).tolist(), text=t, score=float(s))
            for b, t, s in zip(detected.boxes, detected.txts, detected.scores)]
        located, warnings = imaging.locate_cloud_cells(path / 'processed.png', cells, lines)
        # Keep explicitly confirmed regions, even during a requested reassessment.
        located = [dict(c, polygon=old['polygon']) if old['confirmed'] and old['polygon'] else c
                   for c, old in zip(located, cells)]
        pixels = np.array(Image.open(path / 'processed.png').convert('RGB'))[:, :, ::-1].copy()
        owners = {c['id']: [] for c in located}
        unassigned = []
        for line in lines:
            box = np.array(line['polygon'], dtype=np.float32).reshape(4, 2)
            area = abs(cv2.contourArea(box))
            overlaps = []
            for c in located:
                if len(c['polygon']) != 8: continue
                poly = np.array(c['polygon'], dtype=np.float32).reshape(4, 2)
                intersection, _ = cv2.intersectConvexConvex(box, poly)
                if area and intersection / area >= .65:
                    overlaps.append((intersection / area, c['id']))
            overlaps.sort(reverse=True)
            if overlaps and (len(overlaps) == 1 or overlaps[0][0] - overlaps[1][0] > .2):
                owners[overlaps[0][1]].append(line)
            else:
                unassigned.append(line)
        crops, ids, candidates = [], [], {}
        for c in located:
            if len(c['polygon']) != 8 or (not c['text'].strip() and not owners[c['id']]): continue
            p = np.array(c['polygon'], dtype=np.float32).reshape(4, 2)
            w = max(8, round(max(np.linalg.norm(p[1]-p[0]), np.linalg.norm(p[2]-p[3]))))
            h = max(8, round(max(np.linalg.norm(p[3]-p[0]), np.linalg.norm(p[2]-p[1]))))
            matrix = cv2.getPerspectiveTransform(p, np.float32([[0,0],[w-1,0],[w-1,h-1],[0,h-1]]))
            crop = cv2.warpPerspective(pixels, matrix, (w,h), borderValue=(255,255,255))
            inset = min(3, (min(w,h)-4)//2)
            crop = crop[inset:h-inset, inset:w-inset]
            crops.append(crop); ids.append(c['id'])
        if crops:
            output = _engine.text_rec(TextRecInput(img=crops))
            for cid, text, score in zip(ids, output.txts, output.scores):
                if text.strip(): candidates[cid] = dict(text=text, score=float(score))
        matrix, evidence = imaging.register_original(path / 'original.png', path / 'processed.png')
        if matrix is not None:
            located=imaging.original_outlines(path / 'original.png',path / 'processed.png',located,matrix)
            warnings.append('原图框已按图像配准与局部变形映射；折痕、曲面和无特征区仍可能偏移，须核对局部图。')
        warnings.append('复核分数来自本地 RapidOCR/PP-OCRv6 候选文字，不是扫描全能王分数或正确率。正文未自动替换；两次识别不一致须看图核对。')
        if matrix is None: warnings.append('原图配准未通过，原图不画猜测框；请在处理图校对。')
        return attach_candidates(located, candidates), warnings, matrix, dict(registration=evidence,
            lines=lines, unassigned=unassigned, assessed_cells=len(candidates))
