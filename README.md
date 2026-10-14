# Shout

Offline voice dictation for Windows, inspired by WisprFlow. Hold **Ctrl+Win**, speak Hungarian or English, release, and the text is pasted where the cursor is. Everything runs locally with Whisper large-v3; no audio leaves the machine.

| Keys | Action |
|---|---|
| Hold Ctrl+Win | Dictate (push-to-talk) |
| Ctrl+Win+Space | Hands-free mode; press Ctrl+Win again to stop |
| Esc | Cancel |

## Install

Run `ShoutSetup.exe` (project root). By default it installs for the current user only, with no admin rights, to `%LOCALAPPDATA%\Programs\Shout`; the wizard can also install for all users or into another folder.

On first launch Shout downloads:
- the Whisper model (about 3 GB)
- cuBLAS, only on NVIDIA GPUs (about 550 MB)

Without an NVIDIA GPU it falls back to `large-v3-turbo` on the CPU, which is slower but works.

The installer is not code-signed, so SmartScreen shows "Windows protected your PC". Click **More info → Run anyway**.

## Develop

```powershell
python -m venv .venv
.venv\Scripts\pip install --no-deps -r requirements.txt pytest
.venv\Scripts\python -m pytest test_shout.py   # hotkey state machine, language pick, hallucination filter
.venv\Scripts\python shout.py                  # run from source
powershell -ExecutionPolicy Bypass -File build.ps1   # dist\Shout + ShoutSetup.exe (needs Inno Setup 6)
```

| File | Role |
|---|---|
| `engine.py` | Microphone capture, Whisper (faster-whisper / CTranslate2), first-run cuBLAS download |
| `keys.py` | Ctrl+Win state machine, low-level keyboard hook, Ctrl+V injection |
| `ui.py` | Overlay pill, main window, theme |
| `shout.py` | Wiring, tray icon, settings and history storage |
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
