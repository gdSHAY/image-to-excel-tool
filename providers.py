import os
from pathlib import Path
import subprocess
import threading
import time
import re
from urllib.parse import urlparse
import httpx
from tables import from_textin, from_workbook

ROOT = Path(__file__).resolve().parent
CLI = ROOT / 'node_modules/@camscanner-cli/win32-x64/bin/camscanner-cli.exe'
LOGIN_PROCESS = None
LOGIN_LOCK = threading.Lock()
LOGIN_STATE = {'url':None,'error':None,'started_at':None}


def login_running():
    return LOGIN_PROCESS is not None and LOGIN_PROCESS.poll() is None


def login_details():
    with LOGIN_LOCK:
        return dict(login_in_progress=login_running(),login_url=LOGIN_STATE['url'] if login_running() else None,
            login_error=LOGIN_STATE['error'])


def auth_environment():
    env = os.environ.copy()
    env['LOCALAPPDATA'] = str(ROOT / 'data/auth')
    return env


def allowed_auth_url(url):
    parsed = urlparse(url)
    return parsed.scheme == 'https' and parsed.hostname == 'www.camscanner.com' and parsed.path == '/agent-auth'


def monitor_login(process, ready):
    # Only the official authorization URL is exposed. Never expose CLI auth tokens/output.
    def expire():
        with LOGIN_LOCK:
            if LOGIN_PROCESS is process and process.poll() is None:
                LOGIN_STATE['error'] = '登录等待已超时，请重新点击登录。'
                process.terminate()
    timer = threading.Timer(320,expire)
    timer.daemon = True
    timer.start()
    try:
        for line in process.stdout:
            for url in re.findall(r'https?://[^\s<>\"\x1b]+',line):
                if allowed_auth_url(url):
                    with LOGIN_LOCK:
                        if LOGIN_PROCESS is process:
                            LOGIN_STATE['url'] = url
                    ready.set()
        code = process.wait()
        with LOGIN_LOCK:
            if LOGIN_PROCESS is process:
                LOGIN_STATE['url'] = None
                if code and not LOGIN_STATE['error']:
                    LOGIN_STATE['error'] = '官方登录未完成或已过期，请重新登录；检查网络和浏览器授权。'
    except (OSError,ValueError):
        with LOGIN_LOCK:
            if LOGIN_PROCESS is process:
                LOGIN_STATE['error'] = '无法读取官方登录结果，请重试。'
    finally:
        timer.cancel()
        ready.set()


def cancel_login():
    with LOGIN_LOCK:
        if login_running():
            LOGIN_PROCESS.terminate()
        LOGIN_STATE.update(url=None,error='已取消登录，可重新登录。')


def start_login():
    global LOGIN_PROCESS
    with LOGIN_LOCK:
        if login_running():
            return
        if not CLI.is_file():
            raise ValueError('官方 CLI 未安装，请运行 setup.ps1')
        ready = threading.Event()
        LOGIN_STATE.update(url=None,error=None,started_at=time.monotonic())
        # Keep the CLI waiting for its callback, while the UI presents its official URL.
        LOGIN_PROCESS = subprocess.Popen(
            [str(CLI),'auth','login','--no-browser'],cwd=ROOT,env=auth_environment(),
            stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        threading.Thread(target=monitor_login,args=(LOGIN_PROCESS,ready),daemon=True).start()
    ready.wait(timeout=8)


def cli(args, timeout=300):
    if not CLI.is_file():
        raise ValueError('官方 CLI 未安装，请运行 setup.ps1')
    env = auth_environment()
    try:
        run = subprocess.run([str(CLI),*map(str,args)], cwd=ROOT, env=env,
            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    except subprocess.TimeoutExpired as exc:
        raise ValueError(f'扫描全能王请求超过 {timeout} 秒，结果未知。请先检查账户记录，再手动继续；未自动重试。') from exc
    if run.returncode:
        # Classify known diagnostics without exposing tokens, URLs, headers or raw output.
        message=(run.stderr+'\n'+run.stdout).lower()
        if any(s in message for s in ('insufficient','quota exceeded','余额不足','额度不足')):
            reason='账户额度不足，请在官方页面检查额度'
        elif any(s in message for s in ('unauthorized','token expired','not logged in','未登录','授权过期')):
            reason='官方授权无效或已过期，请重新登录'
        elif any(s in message for s in ('429','rate limit','请求过于频繁')):
            reason='官方服务限流，请稍后手动继续'
        elif any(s in message for s in ('timeout','timed out','connection','dial tcp','tls handshake','no such host')):
            reason='官方请求网络连接或超时失败，结果未知，请先检查账户记录'
        else:
            reason=f'官方 CLI 返回失败（退出码 {run.returncode}），未提供可确认的安全原因'
        raise ValueError(f'扫描全能王：{reason}；未自动重试。')
    return run.stdout


def recognize(image, provider, app_id='', secret=''):
    if provider == 'camscanner':
        target = image.parent / 'cloud.xlsx'
        cli(['image','convert',image,'--format','excel','-o',target])
        if not target.is_file():
            raise ValueError('云端未返回 Excel 文件')
        return from_workbook(target), None
    if not app_id or not secret:
        raise ValueError('请在本地界面填写 TextIn App ID 和 Secret Code')
    data = image.read_bytes()
    if len(data) > 10_000_000:
        raise ValueError('TextIn 图片限制10MB，请缩小文件后重试')
    response = httpx.post('https://api.textin.com/ai/service/v2/recognize/table',
        params={'character':1,'straighten':0,'output_order':'perpendicular','excel':0},
        headers={'x-ti-app-id':app_id,'x-ti-secret-code':secret,'Content-Type':'application/octet-stream'},
        content=data,timeout=180)
    response.raise_for_status()
    payload = response.json()
    return from_textin(payload), payload
