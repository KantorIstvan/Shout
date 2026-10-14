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
