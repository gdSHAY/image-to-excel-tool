"""Package only runtime, application resources and no authentication data."""
from pathlib import Path
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parent
report_path = ROOT / 'release/portable-build.json'
report = json.loads(report_path.read_text(encoding='utf-8'))
build = Path(report['build']).resolve()
assert build.is_relative_to((ROOT / 'release').resolve())

def included(path):
    parts = path.relative_to(build).parts
    if '__pycache__' in parts or path.suffix == '.pyc':
        return False
    if parts[0] == 'verification':
        return False
    if parts[0] == 'data':
        return False
    return path.name != '文件校验.json'

files = sorted(p for p in build.rglob('*') if p.is_file() and included(p))
manifest = {p.relative_to(build).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
manifest_path = build / '文件校验.json'
manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
files.append(manifest_path)
destination = ROOT / 'image-to-excel-tool-v1.0.0-win-x64.zip'
with zipfile.ZipFile(destination,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
    for p in files:
        archive.write(p, 'ScanTableStudio/' + p.relative_to(build).as_posix())
with zipfile.ZipFile(destination) as archive:
    assert archive.testzip() is None
    for relative, expected in manifest.items():
        assert hashlib.sha256(archive.read('ScanTableStudio/'+relative)).hexdigest() == expected, relative
    names = archive.namelist()
    assert not any('/data/jobs/' in n or '/data/deleted-jobs/' in n for n in names)
    assert not any(n.startswith('ScanTableStudio/data/') or n.endswith('.enc') or n.endswith('master.key') for n in names)
sha = hashlib.sha256(destination.read_bytes()).hexdigest()
destination.with_suffix('.zip.sha256').write_text(sha+'  '+destination.name+'\n',encoding='utf-8')
report.update(contains_auth=False,files=len(files),zip=str(destination),bytes=destination.stat().st_size,
              sha256=sha,zip_crc_verified=True,zip_hashes_verified=True)
report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False),flush=True)
