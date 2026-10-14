"""Shout engine: CUDA runtime, microphone capture, Whisper transcription."""
import hashlib
import logging
import os
import re
import sys
import threading
import types
import urllib.request
import zipfile

import numpy as np

# faster_whisper imports PyAV only for decoding audio files. We hand it numpy arrays, and
# Smart App Control blocks PyAV's DLLs, so a stub module keeps the import working.
sys.modules.setdefault('av', types.ModuleType('av'))
os.environ.setdefault('HF_HUB_DISABLE_PROGRESS_BARS', '1')  # tqdm crashes under pythonw (no stderr)
os.environ.setdefault('HF_HUB_DISABLE_TELEMETRY', '1')

log = logging.getLogger('shout')

DATA_DIR = os.path.join(os.environ['LOCALAPPDATA'], 'Shout')
CUDA_DIR = os.path.join(DATA_DIR, 'cuda')
MODELS_DIR = os.path.join(DATA_DIR, 'models')
SR = 16000

# CTranslate2 needs only cuBLAS for Whisper (verified: no cuDNN sub-library gets loaded).
CUBLAS_URL = ('https://files.pythonhosted.org/packages/20/e2/fc9a0e985249d873150276d5afb02e39a66817fe'
              'dbf1a385724393e505ed/nvidia_cublas_cu12-12.9.2.10-py3-none-win_amd64.whl')
CUBLAS_SHA256 = '623f43027d40d44ceadf0043f002bd25cf353e8f13ce90b9a87057019f560661'
CUBLAS_DLLS = ('cublas64_12.dll', 'cublasLt64_12.dll')

# Approximate download sizes, only used to draw a progress bar.
MODEL_REPOS = {
    'large-v3': ('Systran/faster-whisper-large-v3', 3.09e9),
    'large-v3-turbo': ('mobiuslabsgmbh/faster-whisper-large-v3-turbo', 1.62e9),
    'medium': ('Systran/faster-whisper-medium', 1.53e9),
}

# Whisper's classic silence hallucinations (subtitle credits it learned from YouTube).
_HALLUCINATION = re.compile(
    r'^\W*(feliratozta|feliratok?\b|a feliratot készítette|köszönöm,? hogy (meg)?néz|'
    r'köszönjük,? hogy (meg)?néz|thanks? (you )?for watching|subtitles? by|amara\.org)', re.I)


def pick_language(probs):
    """Choose between Hungarian and English only; a short 'Igen' must never become Finnish."""
    p = dict(probs)
    return 'en' if p.get('en', 0) > p.get('hu', 0) else 'hu'


def clean_text(text):
    text = ' '.join(text.split())
    if not re.search(r'\w', text) or _HALLUCINATION.search(text):
        return ''
    return text


def _download(url, dest, sha256, progress):
    h = hashlib.sha256()
    part = dest + '.part'
    with urllib.request.urlopen(url, timeout=60) as r, open(part, 'wb') as f:
        total, done = int(r.headers.get('Content-Length', 0)), 0
        while chunk := r.read(1 << 20):
            f.write(chunk)
            h.update(chunk)
            done += len(chunk)
            if total:
                progress('GPU-gyorsítás letöltése', done / total)
    if h.hexdigest() != sha256:
        os.remove(part)
        raise RuntimeError('cuBLAS download checksum mismatch')
    os.replace(part, dest)


def ensure_cuda(progress=lambda msg, frac: None):
    """True if an NVIDIA GPU is usable. Fetches cuBLAS on first run (~550 MB)."""
    import ctranslate2
    if ctranslate2.get_cuda_device_count() == 0:
        return False
    os.makedirs(CUDA_DIR, exist_ok=True)
    if not all(os.path.exists(os.path.join(CUDA_DIR, d)) for d in CUBLAS_DLLS):
        wheel = os.path.join(CUDA_DIR, 'cublas.whl')
        _download(CUBLAS_URL, wheel, CUBLAS_SHA256, progress)
        progress('GPU-gyorsítás kicsomagolása', None)
        with zipfile.ZipFile(wheel) as z:
            for name in CUBLAS_DLLS:
                with z.open(f'nvidia/cublas/bin/{name}') as src, open(os.path.join(CUDA_DIR, name + '.part'), 'wb') as dst:
                    while chunk := src.read(1 << 20):
                        dst.write(chunk)
                os.replace(os.path.join(CUDA_DIR, name + '.part'), os.path.join(CUDA_DIR, name))
        os.remove(wheel)
    os.add_dll_directory(CUDA_DIR)
    os.environ['PATH'] = CUDA_DIR + os.pathsep + os.environ['PATH']  # cuBLAS is delay-loaded via PATH
    return True


def _dir_size(path):
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


class Transcriber:
    def __init__(self, model='auto', progress=None):
        self.requested = model
        self.progress = progress or (lambda msg, frac: None)
        self.model = None
        self.model_name = ''
        self.device = ''

    def load(self):
        from faster_whisper import WhisperModel
        try:
            cuda = ensure_cuda(self.progress)
        except Exception:
            log.exception('CUDA setup failed, using CPU')
            cuda = False
        attempts = [('cuda', 'float16')] if cuda else []
        attempts.append(('cpu', 'int8'))
        for device, compute in attempts:
            name = self.requested if self.requested != 'auto' else ('large-v3' if device == 'cuda' else 'large-v3-turbo')
            try:
                self.model = self._open(WhisperModel, name, device, compute)
                self.model_name, self.device = name, device
                break
            except Exception:
                log.exception('Loading %s on %s failed', name, device)
        if self.model is None:
            raise RuntimeError('No Whisper model could be loaded')
        # First CUDA call JIT-compiles kernels (about 30 s once on new GPUs); pay it now, not on the first dictation.
        self.progress('Bemelegítés', None)
        self.model.detect_language(np.random.default_rng(0).normal(0, 0.05, SR).astype(np.float32))
        log.info('Model ready: %s on %s', self.model_name, self.device)

    def _open(self, WhisperModel, name, device, compute):
        try:
            return WhisperModel(name, device=device, compute_type=compute, download_root=MODELS_DIR, local_files_only=True)
        except Exception:
            pass  # not downloaded yet
        repo, size = MODEL_REPOS.get(name, (None, 0))
        stop = threading.Event()
        if repo and size:
            folder = os.path.join(MODELS_DIR, 'models--' + repo.replace('/', '--'))

            def watch():
                while not stop.wait(0.5):
                    self.progress('Modell letöltése', min(_dir_size(folder) / size, 1.0))
            threading.Thread(target=watch, daemon=True).start()
        else:
            self.progress('Modell letöltése', None)
        try:
            return WhisperModel(name, device=device, compute_type=compute, download_root=MODELS_DIR)
        finally:
            stop.set()

    def transcribe(self, audio, language='auto', hotwords=''):
        if len(audio) < SR * 0.3:
            return '', language
        if language == 'auto':
            try:
                _, _, probs = self.model.detect_language(audio, vad_filter=True)
                language = pick_language(probs)
            except Exception:
                log.exception('Language detection failed, assuming Hungarian')
                language = 'hu'
        # Dictionary terms go in as a finished sentence, so the dictation still starts with a capital letter.
        prompt = ', '.join(w.strip() for w in hotwords.splitlines() if w.strip())
        segments, _ = self.model.transcribe(
            audio, language=language, beam_size=5, vad_filter=True, condition_on_previous_text=False,
            without_timestamps=True, initial_prompt=prompt + '.' if prompt else None)
        return ' '.join(s.text.strip() for s in segments), language


class Recorder:
    """16 kHz mono capture into memory. on_level gets the RMS of every 50 ms block (audio thread)."""

    def __init__(self, on_level=None):
        self.on_level = on_level
        self.stream = None
        self.chunks = []

    @staticmethod
    def refresh():
        """PortAudio only enumerates devices at init; call after a device change while idle."""
        import sounddevice as sd
        sd._terminate()
        sd._initialize()

    @staticmethod
    def input_devices():
        import sounddevice as sd
        mme = next((i for i, a in enumerate(sd.query_hostapis()) if a['name'] == 'MME'), 0)
        seen, out = set(), []
        for i, d in enumerate(sd.query_devices()):
            if d['hostapi'] == mme and d['max_input_channels'] > 0 and d['name'] not in seen \
                    and 'Sound Mapper' not in d['name']:
                seen.add(d['name'])
                out.append((i, d['name']))
        return out

    def start(self, device_name=None):
        import sounddevice as sd
        device = None
        if device_name:
            device = next((i for i, n in self.input_devices() if n == device_name), None)
        if device is None and not self.input_devices():
            self.refresh()  # a headset may have been switched on since startup
            if not self.input_devices():
                raise RuntimeError('no input device')
        self.chunks = []
        self.stream = sd.InputStream(samplerate=SR, channels=1, dtype='float32', device=device,
                                     blocksize=SR // 20, callback=self._callback)
        self.stream.start()

    def _callback(self, indata, frames, t, status):
        self.chunks.append(indata[:, 0].copy())
        if self.on_level:
            self.on_level(float(np.sqrt(np.mean(indata ** 2))))

    def stop(self):
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        audio = np.concatenate(self.chunks) if self.chunks else np.zeros(0, np.float32)
        self.chunks = []
        return audio

    @property
    def active(self):
        return self.stream is not None
