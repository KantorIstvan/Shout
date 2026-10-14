"""Update check: asks GitHub for the latest release tag. Notification only, nothing is downloaded."""
import json
import re
import urllib.request

from version import __version__

REPO = 'KantorIstvan/Shout'
API = f'https://api.github.com/repos/{REPO}/releases/latest'


def parse_version(tag):
    m = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)', tag.strip())
    return tuple(int(g) for g in m.groups()) if m else None


def is_newer(tag, current=__version__):
    a, b = parse_version(tag), parse_version(current)
    return bool(a and b and a > b)  # pre-release or odd tags (v1.2.0-beta) never count


def release_url(tag):
    return f'https://github.com/{REPO}/releases/tag/{tag}'  # built from the validated tag, not taken from the response


def latest_newer_tag():
    """Tag of a newer release, or None. Network and API errors propagate to the caller."""
    req = urllib.request.Request(API, headers={'User-Agent': f'Shout/{__version__}',
                                               'Accept': 'application/vnd.github+json'})
    with urllib.request.urlopen(req, timeout=10) as r:
        tag = json.load(r)['tag_name']
    return tag if is_newer(tag) else None
