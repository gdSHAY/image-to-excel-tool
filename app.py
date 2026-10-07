import json
import math
import os
import threading
import uuid
import hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from PIL import Image
import imaging
import assessment
import providers
from tables import validate, export, from_workbook

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data/jobs'
DATA.mkdir(parents=True, exist_ok=True)
# A stopped process must not leave a task permanently looking active.
for saved in DATA.glob('*/job.json'):
    try:
        previous = json.loads(saved.read_text(encoding='utf-8'))
        if previous.get('status') == 'recognizing':
            previous.update(status='failed',error='上次识别被服务退出中断，结果未知。请检查账户记录后手动重试。')
            saved.write_text(json.dumps(previous,ensure_ascii=False),encoding='utf-8')
    except (OSError,json.JSONDecodeError):
        pass  # Preserve damaged task files; do not replace them with default data.
POOL = ThreadPoolExecutor(max_workers=1)
LOCK = threading.RLock()
app = FastAPI(title='ScanTable Studio')


@app.middleware('http')
async def local_only(request: Request, call_next):
    host = request.headers.get('host','').split(':')[0]
    origin = request.headers.get('origin')
    if host not in ('127.0.0.1','localhost','testserver') or (origin and origin not in ('http://127.0.0.1:8788','http://localhost:8788')):
        return JSONResponse({'detail':'仅允许本机访问'},status_code=403)
    return await call_next(request)


@app.exception_handler(ValueError)
async def bad_value(request, exc):
    return JSONResponse({'detail':str(exc)}, status_code=422)


def job_path(jid):
    try:
        if uuid.UUID(jid).hex != jid:
            raise ValueError()
    except ValueError:
        raise HTTPException(404, '任务不存在')
    path = DATA / jid
    if path.resolve().parent != DATA.resolve():
        raise HTTPException(404, '任务不存在')
    if not (path / 'job.json').exists():
        raise HTTPException(404, '任务不存在')
    return path


def read_job(jid):
    return json.loads((job_path(jid) / 'job.json').read_text(encoding='utf-8'))


def write_job(path, job):
    temp = path / 'job.tmp'
    temp.write_text(json.dumps(job, ensure_ascii=False, allow_nan=False),encoding='utf-8')
    temp.replace(path / 'job.json')


def public(job):
    job = dict(job)
    jid = job['id']
    job['original_url'] = f'/api/jobs/{jid}/image/original'
    job['processed_url'] = f'/api/jobs/{jid}/image/processed?v={job.get("revision",0)}'
    return job


def require_idle(job):
    if job['status'] == 'recognizing':
        raise HTTPException(409,'识别中，请等待完成')


@app.get('/api/health')
def health():
    return {'ok':True,'application':'ScanTableStudio','pid':os.getpid(),'cli_installed':providers.CLI.is_file()}


@app.get('/api/jobs')
def history():
    with LOCK:
        return [public(json.loads(p.read_text(encoding='utf-8'))) for p in sorted(DATA.glob('*/job.json'),key=lambda p:p.stat().st_mtime,reverse=True)][:100]


@app.delete('/api/jobs/{jid}')
def delete_history(jid: str):
    with LOCK:
        job = read_job(jid)
        require_idle(job)
        source = job_path(jid)
        trash = DATA.parent / 'deleted-jobs'
        trash.mkdir(exist_ok=True)
        target = trash / jid
        if target.exists():
            raise HTTPException(409, '回收目录已有同名任务')
        source.rename(target)
        return {'id':jid,'deleted':True,'recoverable':True}


@app.post('/api/trash/{jid}/restore')
def restore_history(jid: str):
    with LOCK:
        try:
            if uuid.UUID(jid).hex != jid:
                raise ValueError()
        except ValueError:
            raise HTTPException(404, '已删除任务不存在')
        trash = DATA.parent / 'deleted-jobs'
        source = trash / jid
        if source.resolve().parent != trash.resolve() or not (source / 'job.json').exists():
            raise HTTPException(404, '已删除任务不存在')
        target = DATA / jid
        if target.exists():
            raise HTTPException(409, '历史中已有同名任务')
        source.rename(target)
        return public(read_job(jid))


@app.post('/api/jobs')
async def upload(file: UploadFile = File(...), geometry: bool = Form(True), enhancement: Literal['natural','original','ocr','bw'] = Form('natural')):
    data = await file.read(40_000_001)
    if len(data)>40_000_000:
        raise HTTPException(413,'图片限制40MB')
    from io import BytesIO
    try:
        with Image.open(BytesIO(data)) as im:
            if im.format not in ('JPEG','PNG','BMP','TIFF','WEBP') or min(im.size)<20 or max(im.size)>10000 or im.width*im.height>40_000_000:
                raise ValueError('支持20~10000像素的图片，总像素不超过4000万')
            im.verify()
    except (OSError, Image.DecompressionBombError) as exc:
        raise ValueError('无法读取图片，请使用正常 JPG/PNG 图片') from exc
    jid = uuid.uuid4().hex
    path = DATA / jid
    path.mkdir()
    source = path / 'source.upload'
    source.write_bytes(data)
    matrix,warnings = imaging.preprocess(source,path / 'processed.png',geometry,enhancement)
    job = dict(id=jid,name=Path(file.filename or '图片').name,status='prepared',warnings=warnings,
        cells=[],matrix=matrix,revision=0,error=None,provider=None)
    with LOCK:
        write_job(path,job)
    return public(job)


@app.get('/api/jobs/{jid}')
def get_job(jid: str):
    with LOCK:
        return public(read_job(jid))


@app.get('/api/jobs/{jid}/image/{kind}')
def get_image(jid: str, kind: Literal['original','processed']):
    return FileResponse(job_path(jid) / f'{kind}.png')


class Recognition(BaseModel):
    provider: Literal['camscanner','textin'] = 'camscanner'
    app_id: str = Field(default='',max_length=500)
    secret: str = Field(default='',max_length=500)
    cloud_enhance: bool = False


def work(jid, settings):
    path = job_path(jid)
    try:
        image = path / 'processed.png'
        warnings = []
        cache_path=path / 'pipeline.json'
        cache=json.loads(cache_path.read_text(encoding='utf-8')) if cache_path.exists() else {}
        def digest(file):return hashlib.sha256(file.read_bytes()).hexdigest()
        def cache_save():
            temp=path / 'pipeline.tmp'
            temp.write_text(json.dumps(cache),encoding='utf-8');temp.replace(cache_path)
        def phase(name):
            with LOCK:
                job=read_job(jid);job.update(phase=name)
                job['warnings']=list(dict.fromkeys(job['warnings']+warnings))
                write_job(path,job)
        if settings.cloud_enhance:
            phase('enhance')
            if cache.get('enhanced_sha')!=digest(image):
                enhanced = path / 'enhanced.png'
                providers.cli(['image','enhance',image,'--mode','7','-o',enhanced])
                with Image.open(image) as old, Image.open(enhanced) as new:
                    if old.size != new.size:
                        warnings.append('云端增强改变了尺寸；原图坐标映射失效。请在处理图校对。')
                        with LOCK:
                            job = read_job(jid)
                            job['matrix'] = None
                            write_job(path,job)
                    new.verify()
                enhanced.replace(image)
                cache['enhanced_sha']=digest(image);cache_save()
            warnings.append('已应用扫描全能王超级滤镜；请对照原图核对细笔画、数字和表格交点。')
        phase('table')
        workbook=path / 'cloud.xlsx'
        if settings.provider=='camscanner' and workbook.exists() and cache.get('table_input_sha')==digest(image) and cache.get('workbook_sha')==digest(workbook):
            (cells,parsed_warnings),raw=from_workbook(workbook),None
        else:
            (cells,parsed_warnings),raw = providers.recognize(image,settings.provider,settings.app_id,settings.secret)
            if settings.provider=='camscanner':
                cache.update(table_input_sha=digest(image),workbook_sha=digest(workbook));cache_save()
        if settings.provider == 'camscanner':
            phase('assess')
            try:
                cells, location_warnings, matrix, evidence = assessment.assess(path,cells)
                parsed_warnings.extend(location_warnings)
                (path / 'assessment.json').write_text(json.dumps(evidence,ensure_ascii=False),encoding='utf-8')
                with LOCK:
                    job=read_job(jid)
                    job.update(matrix=matrix,registration=evidence['registration'])
                    write_job(path,job)
            except Exception:
                cells, location_warnings = imaging.locate_cloud_cells(image,cells)
                parsed_warnings.extend(location_warnings+['本地复核失败，分数未知；扫描全能王正文保留，请人工校对。'])
        if raw is not None:
            (path / 'raw.json').write_text(json.dumps(raw,ensure_ascii=False),encoding='utf-8')
        with LOCK:
            job = read_job(jid)
            job.update(cells=cells,status='review',phase=None,failed_stage=None,error=None,provider=settings.provider,revision=job['revision']+1)
            job['warnings']=list(dict.fromkeys(job['warnings']+warnings+parsed_warnings))
            write_job(path,job)
    except Exception as exc:
        # Never include response request headers, secret values, or CLI auth output.
        message = str(exc) if isinstance(exc, ValueError) else '识别/增强失败：网络、超时或返回文件异常。未自动重试，请检查连接和账户。'
        with LOCK:
            job = read_job(jid)
            stage=job.get('phase')
            label={'enhance':'AI 增强','table':'表格识别','assess':'本地复核'}.get(stage,'识别')
            job.update(status='failed',failed_stage=stage,error=f'{label}失败：{message}',revision=job['revision']+1)
            write_job(path,job)


@app.post('/api/jobs/{jid}/recognize')
def recognize(jid: str, body: Recognition):
    with LOCK:
        job = read_job(jid)
        require_idle(job)
        if job['cells']:
            raise HTTPException(409,'已有校对结果。重新识别请重新上传，避免覆盖人工修正。')
        job.update(status='recognizing',error=None,provider=body.provider)
        write_job(job_path(jid),job)
    POOL.submit(work,jid,body)
    return public(job)


class Warp(BaseModel):
    points: list[list[float]]


@app.post('/api/jobs/{jid}/warp')
def warp(jid: str, body: Warp):
    with LOCK:
        job = read_job(jid)
        require_idle(job)
        if job['cells']:
            raise HTTPException(409,'识别后不可改变几何坐标，请重新上传后拉正')
        path = job_path(jid)
        matrix = imaging.manual_warp(path / 'original.png',path / 'processed.png',body.points)
        job.update(matrix=matrix,revision=job['revision']+1)
        write_job(path,job)
        return public(job)


class Cell(BaseModel):
    id: str
    row: int = Field(ge=1,le=10000)
    col: int = Field(ge=1,le=500)
    rowspan: int = Field(ge=1,le=10000)
    colspan: int = Field(ge=1,le=500)
    text: str = Field(max_length=32767)
    score: float | None = None
    polygon: list[float] = Field(default_factory=list,max_length=8)
    original_polygon: list[float] = Field(default_factory=list,max_length=256)
    confirmed: bool = False
    kind: str = 'cell'
    candidate_text: str | None = Field(default=None,max_length=32767)
    candidate_score: float | None = Field(default=None,ge=0,le=1,allow_inf_nan=False)
    assessment_source: str | None = Field(default=None,max_length=200)


def reassess_work(jid):
    path=job_path(jid)
    try:
        cells,warnings,matrix,evidence=assessment.assess(path,read_job(jid)['cells'])
        (path / 'assessment.json').write_text(json.dumps(evidence,ensure_ascii=False),encoding='utf-8')
        with LOCK:
            job=read_job(jid)
            job.update(cells=cells,matrix=matrix,registration=evidence['registration'],status='review',
                error=None,revision=job['revision']+1)
            previous=[w for w in job['warnings'] if not w.startswith(('单元格定位：','本地表格线定位不可靠','原图配准未通过','云端增强改变了尺寸'))]
            job['warnings']=list(dict.fromkeys(previous+warnings))
            write_job(path,job)
    except Exception:
        with LOCK:
            job=read_job(jid)
            job.update(status='review',error='本地定位与评估失败，原识别结果保留；请人工校对。',revision=job['revision']+1)
            write_job(path,job)


@app.post('/api/jobs/{jid}/assess')
def reassess(jid: str):
    with LOCK:
        job=read_job(jid)
        require_idle(job)
        if job.get('provider')!='camscanner' or not job['cells']:
            raise HTTPException(409,'请先完成扫描全能王表格识别')
        job.update(status='recognizing',error=None)
        write_job(job_path(jid),job)
    POOL.submit(reassess_work,jid)
    return public(job)


class Save(BaseModel):
    revision: int
    cells: list[Cell] = Field(max_length=30000)


@app.put('/api/jobs/{jid}')
def save(jid: str, body: Save):
    cells = [c.model_dump() for c in body.cells]
    validate(cells)
    for c in cells:
        polygon = c['polygon']
        if len(polygon) not in (0,8) or any(not math.isfinite(v) or v<0 or v>10000 for v in polygon):
            raise ValueError('图片区域坐标无效')
        outline=c['original_polygon']
        if (outline and (len(outline)<8 or len(outline)%2)) or any(not math.isfinite(v) or v<0 or v>10000 for v in outline):
            raise ValueError('原图区域坐标无效')
    with LOCK:
        job = read_job(jid)
        require_idle(job)
        if body.revision != job['revision']:
            raise HTTPException(409,'另一窗口已修改此任务，请重新载入')
        job.update(cells=cells,revision=job['revision']+1,status='review')
        write_job(job_path(jid),job)
        return public(job)


@app.get('/api/jobs/{jid}/excel')
def download(jid: str, draft: bool = False):
    with LOCK:
        job = read_job(jid)
        require_idle(job)
        if not job['cells']:
            raise HTTPException(409,'暂无可导出的单元格，请先识别图片')
        path = job_path(jid)
        target = path / f'result-{job["revision"]}.xlsx'
        export(job['cells'],path / 'original.png',target)
    return FileResponse(target,filename=f'{"未校对草稿" if draft else "表格"}-{jid[:8]}.xlsx')


@app.get('/api/auth/status')
def auth_status():
    try:
        output = providers.cli(['auth','status','--json'],30)
        # Return only safe status summary, not tokens or account details.
        logged_in = False
        try:
            payload = json.loads(output)
            logged_in = payload.get('logged_in') is True or payload.get('authenticated') is True
        except json.JSONDecodeError:
            pass
        return {'installed':True,'logged_in':logged_in,**providers.login_details(),
            'message':'已登录扫描全能王' if logged_in else '请点击登录，在官方页面完成授权。'}
    except Exception:
        return {'installed':providers.CLI.is_file(),'logged_in':False,**providers.login_details(),
            'message':'授权检查失败，可点击登录重试；详情见官方登录窗口。'}


@app.post('/api/auth/login')
def auth_login():
    providers.start_login()
    return {'started':True,**providers.login_details(),'message':'请打开下方官方授权链接，在浏览器完成登录。'}


@app.post('/api/auth/cancel')
def auth_cancel():
    providers.cancel_login()
    return {'cancelled':True}


app.mount('/',StaticFiles(directory=ROOT / 'web',html=True),name='web')
