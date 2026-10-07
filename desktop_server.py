"""Hidden server entry point used by the Windows launcher."""
import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
os.chdir(root)
(root / 'data').mkdir(exist_ok=True)
sys.stdout = open(root / 'data/desktop-server.log', 'a', encoding='utf-8', buffering=1)
sys.stderr = sys.stdout
import uvicorn

if __name__ == '__main__':
    uvicorn.run('app:app', host='127.0.0.1', port=8788)
