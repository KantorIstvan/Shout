"""Update check and one-click update from GitHub Releases.

The newest release's Shout-X.Y.Z.zip is downloaded, checked against GitHub's SHA-256 digest, extracted, and its
Shout.exe must carry a valid Python Software Foundation signature. That copy then runs `Shout.exe -X update`
(installer.run_update), which replaces the installed version and starts it. Files downloaded by the app itself get
no Mark-of-the-Web, so Smart App Control treats them like the original install.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import urllib.request
import zipfile
from collections import namedtuple

from version import __version__

REPO = 'KantorIstvan/Shout'
API = f'https://api.github.com/repos/{REPO}/releases/latest'
DOWNLOAD_PREFIX = f'https://github.com/{REPO}/releases/download/'
UPDATE_DIR = os.path.join(os.environ['LOCALAPPDATA'], 'Shout', 'update')
NO_WINDOW = 0x08000000

Release = namedtuple('Release', 'tag url size sha256')  # url is None when the release has no ZIP attached


def parse_version(tag):
    m = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)', tag.strip())
    return tuple(int(g) for g in m.groups()) if m else None


def is_newer(tag, current=__version__):
    a, b = parse_version(tag), parse_version(current)
    return bool(a and b and a > b)  # pre-release or odd tags (v1.2.0-beta) never count


def release_url(tag):
    return f'https://github.com/{REPO}/releases/tag/{tag}'  # built from the validated tag, not taken from the response


def pick_release(data, current=__version__):
    """The newer release described by GitHub's API response, or None."""
    tag = data.get('tag_name') or ''
    if not is_newer(tag, current):
        return None
    for asset in data.get('assets') or []:
        name, url = asset.get('name') or '', asset.get('browser_download_url') or ''
        if re.fullmatch(r'Shout-\d+\.\d+\.\d+\.zip', name) and url.startswith(DOWNLOAD_PREFIX):
            digest = asset.get('digest') or ''
            return Release(tag, url, asset.get('size') or 0, digest[7:].lower() if digest.startswith('sha256:') else None)
    return Release(tag, None, 0, None)


def _request(url):
    return urllib.request.Request(url, headers={'User-Agent': f'Shout/{__version__}',
                                                'Accept': 'application/vnd.github+json'})


def newer_release():
    """Network and API errors propagate to the caller."""
    with urllib.request.urlopen(_request(API), timeout=10) as r:
        return pick_release(json.load(r))


def signed_by_psf(path):
    """Shout.exe is python.org's pythonw.exe: anything else in its place means a broken or tampered download."""
    script = ('$s = Get-AuthenticodeSignature -LiteralPath $env:SHOUT_SIG_PATH; '
              '"$($s.Status)|$($s.SignerCertificate.Subject)"')
    r = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', script],
                       env={**os.environ, 'SHOUT_SIG_PATH': path}, capture_output=True, text=True,
                       creationflags=NO_WINDOW, timeout=60)
    status, _, subject = r.stdout.strip().partition('|')
    return status == 'Valid' and 'O=Python Software Foundation' in subject


def download_update(release, progress, workdir=UPDATE_DIR):
    """Download, verify and extract the release. Returns the path of the new Shout.exe."""
    os.makedirs(workdir, exist_ok=True)
    zip_path = os.path.join(workdir, 'update.zip')
    part = zip_path + '.part'
    h = hashlib.sha256()
    with urllib.request.urlopen(_request(release.url), timeout=60) as r, open(part, 'wb') as f:
        total, done = int(r.headers.get('Content-Length') or release.size or 0), 0
        while chunk := r.read(1 << 20):
            f.write(chunk)
            h.update(chunk)
            done += len(chunk)
            if total:
                progress(min(done / total, 1.0))
    if release.sha256 and h.hexdigest() != release.sha256:
        os.remove(part)
        raise RuntimeError('A letöltött fájl sérült. Próbáld újra.')
    os.replace(part, zip_path)
    dest = os.path.join(workdir, release.tag)  # the tag passed the version regex, safe as a folder name
    shutil.rmtree(dest, ignore_errors=True)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(dest)  # zipfile drops absolute paths and '..' components
    os.remove(zip_path)
    exe = os.path.join(dest, 'Shout', 'Shout.exe')
    if not (os.path.exists(exe) and signed_by_psf(exe)):
        shutil.rmtree(dest, ignore_errors=True)
        raise RuntimeError('Az új verzió ellenőrzése nem sikerült, a frissítés megszakítva.')
    return exe
