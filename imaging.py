"""Conservative local geometry fallback. Cloud enhancement is in providers.py."""
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageOps


def preprocess(source: Path, dest: Path, geometry: bool, enhancement: str):
    with Image.open(source) as opened:
        image = ImageOps.exif_transpose(opened).convert('RGB')
        image.save(source.parent / 'original.png')
    pixels = np.array(image)
    matrix = np.eye(3)
    warnings = []
    if geometry:
        scale = min(1, 1400 / max(image.size))
        small = cv2.resize(pixels, None, fx=scale, fy=scale)
        gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
        edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 50, 150)
        edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        quad = None
        for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:10]:
            approx = cv2.approxPolyDP(contour, .02 * cv2.arcLength(contour, True), True)
            if len(approx) == 4 and cv2.isContourConvex(approx) and cv2.contourArea(approx) > .45 * small.shape[0] * small.shape[1]:
                quad = approx.reshape(4, 2).astype(np.float32) / scale
                break
        if quad is not None:
            # Angular ordering avoids duplicated corners in diamond-shaped pages.
            center = quad.mean(axis=0)
            quad = quad[np.argsort(np.arctan2(quad[:, 1]-center[1], quad[:, 0]-center[0]))]
            quad = np.roll(quad, -np.argmin(quad.sum(axis=1)), axis=0)
            w = round(max(np.linalg.norm(quad[1]-quad[0]), np.linalg.norm(quad[2]-quad[3])))
            h = round(max(np.linalg.norm(quad[3]-quad[0]), np.linalg.norm(quad[2]-quad[1])))
            if min(w, h) >= 20:
                matrix = cv2.getPerspectiveTransform(quad, np.float32([[0, 0], [w-1, 0], [w-1, h-1], [0, h-1]]))
                # The detected contour may be the TABLE border rather than the paper.
                # Transform the whole original canvas so outside notes are never cropped.
                corners = np.float32([[[0,0],[image.width-1,0],[image.width-1,image.height-1],[0,image.height-1]]])
                transformed = cv2.perspectiveTransform(corners,matrix)[0]
                lower = np.floor(transformed.min(axis=0))
                upper = np.ceil(transformed.max(axis=0))
                out_w,out_h = map(int,upper-lower+1)
                if min(out_w,out_h)>0 and max(out_w,out_h)<=10000 and out_w*out_h<=40_000_000:
                    translation = np.array([[1,0,-lower[0]],[0,1,-lower[1]],[0,0,1]],dtype=float)
                    matrix = translation @ matrix
                    pixels = cv2.warpPerspective(pixels, matrix, (out_w,out_h), borderValue=(255, 255, 255))
                    warnings.append('自动拉正保留完整画面，避免裁掉表格外备注；背景中其他纸张可能仍可见。')
                else:
                    matrix = np.eye(3)
                    warnings.append('透视变换范围异常，保留原图；请手选四角。')
        else:
            warnings.append('未可靠检测到纸张四角，保留完整图片。可在预览中手动选四角重新拉正。')
        warnings.append('本地采用 OpenCV 平面透视回退；不支持曲面展开或自动文字方向模型。')
    if enhancement == 'ocr':
        lab = cv2.cvtColor(pixels, cv2.COLOR_RGB2LAB)
        lab[:, :, 0] = cv2.createCLAHE(clipLimit=1.3, tileGridSize=(8, 8)).apply(lab[:, :, 0])
        pixels = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)
    elif enhancement == 'bw':
        gray = cv2.cvtColor(pixels, cv2.COLOR_RGB2GRAY)
        pixels = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15)
    Image.fromarray(pixels).save(dest)
    return matrix.tolist(), warnings


def manual_warp(source, dest, points):
    pixels = np.array(Image.open(source).convert('RGB'))
    quad = np.array(points, dtype=np.float32)
    if quad.shape != (4, 2) or not np.isfinite(quad).all():
        raise ValueError('必须提供左上、右上、右下、左下四角')
    if (quad < 0).any() or (quad[:, 0] > pixels.shape[1]).any() or (quad[:, 1] > pixels.shape[0]).any():
        raise ValueError('角点必须在图片范围内')
    if not cv2.isContourConvex(quad.astype(np.int32)) or cv2.contourArea(quad) < 400:
        raise ValueError('四角须组成不相交的有效四边形')
    w = round(max(np.linalg.norm(quad[1]-quad[0]), np.linalg.norm(quad[2]-quad[3])))
    h = round(max(np.linalg.norm(quad[3]-quad[0]), np.linalg.norm(quad[2]-quad[1])))
    matrix = cv2.getPerspectiveTransform(quad, np.float32([[0,0], [w-1,0], [w-1,h-1], [0,h-1]]))
    Image.fromarray(cv2.warpPerspective(pixels, matrix, (w,h))).save(dest)
    return matrix.tolist()


def locate_cloud_cells(image_path, cells, ocr_lines=None):
    """Candidate geometry only: cloud remains the source of logical structure/text.

    Bind only when detected line counts EXACTLY match this workbook's structure.
    A missing/extra line causes fallback, never guessed row/column boundaries.
    """
    if not cells:
        return cells, []
    rows=max(c['row']+c['rowspan']-1 for c in cells)
    cols=max(c['col']+c['colspan']-1 for c in cells)
    gray=np.array(Image.open(image_path).convert('L'))
    height,width=gray.shape
    binary=cv2.adaptiveThreshold(gray,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C,cv2.THRESH_BINARY_INV,31,12)
    horizontal=cv2.morphologyEx(binary,cv2.MORPH_OPEN,np.ones((1,max(20,width//30)),np.uint8))
    horizontal=cv2.morphologyEx(horizontal,cv2.MORPH_CLOSE,np.ones((1,max(10,width//8)),np.uint8))
    vertical=cv2.morphologyEx(binary,cv2.MORPH_OPEN,np.ones((max(20,height//35),1),np.uint8))
    hc,_=cv2.findContours(horizontal,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    vc,_=cv2.findContours(vertical,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    hboxes=sorted([cv2.boundingRect(c) for c in hc if cv2.boundingRect(c)[2]>.65*width],key=lambda b:b[1])
    vboxes=sorted([cv2.boundingRect(c) for c in vc if cv2.boundingRect(c)[3]>.30*height],key=lambda b:b[0])
    groups=[]
    for box in vboxes:
        if groups and abs(box[0]-groups[-1][0][0])<max(5,width*.008):
            groups[-1].append(box)
        else:
            groups.append([box])
    outside = {}
    # A workbook can include real text BELOW the table as its last logical row.
    # Require independent OCR position evidence before excluding that row from grid counts.
    if hboxes and len(hboxes)==rows and ocr_lines:
        from difflib import SequenceMatcher
        tail=[c for c in cells if c['row']==rows]
        if len(tail)==1 and tail[0]['col']==1 and tail[0]['colspan']==cols and tail[0]['rowspan']==1:
            for line in ocr_lines:
                polygon=np.array(line['polygon'],dtype=float).reshape(4,2)
                if polygon[:,1].mean()>hboxes[-1][1]+hboxes[-1][3] and SequenceMatcher(None,tail[0]['text'].strip(),line['text'].strip()).ratio()>=.65:
                    outside[tail[0]['id']]=line['polygon']
                    rows-=1
                    break
    def fit(mask,boxes,vertical=False):
        xx,yy=[],[]
        for x,y,w,h in boxes:
            cy,cx=np.nonzero(mask[y:y+h,x:x+w])
            xx.extend((cx+x).tolist());yy.extend((cy+y).tolist())
        return np.polyfit(yy,xx,1) if vertical else np.polyfit(xx,yy,1)
    if len(hboxes)==rows+1 and len(groups)==cols+1:
        hlines=[fit(horizontal,[box]) for box in hboxes]
        vlines=[fit(vertical,group,True) for group in groups]
    else:
        hlines,vlines=segment_grid(binary)
        if len(hlines)!=rows+1 or len(vlines)!=cols+1:
            return cells,['单元格定位：图片线数与云端行列不一致，未生成猜测框。请在校对中手动框选绑定。']
    def intersection(r,col):
        hm,hb=hlines[r];vm,vb=vlines[col]
        den=1-hm*vm
        if abs(den)<.01:raise ValueError('表格边线交点不可靠')
        x=(vm*hb+vb)/den;y=hm*x+hb
        if not (0<=x<width and 0<=y<height):raise ValueError('表格交点超出图片')
        return [float(x),float(y)]
    updated=[]
    try:
        for c in cells:
            if c['id'] in outside:
                updated.append(dict(c,polygon=outside[c['id']],kind='outside'))
                continue
            top,left=c['row']-1,c['col']-1;bottom=top+c['rowspan'];right=left+c['colspan']
            polygon=sum([intersection(top,left),intersection(top,right),intersection(bottom,right),intersection(bottom,left)],[])
            if not cv2.isContourConvex(np.array(polygon,dtype=np.float32).reshape(4,2)):
                raise ValueError('候选框不可靠')
            updated.append(dict(c,polygon=polygon))
    except (ValueError,cv2.error):
        return cells,['本地表格线定位不可靠，请在校对中手动框选绑定。']
    return updated,['格子位置由本地表格线匹配生成候选，非扫描全能王原生坐标；行列线数一致仍需逐格看图确认。']


def segment_grid(binary):
    """Aggregate observed short border segments; never interpolate missing borders."""
    height,width=binary.shape
    minimum=max(20,round(min(height,width)*.052))
    lines=cv2.HoughLinesP(binary,1,np.pi/720,max(20,minimum//2),
                         minLineLength=minimum,maxLineGap=max(5,minimum//5))
    if lines is None:return [],[]
    result=[]
    for vertical in (False,True):
        span=height if vertical else width
        pivot=span*(.45 if vertical else .55)
        segments=[]
        for x,y,X,Y in lines.reshape(-1,4):
            u,v,U,V=(y,x,Y,X) if vertical else (x,y,X,Y)
            if abs(U-u)<minimum or abs(V-v)>(.12 if vertical else .08)*abs(U-u):continue
            position=(v+V)/2+(V-v)/(U-u)*(pivot-(u+U)/2)
            segments.append((float(position),(float(u),float(v),float(U),float(V))))
        groups=[]
        for position,line in sorted(segments):
            tolerance=max(4,min(height,width)*.012)
            if groups and abs(position-np.median([p[0] for p in groups[-1]]))<tolerance:
                groups[-1].append((position,line))
            else:groups.append([(position,line)])
        fitted=[]
        for group in groups:
            support=np.zeros(span,bool)
            uu,vv=[],[]
            for _,(u,v,U,V) in group:
                support[max(0,int(min(u,U))):min(span,int(max(u,U))+1)]=True
                # Samples weight longer observed segments more heavily.
                t=np.linspace(0,1,max(2,round(abs(U-u)/8)))
                uu.extend(u+(U-u)*t);vv.extend(v+(V-v)*t)
            if support.sum()<.4*span:continue
            fitted.append(np.polyfit(uu,vv,1))
        result.append(fitted)
    return result


def register_original(original,processed):
    """Find a verified original→processed map; reject weak or localized matches."""
    a=np.array(Image.open(original).convert('L'));b=np.array(Image.open(processed).convert('L'))
    detector=cv2.SIFT_create(nfeatures=6000,contrastThreshold=.02)
    ka,da=detector.detectAndCompute(a,None);kb,db=detector.detectAndCompute(b,None)
    if da is None or db is None:return None,{'reason':'图像特征不足'}
    pairs=cv2.BFMatcher(cv2.NORM_L2).knnMatch(da,db,k=2)
    good=[pair[0] for pair in pairs if len(pair)==2 and pair[0].distance<.70*pair[1].distance]
    if len(good)<30:return None,{'reason':'可靠匹配点不足'}
    x=np.float32([ka[g.queryIdx].pt for g in good]);y=np.float32([kb[g.trainIdx].pt for g in good])
    matrix,mask=cv2.findHomography(x,y,cv2.RANSAC,4.0)
    if matrix is None or mask is None:return None,{'reason':'图像配准失败'}
    selected=mask.ravel().astype(bool)
    if selected.sum()<30 or selected.mean()<.5:return None,{'reason':'配准匹配质量不足'}
    mapped=cv2.perspectiveTransform(x[selected,None,:],matrix)[:,0,:]
    error=float(np.median(np.linalg.norm(mapped-y[selected],axis=1)))
    hull=cv2.convexHull(x[selected]);coverage=cv2.contourArea(hull)/(a.shape[0]*a.shape[1])
    evidence=dict(inliers=int(selected.sum()),matches=len(good),median_error_px=error,coverage=float(coverage))
    evidence['inlier_ratio']=float(selected.mean())
    if error>3 or coverage<.12:return None,dict(evidence,reason='特征覆盖或误差未通过')
    return matrix.tolist(),evidence


def original_outlines(original,processed,cells,matrix):
    """Refine the verified global map with forward/backward checked local flow.

    Sample edges to follow bent paper. Unsupported corrections keep the global map.
    All coordinates remain review candidates, not guaranteed pixel-perfect geometry.
    """
    a=np.array(Image.open(original).convert('L'));b=np.array(Image.open(processed).convert('L'))
    matrix=np.array(matrix,dtype=float)
    warped=cv2.warpPerspective(a,matrix,(b.shape[1],b.shape[0]),borderValue=255)
    scale=min(1.,1000/b.shape[1]);size=(round(b.shape[1]*scale),round(b.shape[0]*scale))
    clahe=cv2.createCLAHE(2,(8,8))
    aa=clahe.apply(cv2.resize(warped,size));bb=clahe.apply(cv2.resize(b,size))
    engine=cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
    flow=engine.calc(bb,aa,None);reverse=engine.calc(aa,bb,None)
    updated=[]
    for c in cells:
        item=dict(c,original_polygon=[])
        if len(c['polygon'])==8:
            corners=np.array(c['polygon'],dtype=np.float32).reshape(4,2)
            points=np.array([corners[k]*(1-t)+corners[(k+1)%4]*t for k in range(4)
                             for t in np.linspace(0,1,9,endpoint=False)],dtype=np.float32)
            small=points*scale
            xs=np.clip(np.round(small[:,0]).astype(int),0,size[0]-1)
            ys=np.clip(np.round(small[:,1]).astype(int),0,size[1]-1)
            delta=flow[ys,xs];q=small+delta
            rx=np.clip(np.round(q[:,0]).astype(int),0,size[0]-1)
            ry=np.clip(np.round(q[:,1]).astype(int),0,size[1]-1)
            error=np.linalg.norm(delta+reverse[ry,rx],axis=1)
            valid=(error<2)&(np.linalg.norm(delta,axis=1)<150*scale)
            if valid.sum()>=4:
                # Interpolate rejected flow samples instead of introducing sharp jumps.
                for axis in range(2):
                    delta[:,axis]=np.interp(np.arange(len(points)),np.flatnonzero(valid),delta[valid,axis],period=len(points))
                refined=((small+delta)/scale).astype(np.float32)
            else:
                refined=points
            mapped=cv2.perspectiveTransform(refined[None,:,:],np.linalg.inv(matrix))[0]
            if np.isfinite(mapped).all() and (mapped>=0).all() and (mapped[:,0]<a.shape[1]).all() and (mapped[:,1]<a.shape[0]).all():
                item['original_polygon']=mapped.reshape(-1).tolist()
        updated.append(item)
    return updated
