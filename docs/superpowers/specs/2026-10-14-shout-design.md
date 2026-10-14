# Shout — design

Local, offline voice dictation for Windows, inspired by WisprFlow. Hold a hotkey, speak Hungarian or English, release, and the text is pasted into whatever app has focus.

## Behaviour

| Input | Action |
|---|---|
| Hold Ctrl+Win | Record while held; transcribe and paste on release |
| Ctrl+Win+Space | Hands-free toggle: start, then stop and paste |
| Esc while recording | Cancel and discard |
| Any other key while holding Ctrl+Win | Cancel, so OS shortcuts like Ctrl+Win+Arrow still work |
| Hold < 0.3 s | Ignored |

- On activation, a dummy key (VK 0xE8, unassigned) is injected so releasing Win does not open the Start menu.
- Paste waits until Win, Ctrl, Alt and Shift are physically released, so Win+V and similar shortcuts never fire.

## ASR

- faster-whisper (CTranslate2).
  - With an NVIDIA GPU: `large-v3`, `float16` on CUDA.
  - Without one: `large-v3-turbo`, `int8` on the CPU.
  - The model can be overridden in settings.
- Language mode `auto` scores all languages with Whisper and picks the higher of `hu` and `en`. A fixed `hu` or `en` mode is also available.
- VAD filter is on, `condition_on_previous_text=False`, beam size 5.
- Dictionary words from settings are passed as `initial_prompt`, as one comma-separated sentence ending in a period. Passing them as `hotwords` made output start lowercase.
- Output post-filter: trim whitespace and drop known silence hallucinations (e.g. "Feliratozta…", "Köszönöm, hogy megnézted", "Thank you for watching"). If nothing is left, nothing is pasted.

## Runtime dependencies on first launch

- Model weights: downloaded from Hugging Face into `%LOCALAPPDATA%\Shout\models`.
- CUDA runtime: cuBLAS 12 only, and only when CTranslate2 reports a CUDA device. The pinned NVIDIA PyPI wheel is SHA-256 verified; only `cublas64_12.dll` and `cublasLt64_12.dll` are extracted into `%LOCALAPPDATA%\Shout\cuda`. If the GPU path fails, Shout falls back to the CPU.

## UI (PySide6)

- **Pill:** bottom-centre, frameless, translucent, topmost, does not take focus (`WS_EX_NOACTIVATE`) and passes clicks through. Shows a live level waveform while recording, animated dots while transcribing and a short error flash.
- **Tray icon:** Open, Copy last, Quit. The tooltip shows status (loading model / ready / error).
- **Main window:**
  - History tab: newest first; click an item to copy it.
  - Settings tab: language mode, model, microphone, dictionary, start with Windows.

## Data

`%APPDATA%\Shout\settings.json` and `%APPDATA%\Shout\history.jsonl` (text only, no audio).

## Packaging

Revised during implementation, because Smart App Control is enforced on the target machine.

- No PyInstaller: its bootloader is an unsigned exe that Smart App Control blocks with no override. Instead, `Shout.exe` is python.org's PSF-signed `pythonw.exe`, renamed, from the official embeddable runtime. The app ships as `.py` files and starts via `Lib/site-packages/shout_boot.pth`. Autostart uses `Shout.exe -X tray`.
- PyAV is excluded (its DLL is blocked; the app never decodes files).
- onnxruntime dev tools are pruned (they exceed MAX_PATH).
- Only cuBLAS is downloaded on first run. cuDNN turned out to be unused by CTranslate2 Whisper (verified by in-process module enumeration).
- Icon: off-black rounded square with white waveform bars (3 bars at 16 to 24 px, 5 bars from 32 px), pixel-snapped up to 48 px, faint light edge for dark taskbars.
- Distribution is `Shout-<version>.zip` (about 106 MB). Inno Setup was dropped in 1.1.1: Smart App Control started blocking the unsigned setup.exe (the 1.0 build had been allowed). Started from an extracted folder, `Shout.exe` shows an install/update dialog (`installer.py`): folder picker, autostart, desktop icon. It copies itself, creates shortcuts, adds an HKCU Apps entry, and registers `Shout.exe -X uninstall` as the uninstaller (which deletes its own folder after exit via cmd). Verified with Mark-of-the-Web on every extracted file: no Smart App Control blocks.

## Out of scope (MVP)

LLM cleanup (Ollama later), app-context-aware formatting, snippets, streaming partial results, macOS, auto-update, code signing.

## Testing

- `test_shout.py`: hotkey state machine, hu/en language pick, hallucination filter.
- Manual end-to-end test: dictate Hungarian and English into Notepad from the built exe and from the installed app.
