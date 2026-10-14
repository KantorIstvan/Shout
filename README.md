# Shout

Offline voice dictation for Windows, inspired by WisprFlow. Hold **Ctrl+Win**, speak Hungarian or English, release, and the text is pasted where the cursor is. Everything runs locally with Whisper large-v3; no audio leaves the machine.

| Keys | Action |
|---|---|
| Hold Ctrl+Win | Dictate (push-to-talk) |
| Ctrl+Win+Space | Hands-free mode; press Ctrl+Win again to stop |
| Esc | Cancel |

## Install

Download `Shout-<version>.zip` from the [Releases](https://github.com/KantorIstvan/Shout/releases) page, extract it, and double-click `Shout.exe`. It offers to install itself (default folder: `%LOCALAPPDATA%\Programs\Shout`, no admin rights needed), with a Start menu entry, optional autostart and desktop icon. It also adds an entry to Windows' Apps list, where you can uninstall it. **Csak most futtatom** runs it from the extracted folder without installing.

To update, extract the new ZIP and run its `Shout.exe`. It replaces the installed copy and keeps your settings, history and models.

On first launch Shout downloads:
- the Whisper model (about 3 GB)
- cuBLAS, only on NVIDIA GPUs (about 550 MB)

Without an NVIDIA GPU it falls back to `large-v3-turbo` on the CPU, which is slower but works.

Why a ZIP and not a setup.exe: an unsigned installer is blocked by Windows Smart App Control with no override. `Shout.exe` itself is signed (see below), so it can install itself even with Smart App Control on.

## Updates

Shout checks the GitHub Releases page on startup and twice a day. If a newer version exists, it shows a tray notification and a link in the sidebar. It never downloads or installs anything by itself: download the new ZIP from the Releases page, extract it and run its `Shout.exe`. Settings, history and models are kept. The check can be switched off in Settings (then the only network use is the first-run model download).

To release a new version: bump `version.py`, run `build.ps1`, commit, tag `vX.Y.Z`, push, and attach `Shout-X.Y.Z.zip` to a GitHub Release for that tag.

## Develop

```powershell
python -m venv .venv
.venv\Scripts\pip install --no-deps -r requirements.txt pytest
.venv\Scripts\python -m pytest test_shout.py   # hotkey state machine, language pick, hallucination filter
.venv\Scripts\python shout.py                  # run from source
powershell -ExecutionPolicy Bypass -File build.ps1   # dist\Shout + Shout-<version>.zip
```

| File | Role |
|---|---|
| `engine.py` | Microphone capture, Whisper (faster-whisper / CTranslate2), first-run cuBLAS download |
| `keys.py` | Ctrl+Win state machine, low-level keyboard hook, Ctrl+V injection |
| `ui.py` | Overlay pill, main window, theme |
| `shout.py` | Wiring, tray icon, settings and history storage |
| `installer.py` | Self-install, update and uninstall of the packaged `Shout.exe` |
| `make_icon.py` | Regenerates `assets/shout.ico` |

## Why there is no PyInstaller

Smart App Control blocks unsigned executables with no override. A PyInstaller bootloader is unsigned, so `Shout.exe` is python.org's Authenticode-signed `pythonw.exe`, renamed (the signature stays valid). The app runs from plain `.py` files via `shout_boot.pth`.

For the same reason PyAV is excluded: its DLLs get blocked, and Shout never decodes audio files.

## Data

- Settings and history: `%APPDATA%\Shout`
- Models, cuBLAS and log: `%LOCALAPPDATA%\Shout`
- Audio is never written to disk.

## License

MIT, see [LICENSE](LICENSE).

Third-party components:
- [Geist](https://vercel.com/font) font (OFL)
- [Phosphor](https://phosphoricons.com) icons (MIT); both license files are in `assets/`
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) and the OpenAI Whisper weights (MIT)
- [PySide6 / Qt](https://www.qt.io/qt-for-python) (LGPL-3.0, dynamically linked)
