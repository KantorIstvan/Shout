from engine import pick_language, clean_text
from keys import Hotkey, VK_LCONTROL, VK_LWIN, VK_SPACE, VK_ESCAPE


def test_pick_language():
    assert pick_language([('fi', .5), ('hu', .3), ('en', .1)]) == 'hu'
    assert pick_language([('en', .6), ('hu', .2)]) == 'en'
    assert pick_language([('de', .9)]) == 'hu'


def test_clean_text():
    assert clean_text('  Szia,   hogy vagy? ') == 'Szia, hogy vagy?'
    assert clean_text('Feliratozta: Kiss Pista') == ''
    assert clean_text('Köszönöm, hogy megnézted!') == ''
    assert clean_text(' Thank you for watching. ') == ''
    assert clean_text('...') == ''
    assert clean_text('Köszönöm a segítséget a projektben.') == 'Köszönöm a segítséget a projektben.'


def run(h, seq):
    return [h.feed(vk, down, t)[0] for vk, down, t in seq]


def test_ptt():
    h = Hotkey()
    assert run(h, [(VK_LCONTROL, 1, 0), (VK_LWIN, 1, .1), (VK_LWIN, 0, 1.5), (VK_LCONTROL, 0, 1.6)]) == [None, 'start', 'stop', None]
    assert h.state == 'idle'


def test_win_first_then_ctrl():
    h = Hotkey()
    assert run(h, [(VK_LWIN, 1, 0), (VK_LCONTROL, 1, .1), (VK_LCONTROL, 0, 1.5), (VK_LWIN, 0, 1.6)]) == [None, 'start', 'stop', None]


def test_key_repeat_is_ignored():
    h = Hotkey()
    assert run(h, [(VK_LCONTROL, 1, 0), (VK_LWIN, 1, .1), (VK_LWIN, 1, .2), (VK_LCONTROL, 1, .3), (VK_LWIN, 0, 1)]) == [None, 'start', None, None, 'stop']


def test_short_hold_cancels():
    h = Hotkey()
    assert run(h, [(VK_LCONTROL, 1, 0), (VK_LWIN, 1, .1), (VK_LWIN, 0, .2)]) == [None, 'start', 'cancel']


def test_other_key_cancels_and_waits_for_release():
    h = Hotkey()
    ev = run(h, [(VK_LCONTROL, 1, 0), (VK_LWIN, 1, .1), (0x25, 1, .5), (0x25, 0, .6), (VK_LWIN, 0, .7), (VK_LCONTROL, 0, .8)])
    assert ev == [None, 'start', 'cancel', None, None, None]
    assert h.state == 'idle'


def test_handsfree():
    h = Hotkey()
    assert run(h, [(VK_LCONTROL, 1, 0), (VK_LWIN, 1, .1)]) == [None, 'start']
    assert h.feed(VK_SPACE, 1, .2) == ('handsfree', True)
    assert h.feed(VK_SPACE, 0, .3) == (None, True)
    assert run(h, [(VK_LWIN, 0, .4), (VK_LCONTROL, 0, .5)]) == [None, None]
    assert h.state == 'free'
    assert run(h, [(VK_LCONTROL, 1, 5), (VK_LWIN, 1, 5.1)]) == [None, 'stop']
    assert run(h, [(VK_LWIN, 0, 5.2), (VK_LCONTROL, 0, 5.3)]) == [None, None]
    assert h.state == 'idle'


def test_esc_cancels_handsfree_and_is_suppressed():
    h = Hotkey()
    run(h, [(VK_LCONTROL, 1, 0), (VK_LWIN, 1, .1), (VK_SPACE, 1, .2), (VK_SPACE, 0, .3), (VK_LWIN, 0, .4), (VK_LCONTROL, 0, .5)])
    assert h.feed(VK_ESCAPE, 1, 2) == ('cancel', True)
    assert h.feed(VK_ESCAPE, 0, 2.1) == (None, True)
    assert h.state == 'idle'


def test_esc_when_idle_passes_through():
    h = Hotkey()
    assert h.feed(VK_ESCAPE, 1, 0) == (None, False)


def test_no_start_with_extra_modifier():
    h = Hotkey()
    assert run(h, [(0xA0, 1, 0), (VK_LCONTROL, 1, .1), (VK_LWIN, 1, .2)]) == [None, None, None]


def test_update_versions():
    from updates import is_newer, parse_version, release_url
    assert parse_version('v1.10.0') == (1, 10, 0)
    assert is_newer('v1.10.0', '1.9.0')  # numeric, not string, comparison
    assert is_newer('v2.0.0', '1.99.99')
    assert not is_newer('v1.1.0', '1.1.0')
    assert not is_newer('v1.0.0', '1.1.0')
    assert not is_newer('v1.2.0-beta', '1.1.0')
    assert not is_newer('nightly', '1.1.0')
    assert release_url('v1.2.0') == 'https://github.com/KantorIstvan/Shout/releases/tag/v1.2.0'


def test_dictionary_entries():
    from engine import PROMPT_TOKENS, add_entries, dictionary_prompt, parse_entries, prompt_tokens
    assert parse_entries('Kovács Bence,  pull   request\n\nKubernetes; Letterboxd ') == \
        ['Kovács Bence', 'pull request', 'Kubernetes', 'Letterboxd']
    assert dictionary_prompt([]) == '' and prompt_tokens([]) == 0
    words, added, dup, rejected = add_entries(['Kubernetes'], 'kubernetes, Docker, docker')
    assert words == ['Kubernetes', 'Docker'] and (added, dup, rejected) == (1, 2, 0)
    many = '\n'.join(f'Szakkifejezés{i}' for i in range(500))
    words, added, dup, rejected = add_entries([], many)
    assert 20 < added < 100 and rejected == 500 - added  # hard limit, nothing beyond the prompt budget
    assert prompt_tokens(words) <= PROMPT_TOKENS


def test_settings_migrates_old_dictionary(tmp_path, monkeypatch):
    import json
    import shout
    f = tmp_path / 'settings.json'
    f.write_text(json.dumps({'dictionary': 'Kovács Bence\nKubernetes\n\n'}), encoding='utf-8')
    monkeypatch.setattr(shout, 'SETTINGS_FILE', str(f))
    assert shout.load_settings()['dictionary'] == ['Kovács Bence', 'Kubernetes']
def test_prompt_accepts_string():
    from engine import dictionary_prompt
    assert dictionary_prompt('Kovács Bence\nKubernetes') == 'Kovács Bence, Kubernetes.'


def test_install_target(tmp_path):
    from installer import resolve_target, same_path
    assert resolve_target(str(tmp_path / 'new')) == str(tmp_path / 'new')  # missing folder: used as is
    busy = tmp_path / 'Downloads'
    busy.mkdir()
    (busy / 'photo.jpg').write_text('x')
    assert resolve_target(str(busy)) == str(busy / 'Shout')  # never spill into a folder with other files
    old = tmp_path / 'OldShout'
    old.mkdir()
    (old / 'Shout.exe').write_text('x')
    assert resolve_target(str(old)) == str(old)  # an existing Shout folder gets updated in place
    assert same_path(str(old), str(old).upper()) and not same_path(str(old), None)


def test_decode_text_encodings():
    from engine import decode_text, parse_entries
    words = 'Kovács Bence\r\nŐrség\r\nÜllői út\r\n'
    for data in (words.encode('utf-8'), words.encode('utf-8-sig'), words.encode('utf-16'), words.encode('cp1250')):
        assert parse_entries(decode_text(data)) == ['Kovács Bence', 'Őrség', 'Üllői út']


def test_pick_release():
    from updates import pick_release
    asset = {'name': 'Shout-1.3.0.zip', 'size': 10, 'digest': 'sha256:ABC',
             'browser_download_url': 'https://github.com/KantorIstvan/Shout/releases/download/v1.3.0/Shout-1.3.0.zip'}
    r = pick_release({'tag_name': 'v1.3.0', 'assets': [asset]}, current='1.2.0')
    assert r.tag == 'v1.3.0' and r.url.endswith('Shout-1.3.0.zip') and r.sha256 == 'abc'
    assert pick_release({'tag_name': 'v1.2.0', 'assets': [asset]}, current='1.2.0') is None
    evil = dict(asset, browser_download_url='https://evil.example/Shout-1.3.0.zip')
    assert pick_release({'tag_name': 'v1.3.0', 'assets': [evil]}, current='1.2.0').url is None  # only our repo
    assert pick_release({'tag_name': 'v1.3.0', 'assets': []}, current='1.2.0').url is None


def test_download_update_verifies(tmp_path):
    import hashlib, os, pathlib, zipfile
    import pytest
    from updates import Release, download_update

    def make_zip(exe_bytes):
        z = tmp_path / 'Shout-9.9.9.zip'
        with zipfile.ZipFile(z, 'w') as f:
            f.writestr('Shout/Shout.exe', exe_bytes)
            f.writestr('Shout/app/version.py', "__version__ = '9.9.9'")
        return z, hashlib.sha256(z.read_bytes()).hexdigest()

    z, digest = make_zip(b'not a signed exe')
    url = pathlib.Path(z).as_uri()
    with pytest.raises(RuntimeError, match='sérült'):
        download_update(Release('v9.9.9', url, 0, '0' * 64), lambda f: None, str(tmp_path / 'w1'))
    with pytest.raises(RuntimeError, match='ellenőrzése'):
        download_update(Release('v9.9.9', url, 0, digest), lambda f: None, str(tmp_path / 'w2'))
    signed = pathlib.Path(__file__).parent / 'dist' / 'Shout' / 'Shout.exe'
    if signed.exists():  # needs a build; the real python.org-signed launcher must pass
        z, digest = make_zip(signed.read_bytes())
        exe = download_update(Release('v9.9.9', pathlib.Path(z).as_uri(), 0, digest), lambda f: None, str(tmp_path / 'w3'))
        assert exe.endswith(os.path.join('v9.9.9', 'Shout', 'Shout.exe')) and os.path.exists(exe)
