"""Shout: hold Ctrl+Win, speak Hungarian or English, release, and the text is typed where your cursor is."""
import ctypes
import json
import logging
import os
import sys
import threading
import winreg
from datetime import datetime

from PySide6.QtCore import QMimeData, QObject, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QDesktopServices, QGuiApplication, QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

import ui
from engine import DATA_DIR, SR, Recorder, Transcriber, clean_text, parse_entries
from keys import KeyHook, send_ctrl_v, wait_modifiers_released
from updates import latest_newer_tag, release_url

log = logging.getLogger('shout')

CONFIG_DIR = os.path.join(os.environ['APPDATA'], 'Shout')
SETTINGS_FILE = os.path.join(CONFIG_DIR, 'settings.json')
HISTORY_FILE = os.path.join(CONFIG_DIR, 'history.jsonl')
DEFAULTS = {'language': 'auto', 'model': 'auto', 'mic': None, 'dictionary': [], 'check_updates': True,
            'update_notified': ''}
RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
PIPE_NAME = 'Shout-' + os.environ.get('USERNAME', 'user')
MUTEX_NAME = 'ShoutSingleInstance'  # also checked by the installer (AppMutex)
HISTORY_SHOWN = 300


# --------------------------------------------------------------------------- storage

def load_settings():
    try:
        with open(SETTINGS_FILE, encoding='utf-8') as f:
            s = {**DEFAULTS, **json.load(f)}
        if isinstance(s['dictionary'], str):  # 1.0 stored one newline-separated string
            s['dictionary'] = parse_entries(s['dictionary'])
        return s
    except (OSError, ValueError):
        return dict(DEFAULTS)


def save_settings(s):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    tmp = SETTINGS_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(s, f, ensure_ascii=False, indent=2)
    os.replace(tmp, SETTINGS_FILE)


def load_history():
    try:
        with open(HISTORY_FILE, encoding='utf-8') as f:
            lines = f.readlines()[-HISTORY_SHOWN:]
    except OSError:
        return []
    items = []
    for line in lines:
        try:
            items.append(json.loads(line))
        except ValueError:
            pass
    return items


def append_history(item):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(HISTORY_FILE, 'a', encoding='utf-8') as f:
        f.write(json.dumps(item, ensure_ascii=False) + '\n')


def autostart_command():
    if os.path.basename(sys.executable).lower() == 'shout.exe':
        return f'"{sys.executable}" -X tray'  # packaged: Shout.exe is the signed pythonw.exe
    pythonw = os.path.join(os.path.dirname(sys.executable), 'pythonw.exe')
    return f'"{pythonw}" "{os.path.abspath(__file__)}" --tray'


def autostart_enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, 'Shout')
            return True
    except OSError:
        return False


def set_autostart(on):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, 'Shout', 0, winreg.REG_SZ, autostart_command())
        else:
            try:
                winreg.DeleteValue(k, 'Shout')
            except OSError:
                pass


# --------------------------------------------------------------------------- app

class Controller(QObject):
    hotkey = Signal(str)
    level = Signal(float)
    done = Signal(str, str, float)
    failed = Signal(str)
    status = Signal(str, str, object)
    loaded = Signal(object)
    update_found = Signal(str)

    def __init__(self, app, show_window):
        super().__init__()
        self.app = app
        self.settings = load_settings()
        self.transcriber = None
        self.busy = False
        self.loading_text = 'A modell még töltődik'
        self.saved_clipboard = None

        self.pill = ui.Pill()
        self.window = ui.MainWindow(self.settings, Recorder.input_devices)
        self.window.winId()  # native window must exist to receive WM_DEVICECHANGE while hidden
        self.window.history.set_items(load_history())
        self.window.settings_page.set_autostart(autostart_enabled())
        self.window.settings_page.changed.connect(self.on_setting)
        self.window.dictionary.changed.connect(lambda words: self.on_setting('dictionary', words))
        self.window.device_change.connect(lambda: self.device_timer.start())
        self.device_timer = QTimer(self, singleShot=True, interval=1500, timeout=self.refresh_devices)
        self.restore_timer = QTimer(self, singleShot=True, interval=700, timeout=self.restore_clipboard)

        self.tray = QSystemTrayIcon(QIcon(os.path.join(ui.ASSETS, 'shout.ico')), self)
        menu = QMenu()
        for text, slot in (('Megnyitás', self.show_window), ('Utolsó másolása', self.copy_last)):
            a = QAction(text, menu)
            a.triggered.connect(slot)
            menu.addAction(a)
        menu.addSeparator()
        quit_action = QAction('Kilépés', menu)
        quit_action.triggered.connect(self.quit)
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda r: r == QSystemTrayIcon.ActivationReason.Trigger and self.show_window())
        self.tray.setToolTip('Shout')
        self.tray.show()
        self.update_tag = None
        self.tray.messageClicked.connect(lambda: self.update_tag and QDesktopServices.openUrl(QUrl(release_url(self.update_tag))))
        self.update_found.connect(self.on_update)
        self.update_timer = QTimer(self, interval=12 * 3600 * 1000, timeout=self.check_updates)
        QTimer.singleShot(20_000, self.check_updates)  # not during model load
        self.update_timer.start()

        self.recorder = Recorder(on_level=self.level.emit)
        self.hotkey.connect(self.on_hotkey)
        self.level.connect(self.pill.set_level)
        self.done.connect(self.on_done)
        self.failed.connect(self.on_failed)
        self.status.connect(self.on_status)
        self.loaded.connect(self.on_loaded)
        self.keyhook = KeyHook(self.hotkey.emit)
        self.keyhook.start()
        QGuiApplication.styleHints().colorSchemeChanged.connect(self.on_theme)

        self.load_model()
        if show_window:
            self.show_window()

    # model ------------------------------------------------------------------
    def load_model(self):
        self.transcriber = None
        self.window.set_status('', 'Modell betöltése', None)

        def progress(msg, frac):
            text = f'{msg} {round(frac * 100)}%' if frac is not None else msg
            self.status.emit('', text, frac)

        def work():
            try:
                t = Transcriber(self.settings['model'], progress)
                t.load()
                self.loaded.emit(t)
            except Exception:
                log.exception('model load failed')
                self.status.emit('', 'A modell betöltése nem sikerült. Részletek a shout.log fájlban.', None)
        threading.Thread(target=work, daemon=True).start()

    def on_loaded(self, t):
        self.transcriber = t
        device = 'GPU' if t.device == 'cuda' else 'CPU'
        self.on_status(f'{t.model_name} · {device}', 'Kész', None)

    def on_status(self, model, text, frac):
        self.window.set_status(model or self.window.model_label.text(), text, frac)
        if self.transcriber is None:
            self.loading_text = text  # shown in the pill if someone dictates before the model is ready
        self.tray.setToolTip(f'Shout: {text}')

    # dictation --------------------------------------------------------------
    def on_hotkey(self, event):
        if event == 'start':
            if self.transcriber is None:
                self.pill.show_message(self.loading_text)
                return
            if self.busy:
                return
            try:
                self.recorder.start(self.settings.get('mic'))
            except Exception:
                log.exception('microphone start failed')
                self.pill.show_message('Nem található mikrofon')
                return
            self.pill.show_recording()
        elif not self.recorder.active:
            return
        elif event == 'handsfree':
            self.pill.show_handsfree()
        elif event == 'cancel':
            self.recorder.stop()
            self.pill.hide_pill()
        elif event == 'stop':
            audio = self.recorder.stop()
            if len(audio) < SR * 0.3:
                self.pill.hide_pill()
                return
            self.busy = True
            self.pill.show_working()
            threading.Thread(target=self.transcribe, args=(audio,), daemon=True).start()

    def transcribe(self, audio):
        try:
            text, lang = self.transcriber.transcribe(audio, self.settings['language'], self.settings['dictionary'])
            text = clean_text(text)
            wait_modifiers_released()
            self.done.emit(text, lang, len(audio) / SR)
        except Exception:
            log.exception('transcription failed')
            self.failed.emit('Hiba a felismerés közben')

    def on_done(self, text, lang, seconds):
        self.busy = False
        if not text:
            self.pill.show_message('Nem hallottam semmit')
            return
        self.paste(text)
        self.pill.hide_pill()
        item = {'t': datetime.now().isoformat(timespec='seconds'), 'text': text, 'lang': lang,
                'seconds': round(seconds, 1)}
        append_history(item)
        self.window.history.add_item(item)
        log.info('dictated %.1fs [%s], %d chars', seconds, lang, len(text))

    def on_failed(self, message):
        self.busy = False
        self.pill.show_message(message, 2600)

    # clipboard paste, then put the user's clipboard back ----
    def paste(self, text):
        cb = QGuiApplication.clipboard()
        if not self.restore_timer.isActive():  # a restore is pending: keep the original snapshot
            self.saved_clipboard = QMimeData()
            original = cb.mimeData()
            for fmt in original.formats():
                self.saved_clipboard.setData(fmt, original.data(fmt))
            if original.hasImage():
                self.saved_clipboard.setImageData(original.imageData())
        self.restore_timer.stop()
        cb.setText(text)
        QTimer.singleShot(40, send_ctrl_v)
        self.restore_timer.start()

    def restore_clipboard(self):
        cb = QGuiApplication.clipboard()
        if self.saved_clipboard is not None and self.saved_clipboard.formats():
            cb.setMimeData(self.saved_clipboard)
        else:
            cb.clear()
        self.saved_clipboard = None

    # updates ----------------------------------------------------------------
    def check_updates(self):
        if not self.settings['check_updates']:
            return

        def work():
            try:
                tag = latest_newer_tag()
                if tag:
                    self.update_found.emit(tag)
            except Exception as e:  # offline, rate-limited, or no release yet (404): try again later
                log.info('update check skipped: %s', e)
        threading.Thread(target=work, daemon=True).start()

    def on_update(self, tag):
        self.update_tag = tag
        self.window.set_update(tag, release_url(tag))
        if self.settings['update_notified'] != tag:  # one popup per version, the sidebar link stays
            self.settings['update_notified'] = tag
            save_settings(self.settings)
            self.tray.showMessage('Shout frissítés', f'Elérhető a Shout {tag.lstrip("v")}. Kattints a letöltéshez.',
                                  QSystemTrayIcon.MessageIcon.Information, 10000)

    # misc -------------------------------------------------------------------
    def on_setting(self, key, value):
        if key == 'autostart':
            set_autostart(value)
            return
        self.settings[key] = value
        save_settings(self.settings)
        if key == 'check_updates' and value:
            self.check_updates()
        if key == 'model':
            self.load_model()

    def refresh_devices(self):
        if not self.recorder.active:
            try:
                Recorder.refresh()
            except Exception:
                log.exception('audio device refresh failed')

    def on_theme(self, *_):
        ui.apply_theme(self.app, os.path.join(DATA_DIR, 'cache'))
        self.window.refresh_icons()

    def show_window(self):
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def copy_last(self):
        items = self.window.history.items
        if items:
            QGuiApplication.clipboard().setText(items[-1]['text'])

    def quit(self):
        self.keyhook.stop()
        if self.recorder.active:
            self.recorder.stop()
        self.tray.hide()
        self.app.quit()


def setup_logging():
    os.makedirs(DATA_DIR, exist_ok=True)
    logging.basicConfig(filename=os.path.join(DATA_DIR, 'shout.log'), filemode='w', level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s', encoding='utf-8')
    sys.excepthook = lambda *exc: log.critical('uncaught', exc_info=exc)
    threading.excepthook = lambda a: log.critical('uncaught in thread', exc_info=(a.exc_type, a.exc_value, a.exc_traceback))


def main():
    if sys.stdout is None:  # pythonw: libraries that print must not crash
        sys.stdout = sys.stderr = open(os.devnull, 'w', encoding='utf-8')
    setup_logging()
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('Shout.Shout')
    app = QApplication(['Shout'])
    app.setApplicationName('Shout')
    app.setQuitOnLastWindowClosed(False)
    app.setStyle('Fusion')

    import installer
    if installer.packaged():
        if 'uninstall' in getattr(sys, '_xoptions', {}):
            ui.load_fonts()
            ui.apply_theme(app, os.path.join(DATA_DIR, 'cache'))
            return installer.uninstall()
        if installer.needs_install():  # started from an extracted ZIP: offer to install or update
            ui.load_fonts()
            ui.apply_theme(app, os.path.join(DATA_DIR, 'cache'))
            if installer.run_install_dialog() != 'portable':
                return 0

    sock = QLocalSocket()
    sock.connectToServer(PIPE_NAME)
    if sock.waitForConnected(300):  # already running: bring its window up instead
        sock.write(b'show')
        sock.waitForBytesWritten(300)
        return 0
    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)  # noqa: F841 (held for process life)
    server = QLocalServer()
    QLocalServer.removeServer(PIPE_NAME)
    server.listen(PIPE_NAME)

    ui.load_fonts()
    ui.apply_theme(app, os.path.join(DATA_DIR, 'cache'))
    tray_mode = '--tray' in sys.argv or 'tray' in getattr(sys, '_xoptions', {})
    first_run = not os.path.exists(SETTINGS_FILE)
    if first_run:
        save_settings(DEFAULTS)
    controller = Controller(app, show_window=first_run or not tray_mode)

    def on_connection():
        conn = server.nextPendingConnection()
        conn.waitForReadyRead(300)
        if bytes(conn.readAll()) == b'quit':  # the installer is replacing this copy
            controller.quit()
        else:
            controller.show_window()
    server.newConnection.connect(on_connection)
    log.info('Shout started (tray=%s, first_run=%s)', tray_mode, first_run)
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
