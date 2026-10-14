"""Self-install, update and uninstall for the packaged Shout.exe.

Shout ships as a ZIP instead of a setup.exe: an unsigned installer gets blocked by Smart App Control, while
Shout.exe (python.org's signed pythonw.exe) is allowed. Run from the extracted folder, Shout copies itself to
the install folder, adds shortcuts and an "Apps & features" entry whose uninstall runs `Shout.exe -X uninstall`.
"""
import ctypes
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
import winreg

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtNetwork import QLocalSocket
from PySide6.QtWidgets import (QCheckBox, QDialog, QFileDialog, QHBoxLayout, QLineEdit, QProgressBar, QPushButton,
                               QVBoxLayout)

import ui
from version import __version__

log = logging.getLogger('shout')

UNINSTALL_KEY = r'Software\Microsoft\Windows\CurrentVersion\Uninstall\Shout'
INNO_KEY = r'Software\Microsoft\Windows\CurrentVersion\Uninstall\{8C5E2A57-4B1D-4E8B-9F0A-5D3C2B7E1A64}_is1'  # 1.0
RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
DEFAULT_DIR = os.path.join(os.environ['LOCALAPPDATA'], 'Programs', 'Shout')
NO_WINDOW = 0x08000000
DETACHED = 0x00000008


def packaged():
    return os.path.basename(sys.executable).lower() == 'shout.exe'


def app_dir():
    return os.path.dirname(os.path.abspath(sys.executable))


def _reg_value(key, name):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
            return winreg.QueryValueEx(k, name)[0]
    except OSError:
        return None


def installed_location():
    loc = _reg_value(UNINSTALL_KEY, 'InstallLocation') or _reg_value(INNO_KEY, 'InstallLocation')
    return os.path.abspath(loc) if loc else None


def installed_version():
    return _reg_value(UNINSTALL_KEY, 'DisplayVersion') or _reg_value(INNO_KEY, 'DisplayVersion')


def same_path(a, b):
    return bool(a and b) and os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def needs_install():
    return not same_path(app_dir(), installed_location())


def resolve_target(path):
    """Never spill files into a folder that holds other things: use a Shout subfolder instead."""
    path = os.path.abspath(path)
    if os.path.isdir(path) and os.listdir(path) and not os.path.exists(os.path.join(path, 'Shout.exe')):
        path = os.path.join(path, 'Shout')
    return path


def _powershell(script):
    subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', script],
                   creationflags=NO_WINDOW, check=False, timeout=30)


def _ps_quote(s):
    return "'" + s.replace("'", "''") + "'"


def _shortcut_paths():
    """Start menu entry always; desktop path resolved by Windows (it may be redirected to OneDrive)."""
    start = os.path.join(os.environ['APPDATA'], r'Microsoft\Windows\Start Menu\Programs\Shout.lnk')
    buf = ctypes.create_unicode_buffer(260)
    ctypes.windll.shell32.SHGetFolderPathW(None, 0x0010, None, 0, buf)  # CSIDL_DESKTOPDIRECTORY
    return start, os.path.join(buf.value, 'Shout.lnk')


def _create_shortcut(lnk, target):
    exe = os.path.join(target, 'Shout.exe')
    _powershell(f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut({_ps_quote(lnk)}); "
                f"$s.TargetPath = {_ps_quote(exe)}; $s.WorkingDirectory = {_ps_quote(target)}; "
                f"$s.IconLocation = {_ps_quote(os.path.join(target, 'app', 'assets', 'shout.ico'))}; $s.Save()")


def stop_running_instance(timeout=10.0):
    """Ask a running Shout to quit (via its local socket) and wait until its mutex is gone."""
    from shout import MUTEX_NAME, PIPE_NAME
    sock = QLocalSocket()
    sock.connectToServer(PIPE_NAME)
    if sock.waitForConnected(300):
        sock.write(b'quit')
        sock.waitForBytesWritten(300)
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        h = ctypes.windll.kernel32.OpenMutexW(0x00100000, False, MUTEX_NAME)  # SYNCHRONIZE
        if not h:
            return True
        ctypes.windll.kernel32.CloseHandle(h)
        time.sleep(0.2)
    return False


def strip_motw(path):
    """Remove the 'downloaded from the internet' stream. Explorer copies it onto every file extracted from a downloaded
    ZIP, and Smart App Control then blocks shortcuts made from those files (e.g. a taskbar pin)."""
    try:
        os.remove(path + ':Zone.Identifier')
    except OSError:
        pass


def install(target, autostart, desktop, progress):
    """Copy this folder to target (unless it already is the target), then register shortcuts, autostart and the
    uninstall entry. Returns True if the installed copy was started and this process should exit."""
    src = app_dir()
    in_place = same_path(src, target)
    files = [os.path.join(r, f) for r, _, fs in os.walk(src) for f in fs]
    if not in_place:
        if not stop_running_instance():
            raise RuntimeError('A futó Shout nem zárult be. Lépj ki belőle a tálcán, és próbáld újra.')
        if os.path.exists(os.path.join(target, 'Shout.exe')):
            shutil.rmtree(target)  # an older Shout: replace it completely so no stale files remain
        for i, f in enumerate(files):
            dst = os.path.join(target, os.path.relpath(f, src))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(f, dst)
            if i % 50 == 0:
                progress(i / len(files))
    for f in files:  # copy2 keeps the ZIP's Mark-of-the-Web; installed files must not have it (see strip_motw)
        strip_motw(os.path.join(target, os.path.relpath(f, src)))
    progress(1.0)

    start, desk = _shortcut_paths()
    _create_shortcut(start, target)
    if desktop:
        _create_shortcut(desk, target)
    exe = os.path.join(target, 'Shout.exe')
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
        if autostart:
            winreg.SetValueEx(k, 'Shout', 0, winreg.REG_SZ, f'"{exe}" -X tray')
        else:
            try:
                winreg.DeleteValue(k, 'Shout')
            except OSError:
                pass
    size_kb = sum(os.path.getsize(f) for f in files) // 1024
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as k:
        for name, value in (('DisplayName', 'Shout'), ('DisplayVersion', __version__), ('Publisher', 'Kantor Istvan'),
                            ('DisplayIcon', os.path.join(target, 'app', 'assets', 'shout.ico')),
                            ('InstallLocation', target), ('UninstallString', f'"{exe}" -X uninstall')):
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)
        for name, value in (('NoModify', 1), ('NoRepair', 1), ('EstimatedSize', size_kb)):
            winreg.SetValueEx(k, name, 0, winreg.REG_DWORD, value)
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, INNO_KEY)  # 1.0 was installed with Inno Setup
    except OSError:
        pass
    if in_place:
        return False
    subprocess.Popen([exe], cwd=target, creationflags=DETACHED)
    return True


class InstallDialog(QDialog):
    done = Signal(object, bool)  # error message or None, and whether the installed copy was started
    progressed = Signal(float)

    def __init__(self):
        super().__init__()
        self.result_action = 'cancel'
        self.setWindowTitle('Shout')
        self.setWindowIcon(QIcon(os.path.join(ui.ASSETS, 'shout.ico')))
        self.setObjectName('page')
        self.setFixedWidth(520)
        old = installed_version()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 22)
        lay.setSpacing(0)
        lay.addWidget(ui.label(f'Shout frissítése: {old} → {__version__}' if old else 'Shout telepítése', 'h2'))
        lay.addSpacing(6)
        lay.addWidget(ui.label('A Shout a választott mappába másolja magát, és a Start menüből indítható lesz. '
                               'A beállításaid, az előzmények és a modell megmaradnak.', 'muted', wrap=True))
        lay.addSpacing(18)
        lay.addWidget(ui.label('Telepítési mappa', 'label'))
        lay.addSpacing(6)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.folder = QLineEdit(installed_location() or DEFAULT_DIR)
        self.folder.setReadOnly(True)
        browse = QPushButton('Tallózás')
        browse.setObjectName('secondary')
        browse.setCursor(Qt.CursorShape.PointingHandCursor)
        browse.clicked.connect(self.browse)
        row.addWidget(self.folder, 1)
        row.addWidget(browse)
        lay.addLayout(row)
        lay.addSpacing(16)
        self.autostart = QCheckBox('Indítás a Windows-zal')
        self.autostart.setChecked(not old or bool(_reg_value(RUN_KEY, 'Shout')))
        self.desktop = QCheckBox('Parancsikon az asztalon')
        lay.addWidget(self.autostart)
        lay.addSpacing(6)
        lay.addWidget(self.desktop)
        lay.addSpacing(18)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 1000)
        self.progress.hide()
        lay.addWidget(self.progress)
        self.error = ui.label('', 'help', wrap=True)
        self.error.hide()
        lay.addWidget(self.error)
        lay.addSpacing(10)
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addStretch()
        self.portable = QPushButton('Csak most futtatom')
        self.portable.setObjectName('secondary')
        self.portable.setCursor(Qt.CursorShape.PointingHandCursor)
        self.portable.clicked.connect(self.run_portable)
        self.go = QPushButton('Frissítés' if old else 'Telepítés')
        self.go.setObjectName('primary')
        self.go.setCursor(Qt.CursorShape.PointingHandCursor)
        self.go.setDefault(True)
        self.go.clicked.connect(self.start)
        buttons.addWidget(self.portable)
        buttons.addWidget(self.go)
        lay.addLayout(buttons)
        self.done.connect(self.finished_install)
        self.progressed.connect(lambda f: self.progress.setValue(int(f * 1000)))

    def showEvent(self, e):
        ui.set_dark_titlebar(self, ui.is_dark())
        super().showEvent(e)

    def browse(self):
        path = QFileDialog.getExistingDirectory(self, 'Telepítési mappa', self.folder.text())
        if path:
            self.folder.setText(resolve_target(path))

    def run_portable(self):
        self.result_action = 'portable'
        self.accept()

    def start(self):
        target = resolve_target(self.folder.text())
        for w in (self.go, self.portable, self.autostart, self.desktop):
            w.setEnabled(False)
        self.error.hide()
        self.progress.show()

        def work():
            try:
                started = install(target, self.autostart.isChecked(), self.desktop.isChecked(), self.progressed.emit)
                self.done.emit(None, started)
            except PermissionError:
                self.done.emit('Ebbe a mappába nincs írási jogod. Válassz egy másikat, például a felajánlott '
                               'alapmappát.', False)
            except Exception as exc:
                log.exception('install failed')
                self.done.emit(str(exc) or exc.__class__.__name__, False)
        threading.Thread(target=work, daemon=True).start()

    def finished_install(self, error, started):
        if error is None:
            self.result_action = 'installed' if started else 'portable'  # in place: keep running this copy
            self.accept()
            return
        self.progress.hide()
        self.error.setText(error)
        self.error.show()
        for w in (self.go, self.portable, self.autostart, self.desktop):
            w.setEnabled(True)


def run_install_dialog():
    """'installed' (the installed copy was started, exit now), 'portable' (keep running from here) or 'cancel'."""
    dialog = InstallDialog()
    dialog.exec()
    return dialog.result_action


class UninstallDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Shout')
        self.setWindowIcon(QIcon(os.path.join(ui.ASSETS, 'shout.ico')))
        self.setObjectName('page')
        self.setFixedWidth(460)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 22)
        lay.setSpacing(0)
        lay.addWidget(ui.label('Shout eltávolítása', 'h2'))
        lay.addSpacing(6)
        lay.addWidget(ui.label('A program, a parancsikonok és az automatikus indítás törlődik.', 'muted', wrap=True))
        lay.addSpacing(16)
        self.wipe = QCheckBox('Az adataim törlése is')
        lay.addWidget(self.wipe)
        lay.addSpacing(4)
        detail = ui.label('Letöltött modellek (kb. 3,5 GB), előzmények, szótár és beállítások.', 'help', wrap=True)
        detail.setContentsMargins(26, 0, 0, 0)
        lay.addWidget(detail)
        lay.addSpacing(20)
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addStretch()
        cancel = QPushButton('Mégse')
        cancel.setObjectName('secondary')
        cancel.clicked.connect(self.reject)
        go = QPushButton('Eltávolítás')
        go.setObjectName('primary')
        go.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(go)
        lay.addLayout(buttons)

    def showEvent(self, e):
        ui.set_dark_titlebar(self, ui.is_dark())
        super().showEvent(e)


def uninstall():
    dialog = UninstallDialog()
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return 0
    stop_running_instance()
    target = app_dir()
    for lnk in _shortcut_paths():
        if os.path.exists(lnk):
            os.remove(lnk)
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, 'Shout')
    except OSError:
        pass
    for key in (UNINSTALL_KEY, INNO_KEY):
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key)
        except OSError:
            pass
    if dialog.wipe.isChecked():
        for d in (os.path.join(os.environ['LOCALAPPDATA'], 'Shout'), os.path.join(os.environ['APPDATA'], 'Shout')):
            shutil.rmtree(d, ignore_errors=True)
    if os.path.exists(os.path.join(target, 'Shout.exe')):  # only ever delete a Shout folder
        # this process still holds files in the folder: cmd deletes it a few seconds after we exit
        subprocess.Popen(f'cmd /c ping -n 4 127.0.0.1 >nul & rmdir /s /q "{target}"',
                         creationflags=NO_WINDOW | DETACHED, cwd=os.environ['TEMP'])
    return 0
