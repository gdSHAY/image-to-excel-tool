"""Build an anonymous portable runtime without credentials or history."""
from pathlib import Path
import datetime
import hashlib
import json
import shutil
import zipfile
import sys

ROOT = Path(__file__).resolve().parent
BASE = Path(sys.base_prefix)
stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
BUILD = ROOT / 'release' / ('portable-' + stamp) / 'ScanTableStudio'
BUILD.mkdir(parents=True)
runtime = BUILD / 'runtime'
runtime.mkdir()
for name in ['python.exe','pythonw.exe','python3.dll','python313.dll',
             'vcruntime140.dll','vcruntime140_1.dll','LICENSE.txt']:
    shutil.copy2(BASE / name, runtime / name)
for name in ['msvcp140.dll','msvcp140_1.dll','msvcp140_2.dll',
             'msvcp140_atomic_wait.dll','msvcp140_codecvt_ids.dll','concrt140.dll','vcomp140.dll']:
    source = Path('C:/Windows/System32') / name
    if source.is_file():
        shutil.copy2(source, runtime / name)
ignore = shutil.ignore_patterns('__pycache__', '*.pyc', 'test', 'tests')
shutil.copytree(BASE / 'DLLs', runtime / 'DLLs', ignore=ignore)
shutil.copytree(BASE / 'Lib', runtime / 'Lib',
    ignore=shutil.ignore_patterns('site-packages','__pycache__','*.pyc','test','tests','ensurepip','idlelib'))
shutil.copytree(ROOT / '.venv/Lib/site-packages', runtime / 'Lib/site-packages', ignore=ignore)
(runtime / 'python313._pth').write_text('.\nDLLs\nLib\nLib/site-packages\n..\n', encoding='utf-8')
for name in ['app.py','imaging.py','assessment.py','providers.py','tables.py',
             'desktop_server.py','图片表格工作台.exe']:
    shutil.copy2(ROOT / name, BUILD / name)
shutil.copytree(ROOT / 'web', BUILD / 'web')
cli_dir = Path('node_modules/@camscanner-cli/win32-x64')
shutil.copytree(ROOT / cli_dir, BUILD / cli_dir)
shutil.copy2(ROOT / 'node_modules/camscanner-cli/README.md', BUILD / cli_dir / 'CLI-README.md')
(BUILD / 'data').mkdir()
# Public builds never copy credentials or task data.
(BUILD / '使用说明.txt').write_text('''图片表格工作台 · Windows 10/11 x64 免安装便携版

1. 完整解压 ZIP 到可写文件夹（不要在压缩包里直接运行）。
2. 双击“图片表格工作台.exe”，工作台会在浏览器打开。
3. 顶部“配置”登录扫描全能王，确认选项并保存配置。
4. 选择图片、上传识别、看图校对、直接导出 Excel。

无需另外安装 Python、Node.js 或下载本地 OCR 模型。
扫描全能王云识别、增强和登录仍需联网，会使用登录账号的额度。
本公开版不含登录凭据、密钥、照片或历史记录。请登录自己的账号。
保留 runtime、node_modules、web 等目录，不能单独移动 EXE。
任务和图片保存在同目录 data；删除历史可撤销，不会删除电脑上的源文件。
启动器可停止本机工作台；关闭网页不等于停止服务。

已内置 Python 3.13、应用依赖、PP-OCRv6 本地模型及官方 CamScanner CLI。
各组件遵循其原许可证，Python LICENSE.txt 与依赖 dist-info/licenses 随包保留。
扫描全能王服务及 CLI 使用遵循供应商条款。
''', encoding='utf-8-sig')
manifest = {str(p.relative_to(BUILD)).replace('\\','/'): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in BUILD.rglob('*') if p.is_file()}
(BUILD / '文件校验.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
report = {'build': str(BUILD), 'files':len(manifest), 'runtime_isolated':True,
          'contains_auth':False,
          'models':[p.name for p in (runtime/'Lib/site-packages/rapidocr/models').glob('*.onnx')]}
(ROOT/'release/portable-build.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False),flush=True)
