import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
log = ROOT / "server.log"
cmd = [
    sys.executable,
    "-m",
    "uvicorn",
    "app.main:app",
    "--host",
    "127.0.0.1",
    "--port",
    "8000",
]

with log.open("ab") as handle:
    process = subprocess.Popen(
        cmd,
        cwd=ROOT,
        stdout=handle,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
    )

print(process.pid)
