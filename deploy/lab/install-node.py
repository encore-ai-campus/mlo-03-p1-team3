"""Install official Node.js 22 for frontend builds under the controller user's home."""
import hashlib
import re
import shutil
import tarfile
import tempfile
from pathlib import Path
from urllib.request import urlopen

base = 'https://nodejs.org/dist/latest-v22.x/'
with urlopen(base + 'SHASUMS256.txt', timeout=30) as response:
    manifest = response.read().decode()
match = re.search(r'^([a-f0-9]{64})\s+(node-v22\.[0-9.]+-linux-x64\.tar\.xz)$', manifest, re.MULTILINE)
if not match:
    raise SystemExit('Official Node.js 22 Linux checksum entry missing')
checksum, filename = match.groups()
with tempfile.TemporaryDirectory() as directory:
    archive = Path(directory) / filename
    with urlopen(base + filename, timeout=60) as response, archive.open('wb') as target:
        shutil.copyfileobj(response, target)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != checksum:
        raise SystemExit('Node.js download checksum mismatch')
    with tarfile.open(archive) as tar:
        tar.extractall(Path(directory) / 'unpack', filter='data')
    source = Path(directory) / 'unpack' / filename.removesuffix('.tar.xz')
    target = Path.home() / '.local/podobank-node'
    if target.exists():
        raise SystemExit('Existing private Node installation preserved; inspect it before replacement')
    target.parent.mkdir(exist_ok=True, parents=True)
    shutil.move(str(source), target)
print('Official Node.js 22 installed; SHA-256 verified.')
