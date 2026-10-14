"""Draws the Shout mark (off-black rounded square, white waveform bars) and writes assets/shout.ico.

Run: python make_icon.py [preview.png]
"""
import struct
import sys

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPen

INK, PAPER = QColor('#0B0B0C'), QColor('#FAFAFA')
SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def render(size):
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    # Faint light edge keeps the off-black square visible on dark taskbars.
    edge = max(1.0, size / 64)
    p.setPen(QPen(QColor(255, 255, 255, 34), edge))
    p.setBrush(INK)
    r = QRectF(edge / 2, edge / 2, size - edge, size - edge)
    p.drawRoundedRect(r, size * 0.23, size * 0.23)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(PAPER)
    # Optical sizing: three fat bars at tray sizes, five bars once there is room.
    if size <= 24:
        heights, w, g = (0.5, 1.0, 0.5), max(2, round(size / 8)), max(2, round(size / 8))
    elif size <= 48:
        heights, w, g = (0.38, 0.68, 1.0, 0.68, 0.38), round(size * 0.075), max(2, round(size * 0.05))
    else:
        heights, w, g = (0.38, 0.68, 1.0, 0.68, 0.38), size * 0.075, size * 0.05
    total = len(heights) * w + (len(heights) - 1) * g
    x = (size - total) / 2
    box = size * (0.56 if size <= 24 else 0.5)
    for h in heights:
        bh = box * h
        if size <= 48:  # snap to whole pixels so small sizes stay crisp
            x, bh = round(x), round(bh / 2) * 2
        p.drawRoundedRect(QRectF(x, (size - bh) / 2, w, bh), w / 2, w / 2)
        x += w + g
    p.end()
    return img


def png_bytes(img):
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, 'PNG')
    return bytes(data)


def write_ico(path):
    blobs = [png_bytes(render(s)) for s in SIZES]
    offset = 6 + 16 * len(SIZES)
    out = struct.pack('<HHH', 0, 1, len(SIZES))
    for s, b in zip(SIZES, blobs):
        out += struct.pack('<BBBBHHII', s % 256, s % 256, 0, 0, 1, 32, len(b), offset)
        offset += len(b)
    with open(path, 'wb') as f:
        f.write(out + b''.join(blobs))


def preview(path):
    pad, zoom = 24, 6
    sheet = QImage(1100, 520, QImage.Format.Format_ARGB32)
    p = QPainter(sheet)
    for row, bg in enumerate(('#F4F4F5', '#0C0C0E')):
        p.fillRect(0, row * 260, 1100, 260, QColor(bg))
        x = pad
        for s in SIZES:
            p.drawImage(x, row * 260 + pad, render(s))
            x += s + pad
        x = pad
        for s in (16, 20, 24, 32):
            p.drawImage(QRectF(x, row * 260 + 150, s * zoom / 2, s * zoom / 2), render(s))
            x += s * zoom / 2 + pad
    p.end()
    sheet.save(path)


if __name__ == '__main__':
    app = QGuiApplication(sys.argv)
    write_ico('assets/shout.ico')
    if len(sys.argv) > 1:
        preview(sys.argv[1])
