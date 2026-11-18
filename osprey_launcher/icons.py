"""Provides item icons: system file icons, cached site icons, letter tiles and the UI line icons."""

from __future__ import annotations

import hashlib
from pathlib import Path

from PySide6.QtCore import (
    QByteArray,
    QFileInfo,
    QObject,
    QRectF,
    QSize,
    Qt,
    QUrl,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QPainter, QPainterPath, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QFileIconProvider

# Line icons from the Lucide set (ISC licence), drawn at 24 x 24 with a 1.5 stroke.
_LUCIDE = {
    "star": '<path d="M11.525 2.295a.53.53 0 0 1 .95 0l2.31 4.679a2.123 2.123 0 0 0 1.595 1.16'
    "l5.166.756a.53.53 0 0 1 .294.904l-3.736 3.638a2.123 2.123 0 0 0-.611 1.878l.882 5.14"
    "a.53.53 0 0 1-.771.56l-4.618-2.428a2.122 2.122 0 0 0-1.973 0L6.396 21.01a.53.53 0 0 1"
    "-.77-.56l.881-5.139a2.122 2.122 0 0 0-.611-1.879L2.16 9.795a.53.53 0 0 1 .294-.906"
    'l5.165-.755a2.122 2.122 0 0 0 1.597-1.16z"/>',
    "plus": '<path d="M5 12h14"/><path d="M12 5v14"/>',
    "search": '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/>'
    '<path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/>'
    '<path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/>',
    "moon": '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
    "layout-grid": '<rect width="7" height="7" x="3" y="3" rx="1"/>'
    '<rect width="7" height="7" x="14" y="3" rx="1"/>'
    '<rect width="7" height="7" x="14" y="14" rx="1"/>'
    '<rect width="7" height="7" x="3" y="14" rx="1"/>',
    "monitor": '<rect width="20" height="14" x="2" y="3" rx="2"/><path d="M8 21h8"/><path d="M12 17v4"/>',
    "download": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/>'
    '<path d="M12 15V3"/>',
}

ICON_SIZE = 40


def line_icon(name: str, color: str, size: int = 16, fill: str = "none") -> QIcon:
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="{fill}" '
        f'stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">'
        f"{_LUCIDE[name]}</svg>"
    )
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    icon = QIcon()
    for scale in (1, 2):
        pix = QPixmap(size * scale, size * scale)
        pix.fill(Qt.transparent)
        painter = QPainter(pix)
        renderer.render(painter)
        painter.end()
        pix.setDevicePixelRatio(scale)
        icon.addPixmap(pix)
    return icon


def app_icon() -> QIcon:
    """The app's own icon for the window and taskbar, drawn from the embedded master SVG."""
    from .app_icon import APP_ICON_SVG

    renderer = QSvgRenderer(QByteArray(APP_ICON_SVG.encode()))
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256, 512):
        pix = QPixmap(size, size)
        pix.fill(Qt.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing)
        renderer.render(painter)
        painter.end()
        icon.addPixmap(pix)
    return icon


def _rounded(image: QImage, size: int, scale: float) -> QPixmap:
    """Draw an image centred in a rounded square, so site icons match the system icons."""
    px = int(size * scale)
    pix = QPixmap(px, px)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    clip = QPainterPath()
    clip.addRoundedRect(QRectF(0, 0, px, px), 10 * scale, 10 * scale)
    painter.setClipPath(clip)
    painter.fillRect(pix.rect(), QColor("#ffffff"))
    inner = int(px * 0.7)
    scaled = image.scaled(inner, inner, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    painter.drawImage((px - scaled.width()) // 2, (px - scaled.height()) // 2, scaled)
    painter.end()
    pix.setDevicePixelRatio(scale)
    return pix


def letter_tile(text: str, bg: str, fg: str, scale: float) -> QPixmap:
    px = int(ICON_SIZE * scale)
    pix = QPixmap(px, px)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, px, px), 10 * scale, 10 * scale)
    painter.fillPath(path, QColor(bg))
    font = QFont()
    font.setPixelSize(int(17 * scale))
    font.setWeight(QFont.Medium)
    painter.setFont(font)
    painter.setPen(QColor(fg))
    painter.drawText(pix.rect(), Qt.AlignCenter, (text[:1] or "?").upper())
    painter.end()
    pix.setDevicePixelRatio(scale)
    return pix


class IconCache(QObject):
    """Builds item icons and downloads a site's icon once when a link is added."""

    site_icon_ready = Signal(str)  # domain

    def __init__(self, data_dir: Path, parent=None):
        super().__init__(parent)
        self.folder = data_dir / "icons"
        self.provider = QFileIconProvider()
        self.net = QNetworkAccessManager(self)
        self.pending: set[str] = set()

    def _site_icon_path(self, domain: str) -> Path:
        return self.folder / (hashlib.sha1(domain.encode()).hexdigest()[:16] + ".png")

    def pixmap_for_path(self, path: str, scale: float) -> QPixmap:
        icon = self.provider.icon(QFileInfo(path))
        pix = icon.pixmap(QSize(ICON_SIZE, ICON_SIZE), scale)
        return pix

    def pixmap_for_link(self, domain: str, bg: str, fg: str, scale: float) -> QPixmap:
        image = QImage(str(self._site_icon_path(domain)))
        if image.isNull():
            return letter_tile(domain, bg, fg, scale)
        return _rounded(image, ICON_SIZE, scale)

    def has_site_icon(self, domain: str) -> bool:
        return self._site_icon_path(domain).exists()

    # Site icon download. Only contacts the site the link points to.

    def fetch_site_icon(self, domain: str) -> None:
        if domain in self.pending:
            return
        self.pending.add(domain)
        self._request(
            domain,
            [f"https://{domain}/apple-touch-icon.png", f"https://{domain}/favicon.ico"],
        )

    def _request(self, domain: str, urls: list[str]) -> None:
        if not urls:
            self.pending.discard(domain)
            return
        request = QNetworkRequest(QUrl(urls[0]))
        request.setAttribute(
            QNetworkRequest.RedirectPolicyAttribute,
            QNetworkRequest.NoLessSafeRedirectPolicy,
        )
        request.setTransferTimeout(8000)
        reply = self.net.get(request)
        reply.finished.connect(lambda: self._done(reply, domain, urls[1:]))

    def _done(self, reply: QNetworkReply, domain: str, rest: list[str]) -> None:
        data = reply.readAll()
        ok = reply.error() == QNetworkReply.NoError
        reply.deleteLater()
        image = QImage.fromData(data) if ok else QImage()
        if image.isNull() or image.width() < 16:
            self._request(domain, rest)
            return
        self.folder.mkdir(parents=True, exist_ok=True)
        image.save(str(self._site_icon_path(domain)), "PNG")
        self.pending.discard(domain)
        self.site_icon_ready.emit(domain)
