"""Shout keyboard: hotkey state machine, low-level hook, synthetic key presses."""
import ctypes
import logging
import time

log = logging.getLogger('shout')

VK_CONTROL, VK_LCONTROL, VK_RCONTROL = 0x11, 0xA2, 0xA3
VK_LWIN, VK_RWIN = 0x5B, 0x5C
VK_SPACE, VK_ESCAPE = 0x20, 0x1B
VK_MASK = 0xE8  # unassigned VK: tapping it while Win is down stops the Start menu from opening
_CTRL = {VK_CONTROL, VK_LCONTROL, VK_RCONTROL}
_WIN = {VK_LWIN, VK_RWIN}
_COMBO = {'ctrl', 'win'}
MIN_HOLD = 0.3


class Hotkey:
    """Ctrl+Win hold = push-to-talk, +Space = hands-free, Esc = cancel.

    feed() returns (event, suppress): event in {'start', 'handsfree', 'stop', 'cancel', None};
    suppress means the key must not reach the focused app.
    """

    def __init__(self):
        self.down = set()
        self.state = 'idle'
        self.t0 = 0.0
        self.eaten = set()  # keys whose press we swallowed, so their release is swallowed too

    def feed(self, vk, down, t):
        k = 'ctrl' if vk in _CTRL else 'win' if vk in _WIN else vk
        if down:
            if k in self.down:  # auto-repeat
                return None, vk in self.eaten
            self.down.add(k)
            swallow = False
        else:
            self.down.discard(k)
            swallow = vk in self.eaten
            self.eaten.discard(vk)
        event = self._step(k, down, t)
        if event in ('handsfree', 'cancel') and down and k in (VK_SPACE, VK_ESCAPE):
            self.eaten.add(vk)
            swallow = True
        return event, swallow

    def _step(self, k, down, t):
        combo = self.down == _COMBO
        if self.state == 'idle':
            if down and combo:
                self.state, self.t0 = 'ptt', t
                return 'start'
        elif self.state == 'ptt':
            if down:
                if k == VK_SPACE:
                    self.state = 'free'
                    return 'handsfree'
                self.state = 'wait'  # Esc, or Ctrl+Win+<other>: an OS shortcut, not dictation
                return 'cancel'
            if k in _COMBO:
                self._settle()
                return 'stop' if t - self.t0 >= MIN_HOLD else 'cancel'
        elif self.state == 'free':
            if down and k == VK_ESCAPE:
                self._settle()
                return 'cancel'
            if down and combo:
                self.state = 'wait'
                return 'stop'
        elif self.state == 'wait':
            self._settle()
        return None

    def _settle(self):
        self.state = 'wait' if _COMBO & self.down else 'idle'


user32 = ctypes.WinDLL('user32', use_last_error=True)
_KEYUP = 0x0002


def _tap(vk):
    user32.keybd_event(vk, 0, 0, 0)
    user32.keybd_event(vk, 0, _KEYUP, 0)


def mask_start_menu():
    _tap(VK_MASK)


def send_ctrl_v():
    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    _tap(0x56)
    user32.keybd_event(VK_CONTROL, 0, _KEYUP, 0)


def wait_modifiers_released(timeout=2.0):
    """Pasting while Win is still held would trigger Win+V instead of Ctrl+V."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if not any(user32.GetAsyncKeyState(vk) & 0x8000 for vk in (0x10, 0x11, 0x12, VK_LWIN, VK_RWIN)):
            return True
        time.sleep(0.02)
    return False


class KeyHook:
    """Global low-level keyboard hook (pynput thread). on_event is called from that thread."""

    _INJECTED = 0x10  # LLKHF_INJECTED: our own synthetic keys

    def __init__(self, on_event):
        self.on_event = on_event
        self.hotkey = Hotkey()
        self.listener = None

    def start(self):
        from pynput import keyboard

        def filt(msg, data):
            if data.flags & self._INJECTED:
                return False
            try:
                event, swallow = self.hotkey.feed(data.vkCode, msg in (0x100, 0x104), time.monotonic())
                if event:
                    if 'win' in self.hotkey.down:
                        mask_start_menu()
                    self.on_event(event)
            except Exception:
                log.exception('hotkey handler failed')
                return False
            if swallow:
                self.listener.suppress_event()
            return False  # pynput's own key callbacks are unused

        self.listener = keyboard.Listener(win32_event_filter=filt)
        self.listener.start()

    def stop(self):
        if self.listener:
            self.listener.stop()
