"""Shout UI: theme, overlay pill, main window (history and settings)."""
import ctypes
import ctypes.wintypes
import math
import os
import time
from datetime import datetime

from PySide6.QtCore import (QByteArray, QEasingCurve, QPropertyAnimation, QRectF, QSize, Qt, QTimer,
                            QVariantAnimation, Signal)
from PySide6.QtGui import (QColor, QCursor, QFont, QFontDatabase, QGuiApplication, QIcon, QPainter, QPalette,
                           QPixmap)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (QAbstractButton, QButtonGroup, QComboBox, QFrame, QHBoxLayout, QLabel,
                               QMainWindow, QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QSizePolicy,
                               QStackedWidget, QVBoxLayout, QWidget)

from version import __version__

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets')

# Monochrome tokens. Radius system: containers 12px, controls 8px, switch and overlay pill fully round.
LIGHT = dict(bg='#F4F4F5', side='#EBEBED', surface='#FAFAFA', hover='#E4E4E7', border='#DCDCE0',
             text='#18181B', muted='#5F5F67', faint='#A1A1AA')
DARK = dict(bg='#0E0E10', side='#131315', surface='#1A1A1D', hover='#222226', border='#2A2A2E',
            text='#F4F4F5', muted='#A1A1AA', faint='#52525B')
INK, PAPER = QColor('#0B0B0C'), QColor('#FAFAFA')
MONTHS = ('január', 'február', 'március', 'április', 'május', 'június', 'július', 'augusztus',
          'szeptember', 'október', 'november', 'december')


def load_fonts():
    for f in os.listdir(os.path.join(ASSETS, 'fonts')):
        if f.endswith('.ttf'):
            QFontDatabase.addApplicationFont(os.path.join(ASSETS, 'fonts', f))
    font = QFont('Geist')
    font.setPixelSize(13)
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    QGuiApplication.setFont(font)


def animations_enabled():
    """Honour Windows' 'Animation effects' setting (the desktop equivalent of prefers-reduced-motion)."""
    flag = ctypes.c_int(1)
    ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(flag), 0)  # SPI_GETCLIENTAREAANIMATION
    return bool(flag.value)


def svg_pixmap(name, color, size, dpr=2.0):
    with open(os.path.join(ASSETS, 'icons', name + '.svg'), encoding='utf-8') as f:
        svg = f.read().replace('currentColor', color)
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    QSvgRenderer(QByteArray(svg.encode())).render(p)
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def is_dark():
    return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark


def tokens():
    return DARK if is_dark() else LIGHT


def stylesheet(t, caret_path):
    return f"""
    QWidget {{ color: {t['text']}; font-family: "Geist"; font-size: 13px; }}
    QMainWindow, #content, #page, QScrollArea, QScrollArea > QWidget > QWidget {{ background: {t['bg']}; }}
    QScrollArea {{ border: none; }}
    #sidebar {{ background: {t['side']}; border-right: 1px solid {t['border']}; }}
    #brand {{ font-size: 15px; font-weight: 600; letter-spacing: -0.2px; }}
    QPushButton#nav {{ text-align: left; padding: 8px 10px; border: 1px solid transparent; border-radius: 8px;
        color: {t['muted']}; background: transparent; font-weight: 500; }}
    QPushButton#nav:hover {{ background: {t['hover']}; color: {t['text']}; }}
    QPushButton#nav:checked {{ background: {t['surface']}; color: {t['text']}; border-color: {t['border']}; }}
    #updateLink {{ font-weight: 500; }}
    #h1 {{ font-size: 22px; font-weight: 600; letter-spacing: -0.4px; }}
    #h2 {{ font-size: 15px; font-weight: 600; letter-spacing: -0.2px; }}
    #label {{ font-weight: 500; }}
    #muted, #help, #status, #day {{ color: {t['muted']}; }}
    #help {{ font-size: 12px; }}
    #day {{ font-size: 12px; font-weight: 500; padding: 14px 0 2px 10px; }}
    #time {{ color: {t['muted']}; font-family: "Geist Mono"; font-size: 12px; }}
    #model {{ font-family: "Geist Mono"; font-size: 12px; }}
    #keycap, #keycapLarge {{ font-family: "Geist Mono"; font-weight: 500; background: {t['surface']};
        border: 1px solid {t['border']}; border-bottom: 2px solid {t['border']}; border-radius: 8px; }}
    #keycap {{ font-size: 12px; padding: 2px 8px; }}
    #keycapLarge {{ font-size: 15px; padding: 8px 16px; }}
    #row {{ border-radius: 8px; background: transparent; }}
    #row[hover="true"] {{ background: {t['surface']}; }}
    #copied {{ color: {t['muted']}; font-size: 12px; }}
    #segment {{ background: {t['side']}; border: 1px solid {t['border']}; border-radius: 8px; }}
    QPushButton#seg {{ border: none; border-radius: 6px; padding: 6px 14px; color: {t['muted']};
        background: transparent; font-weight: 500; }}
    QPushButton#seg:hover {{ color: {t['text']}; }}
    QPushButton#seg:checked {{ background: {t['surface']}; color: {t['text']}; }}
    QComboBox {{ background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 8px;
        padding: 6px 10px; min-width: 280px; }}
    QComboBox:hover {{ border-color: {t['faint']}; }}
    QComboBox:focus {{ border-color: {t['text']}; }}
    QComboBox::drop-down {{ border: none; width: 30px; }}
    QComboBox::down-arrow {{ image: url("{caret_path}"); width: 12px; height: 12px; }}
    QComboBox QAbstractItemView {{ background: {t['surface']}; border: 1px solid {t['border']};
        selection-background-color: {t['hover']}; selection-color: {t['text']}; outline: none; padding: 4px; }}
    QPlainTextEdit {{ background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 8px;
        padding: 6px 8px; }}
    QPlainTextEdit:focus {{ border-color: {t['text']}; }}
    QProgressBar {{ background: {t['border']}; border: none; border-radius: 1px; max-height: 2px; }}
    QProgressBar::chunk {{ background: {t['text']}; border-radius: 1px; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {t['border']}; border-radius: 3px; min-height: 30px; }}
    QScrollBar::handle:vertical:hover {{ background: {t['faint']}; }}
    QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ height: 0; background: none; }}
    QMenu {{ background: {t['surface']}; border: 1px solid {t['border']}; padding: 4px; }}
    QMenu::item {{ padding: 6px 18px 6px 12px; border-radius: 6px; }}
    QMenu::item:selected {{ background: {t['hover']}; }}
    QMenu::separator {{ height: 1px; background: {t['border']}; margin: 4px 6px; }}
    """


def apply_theme(app, cache_dir):
    t = tokens()
    os.makedirs(cache_dir, exist_ok=True)
    caret = os.path.join(cache_dir, f"caret-{t['muted'][1:]}.svg")
    with open(os.path.join(ASSETS, 'icons', 'caret-down.svg'), encoding='utf-8') as f:
        svg = f.read().replace('currentColor', t['muted'])
    with open(caret, 'w', encoding='utf-8') as f:
        f.write(svg)
    pal = app.palette()
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(t['muted']))  # AA contrast, not the faint grey
    pal.setColor(QPalette.ColorRole.Link, QColor(t['text']))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(t['text']))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(t['bg']))
    app.setPalette(pal)
    app.setStyleSheet(stylesheet(t, caret.replace('\\', '/')))


def set_dark_titlebar(widget, dark):
    value = ctypes.c_int(1 if dark else 0)
    ctypes.windll.dwmapi.DwmSetWindowAttribute(int(widget.winId()), 20, ctypes.byref(value), 4)


def label(text, name=None, wrap=False):
    w = QLabel(text)
    if name:
        w.setObjectName(name)
    w.setWordWrap(wrap)
    return w


def keycap(text, large=False):
    return label(text, 'keycapLarge' if large else 'keycap')


def keys_row(*parts, spacing=6):
    """Inline row of keycaps and plain text: strings in [] become keycaps."""
    row = QHBoxLayout()
    row.setSpacing(spacing)
    row.setContentsMargins(0, 0, 0, 0)
    for p in parts:
        row.addWidget(keycap(p[1:-1]) if p.startswith('[') else label(p, 'muted'))
    row.addStretch()
    return row


class Switch(QAbstractButton):
    def __init__(self):
        super().__init__()
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(36, 20)

    def paintEvent(self, _):
        t = tokens()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(t['text'] if self.isChecked() else t['border']))
        p.drawRoundedRect(QRectF(0, 0, 36, 20), 10, 10)
        p.setBrush(QColor(t['bg']))
        p.drawEllipse(QRectF(19 if self.isChecked() else 3, 3, 14, 14))


# --------------------------------------------------------------------------- overlay pill

class Pill(QWidget):
    """Bottom-centre status pill. Never takes focus and lets clicks through."""

    W, H = 320, 72
    PILL_H = 36

    def __init__(self):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool | Qt.WindowType.WindowDoesNotAcceptFocus
                         | Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(self.W, self.H)
        self.mode = 'hidden'
        self.text = ''
        self.level = 0.0
        self.target_level = 0.0
        self.width_now = 120.0
        self.motion = animations_enabled()
        self.lock = svg_pixmap('lock-simple', '#FAFAFA', 13)
        self.frame = QTimer(self, interval=16, timeout=self._tick)
        self.fade = QPropertyAnimation(self, b'windowOpacity', self)
        self.fade.finished.connect(self._fade_done)
        self.widen = QVariantAnimation(self, duration=180, easingCurve=QEasingCurve.Type.OutCubic)
        self.widen.valueChanged.connect(self._set_width)
        self.hide_timer = QTimer(self, singleShot=True, timeout=self.hide_pill)
        self.font_msg = QFont('Geist')
        self.font_msg.setPixelSize(12)
        self.font_msg.setWeight(QFont.Weight.Medium)

    # public API -------------------------------------------------------------
    def show_recording(self):
        self._enter('recording', 124)

    def show_handsfree(self):
        self._enter('handsfree', 148)

    def show_working(self):
        self._enter('working', 76)

    def show_message(self, text, ms=1800):
        self.text = text
        from PySide6.QtGui import QFontMetrics
        self._enter('message', QFontMetrics(self.font_msg).horizontalAdvance(text) + 36)
        self.hide_timer.start(ms)

    def set_level(self, rms):
        self.target_level = min(1.0, (rms * 14) ** 0.6)

    def hide_pill(self):
        if self.mode == 'hidden':
            return
        self.mode = 'hidden'
        if self.motion:
            self.fade.stop()
            self.fade.setDuration(140)
            self.fade.setStartValue(self.windowOpacity())
            self.fade.setEndValue(0.0)
            self.fade.start()
        else:
            self._fade_done()

    # internals --------------------------------------------------------------
    def _enter(self, mode, width):
        self.hide_timer.stop()
        was_hidden = self.mode == 'hidden'
        self.mode = mode
        if was_hidden:
            self.width_now = width
            self._place()
            self.setWindowOpacity(0.0 if self.motion else 1.0)
            self.show()
            self._no_activate()
            if self.motion:
                self.fade.stop()
                self.fade.setDuration(120)
                self.fade.setStartValue(0.0)
                self.fade.setEndValue(1.0)
                self.fade.start()
        elif self.motion:
            self.widen.stop()
            self.widen.setStartValue(self.width_now)
            self.widen.setEndValue(float(width))
            self.widen.start()
        else:
            self.width_now = width
        self.frame.start()
        self.update()

    def _fade_done(self):
        if self.mode == 'hidden':
            self.hide()
            self.frame.stop()
            self.level = self.target_level = 0.0

    def _set_width(self, v):
        self.width_now = v
        self.update()

    def _place(self):
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        g = screen.availableGeometry()
        self.move(g.center().x() - self.W // 2, g.bottom() - self.H - 12)

    def _no_activate(self):
        hwnd = int(self.winId())
        u = ctypes.windll.user32
        u.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        u.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
        ex = u.GetWindowLongPtrW(hwnd, -20)
        u.SetWindowLongPtrW(hwnd, -20, ex | 0x08000000 | 0x80 | 0x20)  # NOACTIVATE | TOOLWINDOW | TRANSPARENT
        u.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)  # HWND_TOPMOST, no move/size/activate

    def _tick(self):
        self.level += (self.target_level - self.level) * 0.35
        self.target_level *= 0.9
        self.update()

    def paintEvent(self, _):
        if self.mode == 'hidden' and not self.isVisible():
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width_now, self.PILL_H
        r = QRectF((self.W - w) / 2, self.H - h - 8, w, h)
        p.setPen(QColor(255, 255, 255, 30))
        p.setBrush(QColor(11, 11, 12, 245))
        p.drawRoundedRect(r, h / 2, h / 2)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(PAPER)
        cx, cy = r.center().x(), r.center().y()
        t = time.monotonic()
        if self.mode in ('recording', 'handsfree'):
            if self.mode == 'handsfree':
                p.drawPixmap(int(r.left() + 14), int(cy - 6.5), self.lock)
                cx += 10
            env = (0.35, 0.55, 0.75, 0.9, 1.0, 0.9, 0.75, 0.55, 0.35)
            bw, gap = 3.0, 3.0
            x = cx - (len(env) * bw + (len(env) - 1) * gap) / 2
            for i, e in enumerate(env):
                wobble = 0.75 + 0.25 * math.sin(t * 9 + i * 0.9) if self.motion else 1.0
                bh = 4 + 16 * e * self.level * wobble
                p.drawRoundedRect(QRectF(x, cy - bh / 2, bw, bh), bw / 2, bw / 2)
                x += bw + gap
        elif self.mode == 'working':
            for i in range(3):
                a = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(t * 6 - i * 0.8)) if self.motion else 1.0
                c = QColor(PAPER)
                c.setAlphaF(a)
                p.setBrush(c)
                p.drawEllipse(QRectF(cx - 14 + i * 11, cy - 2.5, 5, 5))
        elif self.mode == 'message':
            p.setPen(PAPER)
            p.setFont(self.font_msg)
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, self.text)


# --------------------------------------------------------------------------- main window

class HistoryRow(QFrame):
    def __init__(self, item):
        super().__init__()
        self.setObjectName('row')
        self.text = item['text']
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip('Kattints a másoláshoz')
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(14)
        tm = label(datetime.fromisoformat(item['t']).strftime('%H:%M'), 'time')
        tm.setFixedWidth(40)
        tm.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        body = label(self.text, wrap=True)
        body.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.icon = QLabel()
        self.icon.setFixedSize(56, 16)
        self.icon.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        lay.addWidget(tm, 0, Qt.AlignmentFlag.AlignTop)
        lay.addWidget(body, 1)
        lay.addWidget(self.icon, 0, Qt.AlignmentFlag.AlignTop)
        self.reset = QTimer(self, singleShot=True, interval=1400, timeout=lambda: self._show_icon(self.underMouse()))

    def _show_icon(self, on):
        if on:
            self.icon.setPixmap(svg_pixmap('copy', tokens()['muted'], 16))
        else:
            self.icon.clear()

    def _set_hover(self, on):
        self.setProperty('hover', on)
        self.style().unpolish(self)
        self.style().polish(self)
        if not self.reset.isActive():
            self._show_icon(on)

    def enterEvent(self, e):
        self._set_hover(True)

    def leaveEvent(self, e):
        self._set_hover(False)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            QGuiApplication.clipboard().setText(self.text)
            self.icon.setText('Másolva')
            self.icon.setObjectName('copied')
            self.icon.setStyleSheet('')
            self.reset.start()


class HistoryPage(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName('page')
        self.items = []
        outer = QVBoxLayout(self)
        outer.setContentsMargins(36, 32, 36, 0)
        outer.setSpacing(0)
        outer.addWidget(label('Előzmények', 'h1'))
        self.hint = QWidget()
        hint_row = keys_row('Tartsd lenyomva:', '[Ctrl]', '[Win]', 'beszélj, majd engedd el.')
        hint_row.setContentsMargins(0, 10, 0, 12)
        self.hint.setLayout(hint_row)
        outer.addWidget(self.hint)
        self.stack = QStackedWidget()
        outer.addWidget(self.stack, 1)

        # empty state: teaches the one gesture the app has
        empty = QWidget()
        e = QVBoxLayout(empty)
        e.setContentsMargins(0, 48, 0, 0)
        e.setSpacing(0)
        caps = QHBoxLayout()
        caps.setSpacing(10)
        caps.addWidget(keycap('Ctrl', True))
        caps.addWidget(label('+', 'muted'))
        caps.addWidget(keycap('Win', True))
        caps.addStretch()
        e.addLayout(caps)
        e.addSpacing(24)
        e.addWidget(label('Még nincs diktálás', 'h2'))
        e.addSpacing(6)
        body = label('Kattints bármelyik szövegmezőbe, tartsd lenyomva a két billentyűt, és beszélj. '
                     'Elengedéskor a szöveg oda kerül, ahol a kurzor áll.', 'muted', wrap=True)
        body.setMaximumWidth(460)
        e.addWidget(body)
        e.addSpacing(18)
        e.addLayout(keys_row('Kihangosított mód:', '[Ctrl]', '[Win]', '[Szóköz]'))
        e.addSpacing(8)
        e.addLayout(keys_row('Megszakítás:', '[Esc]'))
        e.addStretch()
        self.stack.addWidget(empty)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_host = QWidget()
        self.list = QVBoxLayout(self.list_host)
        self.list.setContentsMargins(0, 0, 8, 24)
        self.list.setSpacing(2)
        self.list.addStretch()
        self.scroll.setWidget(self.list_host)
        self.stack.addWidget(self.scroll)
        self._refresh_empty()

    @staticmethod
    def day_label(d):
        today = datetime.now().date()
        if d == today:
            return 'Ma'
        if (today - d).days == 1:
            return 'Tegnap'
        text = f'{MONTHS[d.month - 1]} {d.day}.'
        return text if d.year == today.year else f'{d.year}. {text}'

    def set_items(self, items):
        while self.list.count() > 1:
            w = self.list.takeAt(0).widget()
            if w:
                w.deleteLater()
        self.items = []
        for item in items:  # oldest first
            self.add_item(item)

    def add_item(self, item):
        """Newest items go on top, under a day header."""
        d = datetime.fromisoformat(item['t']).date()
        if not self.items or datetime.fromisoformat(self.items[-1]['t']).date() != d:
            self.list.insertWidget(0, label(self.day_label(d), 'day'))
            self.list.insertWidget(1, HistoryRow(item))
        else:
            self.list.insertWidget(1, HistoryRow(item))
        self.items.append(item)
        self._refresh_empty()

    def _refresh_empty(self):
        has = bool(self.items)
        self.stack.setCurrentIndex(1 if has else 0)
        self.hint.setVisible(has)


class SettingsPage(QWidget):
    changed = Signal(str, object)

    def __init__(self, settings, list_mics):
        super().__init__()
        self.setObjectName('page')
        self.list_mics = list_mics
        self.settings = settings
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(36, 32, 36, 32)
        lay.setSpacing(0)
        lay.addWidget(label('Beállítások', 'h1'))
        lay.addSpacing(24)

        def section(title, widget_or_layout, help_text=None):
            lay.addWidget(label(title, 'label'))
            lay.addSpacing(8)
            if isinstance(widget_or_layout, QWidget):
                lay.addWidget(widget_or_layout, 0, Qt.AlignmentFlag.AlignLeft)
            else:
                lay.addLayout(widget_or_layout)
            if help_text:
                lay.addSpacing(6)
                h = label(help_text, 'help', wrap=True)
                h.setMaximumWidth(520)
                lay.addWidget(h)
            lay.addSpacing(26)

        keys = QVBoxLayout()
        keys.setSpacing(8)
        keys.addLayout(keys_row('[Ctrl]', '[Win]', 'nyomva tartva: diktálás'))
        keys.addLayout(keys_row('[Ctrl]', '[Win]', '[Szóköz]', 'kihangosított mód'))
        keys.addLayout(keys_row('[Esc]', 'megszakítás'))
        section('Gyorsbillentyűk', keys)

        seg = QFrame()
        seg.setObjectName('segment')
        seg_lay = QHBoxLayout(seg)
        seg_lay.setContentsMargins(2, 2, 2, 2)
        seg_lay.setSpacing(2)
        self.lang_group = QButtonGroup(self)
        for value, text in (('auto', 'Automatikus'), ('hu', 'Magyar'), ('en', 'English')):
            b = QPushButton(text)
            b.setObjectName('seg')
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setProperty('value', value)
            b.setChecked(settings.get('language', 'auto') == value)
            self.lang_group.addButton(b)
            seg_lay.addWidget(b)
        self.lang_group.buttonClicked.connect(lambda b: self.changed.emit('language', b.property('value')))
        section('Nyelv', seg, 'Automatikus módban minden diktálásnál a magyar és az angol közül a valószínűbbet választja.')

        self.mic = QComboBox()
        self.mic.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mic.activated.connect(lambda _: self.changed.emit('mic', self.mic.currentData()))
        section('Mikrofon', self.mic)

        self.model = QComboBox()
        self.model.setCursor(Qt.CursorShape.PointingHandCursor)
        for value, text in (('auto', 'Automatikus (ajánlott)'), ('large-v3', 'large-v3, legpontosabb'),
                            ('large-v3-turbo', 'large-v3-turbo, gyorsabb'), ('medium', 'medium, gyenge gépekre')):
            self.model.addItem(text, value)
        self.model.setCurrentIndex(max(0, self.model.findData(settings.get('model', 'auto'))))
        self.model.activated.connect(lambda _: self.changed.emit('model', self.model.currentData()))
        section('Modell', self.model, 'Automatikus: NVIDIA videokártyán large-v3, egyébként large-v3-turbo. '
                                      'Új modell első betöltésekor letöltés indul.')

        self.dictionary = QPlainTextEdit(settings.get('dictionary', ''))
        self.dictionary.setPlaceholderText('Például:\nKovács Bence\nKubernetes\npull request')
        self.dictionary.setFixedSize(420, 120)
        self.dict_timer = QTimer(self, singleShot=True, interval=600,
                                 timeout=lambda: self.changed.emit('dictionary', self.dictionary.toPlainText()))
        self.dictionary.textChanged.connect(self.dict_timer.start)
        section('Szótár', self.dictionary, 'Nevek, szakszavak, márkák, soronként egy. '
                                           'A felismerés ezeket részesíti előnyben.')

        auto = QHBoxLayout()
        auto.setSpacing(12)
        self.autostart = Switch()
        self.autostart.toggled.connect(lambda on: self.changed.emit('autostart', on))
        auto.addWidget(self.autostart)
        auto.addWidget(label('Indítás a Windows-zal'))
        auto.addStretch()
        section('Rendszer', auto, 'Bejelentkezés után a Shout a tálcán vár, ablak nélkül.')

        upd = QHBoxLayout()
        upd.setSpacing(12)
        self.updates = Switch()
        self.updates.setChecked(settings.get('check_updates', True))
        self.updates.toggled.connect(lambda on: self.changed.emit('check_updates', on))
        upd.addWidget(self.updates)
        upd.addWidget(label('Frissítések keresése'))
        upd.addStretch()
        section('Frissítések', upd, f'Induláskor és naponta kétszer megnézi a GitHubon, van-e újabb verzió '
                                    f'(jelenleg {__version__}). Csak értesít, magától nem telepít semmit. '
                                    'Kikapcsolva az app a modell letöltésén kívül nem használ internetet.')
        lay.addStretch()
        scroll.setWidget(host)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def set_autostart(self, on):
        self.autostart.blockSignals(True)
        self.autostart.setChecked(on)
        self.autostart.blockSignals(False)

    def showEvent(self, e):
        current = self.settings.get('mic')
        self.mic.clear()
        self.mic.addItem('Rendszer alapértelmezett', None)
        for _, name in self.list_mics():
            self.mic.addItem(name, name)
        if current and self.mic.findData(current) < 0:
            self.mic.addItem(f'{current} (nincs csatlakoztatva)', current)
        self.mic.setCurrentIndex(max(0, self.mic.findData(current)))
        super().showEvent(e)


class MainWindow(QMainWindow):
    device_change = Signal()

    def __init__(self, settings, list_mics):
        super().__init__()
        self.setWindowTitle('Shout')
        self.setWindowIcon(QIcon(os.path.join(ASSETS, 'shout.ico')))
        self.resize(880, 600)
        self.setMinimumSize(720, 500)
        root = QWidget()
        root.setObjectName('content')
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        side = QFrame()
        side.setObjectName('sidebar')
        side.setFixedWidth(208)
        s = QVBoxLayout(side)
        s.setContentsMargins(14, 18, 14, 16)
        s.setSpacing(4)
        brand = QHBoxLayout()
        brand.setSpacing(10)
        mark = QLabel()
        mark.setPixmap(QIcon(os.path.join(ASSETS, 'shout.ico')).pixmap(24, 24))
        brand.addWidget(mark)
        brand.addWidget(label('Shout', 'brand'))
        brand.addStretch()
        s.addLayout(brand)
        s.addSpacing(22)
        self.nav_group = QButtonGroup(self)
        self.nav_buttons = []
        for i, (icon, text) in enumerate((('clock-counter-clockwise', 'Előzmények'), ('gear-six', 'Beállítások'))):
            b = QPushButton(text)
            b.setObjectName('nav')
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setIconSize(QSize(16, 16))
            b.setProperty('icon_name', icon)
            self.nav_group.addButton(b, i)
            self.nav_buttons.append(b)
            s.addWidget(b)
        self.nav_buttons[0].setChecked(True)
        s.addStretch()
        self.model_label = label('', 'model')
        self.status_label = label('Indítás', 'status', wrap=True)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 1000)
        self.progress.hide()
        self.update_label = label('', 'updateLink')
        self.update_label.setOpenExternalLinks(True)
        self.update_label.hide()
        s.addWidget(self.update_label)
        s.addSpacing(8)
        s.addWidget(self.model_label)
        s.addWidget(self.status_label)
        s.addSpacing(6)
        s.addWidget(self.progress)
        h.addWidget(side)

        self.pages = QStackedWidget()
        self.history = HistoryPage()
        self.settings_page = SettingsPage(settings, list_mics)
        self.pages.addWidget(self.history)
        self.pages.addWidget(self.settings_page)
        h.addWidget(self.pages, 1)
        self.nav_group.idClicked.connect(self.pages.setCurrentIndex)
        self.setCentralWidget(root)
        self.refresh_icons()

    def refresh_icons(self):
        t = tokens()
        for b in self.nav_buttons:
            ic = QIcon()
            ic.addPixmap(svg_pixmap(b.property('icon_name'), t['muted'], 16), QIcon.Mode.Normal, QIcon.State.Off)
            ic.addPixmap(svg_pixmap(b.property('icon_name'), t['text'], 16), QIcon.Mode.Normal, QIcon.State.On)
            b.setIcon(ic)
        if self.isVisible():
            set_dark_titlebar(self, is_dark())

    def set_update(self, tag, url):
        self.update_label.setText(f'<a href="{url}">Új verzió: {tag.lstrip("v")}</a>')
        self.update_label.show()

    def set_status(self, model, state, frac=None):
        self.model_label.setText(model)
        self.model_label.setVisible(bool(model))
        self.status_label.setText(state)
        self.progress.setVisible(frac is not None)
        if frac is not None:
            self.progress.setValue(int(frac * 1000))

    def showEvent(self, e):
        set_dark_titlebar(self, is_dark())
        super().showEvent(e)

    def closeEvent(self, e):
        e.ignore()  # closing the window keeps Shout running in the tray
        self.hide()

    def nativeEvent(self, event_type, message):
        if event_type == b'windows_generic_MSG':
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == 0x0219:  # WM_DEVICECHANGE: a headset was plugged in or switched on
                self.device_change.emit()
        return super().nativeEvent(event_type, message)

