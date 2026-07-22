"""Panell de previsualització amb marquesines múltiples, com l'Epson Scan.

Fins a 50 marquesines: es dibuixen arrossegant, es mouen des de dins, es
copien i s'esborren. L'activa es marca en color. Densitòmetre en passar el
ratolí (valors RGB sota el cursor). El zoom es mostra al mateix panell.
"""

from PIL import Image
from PySide6 import QtCore, QtGui, QtWidgets

from scanlab.gui.postprocess import apply_levels

MAX_MARQUEES = 50


class PreviewCanvas(QtWidgets.QWidget):
    selection_changed = QtCore.Signal()
    hover_rgb = QtCore.Signal(str)

    def __init__(self):
        super().__init__()
        self.setMinimumSize(420, 520)
        self.setMouseTracking(True)
        self._pixmap: QtGui.QPixmap | None = None
        self._image: Image.Image | None = None
        self._zoom_image: Image.Image | None = None
        self._display_levels: dict | None = None  # nivells de l'histograma en viu
        self._preview_dpi = 75
        self._marquees: list[QtCore.QRectF] = []  # en coords d'imatge (px)
        self._active = -1
        self._drag_start = None
        self._moving = False
        self._move_offset = QtCore.QPointF()
        self.setCursor(QtCore.Qt.CrossCursor)
        # Opcions del menú «Visualitza» (superposicions de la selecció activa)
        self.show_dims = True      # mides en mm (amplada × alçada)
        self.show_area = False     # àrea en mm²
        self.show_thirds = False   # quadrícula de terços
        self.show_center = False   # centre de la selecció

    # --- estat ---

    def set_preview(self, image: Image.Image, dpi: int):
        self._image = image
        self._zoom_image = None
        self._preview_dpi = dpi
        self._rebuild_pixmap()
        self._marquees = []
        self._active = -1
        self.selection_changed.emit()
        self.update()

    def set_zoom(self, image: Image.Image):
        """Mostra la marquesina ampliada al mateix panell (sense tocar res més)."""
        self._zoom_image = image
        self._rebuild_pixmap()
        self.update()

    def clear_zoom(self):
        self._zoom_image = None
        if self._image is not None:
            self._rebuild_pixmap()
        self.update()

    @property
    def zoom_active(self) -> bool:
        return self._zoom_image is not None

    def set_display_levels(self, levels: dict | None):
        """Aplica els nivells de l'histograma a la vista EN VIU."""
        self._display_levels = dict(levels) if levels else None
        if self._image is not None or self._zoom_image is not None:
            self._rebuild_pixmap()
            self.update()

    def _rebuild_pixmap(self):
        image = self._zoom_image or self._image
        if image is None:
            self._pixmap = None
            return
        if self._display_levels:
            image = apply_levels(image, self._display_levels)
        data = image.convert("RGB")
        qimage = QtGui.QImage(
            data.tobytes(), data.width, data.height, data.width * 3,
            QtGui.QImage.Format_RGB888,
        )
        self._pixmap = QtGui.QPixmap.fromImage(qimage)

    def has_preview(self) -> bool:
        return self._image is not None

    @property
    def image(self):
        return self._image

    def _rect_mm(self, rect: QtCore.QRectF):
        scale = 25.4 / self._preview_dpi
        return (rect.x() * scale, rect.y() * scale,
                rect.width() * scale, rect.height() * scale)

    def selection_mm(self):
        """Marquesina activa com a (x, y, amplada, alçada) en mm, o None."""
        if self._active < 0 or self._image is None:
            return None
        return self._rect_mm(self._marquees[self._active])

    def selections_mm(self):
        """Totes les marquesines en mm (per «Totes»)."""
        return [self._rect_mm(r) for r in self._marquees]

    def marquee_count(self) -> int:
        return len(self._marquees)

    def auto_locate(self):
        """Col·loca una marquesina a les vores de l'original."""
        if self._image is None or self.zoom_active:
            return
        gray = self._image.convert("L")
        boxes = []
        for img in (gray.point(lambda p: 255 if p < 235 else 0),
                    gray.point(lambda p: 255 if p > 25 else 0)):
            box = img.getbbox()
            if box:
                boxes.append(box)
        if not boxes:
            return
        box = min(boxes, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))
        self._marquees.append(
            QtCore.QRectF(box[0], box[1], box[2] - box[0], box[3] - box[1])
        )
        self._active = len(self._marquees) - 1
        self.selection_changed.emit()
        self.update()

    def copy_marquee(self):
        if self._active < 0 or len(self._marquees) >= MAX_MARQUEES or self.zoom_active:
            return
        rect = QtCore.QRectF(self._marquees[self._active])
        rect.translate(15, 15)
        bounds = QtCore.QRectF(0, 0, self._image.width, self._image.height)
        rect.moveLeft(min(rect.left(), bounds.width() - rect.width()))
        rect.moveTop(min(rect.top(), bounds.height() - rect.height()))
        self._marquees.append(rect)
        self._active = len(self._marquees) - 1
        self.selection_changed.emit()
        self.update()

    def delete_active(self):
        if self._active >= 0:
            del self._marquees[self._active]
            self._active = len(self._marquees) - 1
        self.selection_changed.emit()
        self.update()

    def clear_selection(self):
        self._marquees = []
        self._active = -1
        self.selection_changed.emit()
        self.update()

    # --- geometria widget <-> imatge ---

    def _fit_rect(self) -> QtCore.QRectF:
        if not self._pixmap:
            return QtCore.QRectF()
        size = self._pixmap.size()
        size.scale(self.size(), QtCore.Qt.KeepAspectRatio)
        x = (self.width() - size.width()) / 2
        y = (self.height() - size.height()) / 2
        return QtCore.QRectF(x, y, size.width(), size.height())

    def _to_image(self, pos: QtCore.QPointF) -> QtCore.QPointF:
        fit = self._fit_rect()
        sx = self._pixmap.width() / fit.width()
        sy = self._pixmap.height() / fit.height()
        x = min(max(pos.x() - fit.x(), 0), fit.width()) * sx
        y = min(max(pos.y() - fit.y(), 0), fit.height()) * sy
        return QtCore.QPointF(x, y)

    def _to_widget(self, rect: QtCore.QRectF) -> QtCore.QRectF:
        fit = self._fit_rect()
        sx = fit.width() / self._pixmap.width()
        sy = fit.height() / self._pixmap.height()
        return QtCore.QRectF(
            fit.x() + rect.x() * sx, fit.y() + rect.y() * sy,
            rect.width() * sx, rect.height() * sy,
        )

    # --- esdeveniments ---

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.fillRect(self.rect(), QtGui.QColor(60, 60, 60))
        if not self._pixmap:
            painter.setPen(QtGui.QColor(200, 200, 200))
            painter.drawText(
                self.rect(), QtCore.Qt.AlignCenter,
                "Prem «Previsualitza» per veure el vidre",
            )
            return
        painter.drawPixmap(self._fit_rect().toRect(), self._pixmap)
        if self.zoom_active:
            return
        for i, marquee in enumerate(self._marquees):
            rect = self._to_widget(marquee)
            color = QtGui.QColor(80, 180, 255) if i == self._active else \
                QtGui.QColor(255, 255, 255)
            painter.setPen(QtGui.QPen(color, 1, QtCore.Qt.DashLine))
            painter.drawRect(rect)
            pen = QtGui.QPen(QtGui.QColor(0, 0, 0), 1, QtCore.Qt.DashLine)
            pen.setDashOffset(3)
            painter.setPen(pen)
            painter.drawRect(rect)
            painter.setPen(color)
            painter.drawText(rect.adjusted(3, 1, 0, 0).topLeft() +
                             QtCore.QPointF(0, 12), str(i + 1))
            if i == self._active:
                self._paint_overlays(painter, rect, marquee)

    def _paint_overlays(self, painter, rect: QtCore.QRectF, marquee: QtCore.QRectF):
        """Superposicions del menú «Visualitza» sobre la marquesina activa."""
        if self.show_thirds:
            pen = QtGui.QPen(QtGui.QColor(255, 255, 255, 150), 1, QtCore.Qt.DashLine)
            painter.setPen(pen)
            for f in (1 / 3, 2 / 3):
                x = rect.x() + rect.width() * f
                y = rect.y() + rect.height() * f
                painter.drawLine(QtCore.QPointF(x, rect.top()),
                                 QtCore.QPointF(x, rect.bottom()))
                painter.drawLine(QtCore.QPointF(rect.left(), y),
                                 QtCore.QPointF(rect.right(), y))
        if self.show_center:
            center = rect.center()
            painter.setPen(QtGui.QPen(QtGui.QColor(255, 90, 90), 1))
            painter.drawLine(QtCore.QPointF(center.x() - 10, center.y()),
                             QtCore.QPointF(center.x() + 10, center.y()))
            painter.drawLine(QtCore.QPointF(center.x(), center.y() - 10),
                             QtCore.QPointF(center.x(), center.y() + 10))
            painter.drawEllipse(center, 3, 3)
        lines = []
        if self.show_dims or self.show_area:
            x_mm, y_mm, w_mm, h_mm = self._rect_mm(marquee)
            if self.show_dims:
                lines.append(f"{w_mm:.0f} × {h_mm:.0f} mm")
            if self.show_area:
                lines.append(f"{w_mm * h_mm:,.0f} mm²".replace(",", "."))
        if lines:
            font = painter.font()
            font.setPointSize(11)
            painter.setFont(font)
            metrics = QtGui.QFontMetricsF(font)
            width = max(metrics.horizontalAdvance(t) for t in lines) + 10
            height = metrics.height() * len(lines) + 6
            x = rect.left()
            y = rect.bottom() + 4
            if y + height > self.height():
                y = rect.top() - height - 4
            box = QtCore.QRectF(x, y, width, height)
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(QtGui.QColor(0, 0, 0, 170))
            painter.drawRoundedRect(box, 3, 3)
            painter.setPen(QtGui.QColor(255, 255, 255))
            for n, text in enumerate(lines):
                painter.drawText(
                    QtCore.QPointF(x + 5, y + metrics.ascent() + 3 + n * metrics.height()),
                    text,
                )

    def mousePressEvent(self, event):
        if not self._pixmap or self.zoom_active:
            return
        pos = self._to_image(event.position())
        for i in range(len(self._marquees) - 1, -1, -1):
            if self._marquees[i].contains(pos):
                self._active = i
                self._moving = True
                self._move_offset = pos - self._marquees[i].topLeft()
                self.setCursor(QtCore.Qt.ClosedHandCursor)
                self.selection_changed.emit()
                self.update()
                return
        if len(self._marquees) >= MAX_MARQUEES:
            return
        self._drag_start = pos
        self._marquees.append(QtCore.QRectF(pos, pos))
        self._active = len(self._marquees) - 1

    def mouseMoveEvent(self, event):
        if not self._pixmap:
            return
        pos = self._to_image(event.position())
        base = self._zoom_image or self._image
        if base is not None:
            x = min(int(pos.x() * base.width / self._pixmap.width()), base.width - 1)
            y = min(int(pos.y() * base.height / self._pixmap.height()), base.height - 1)
            pixel = base.convert("RGB").getpixel((x, y))
            self.hover_rgb.emit(f"RGB: {pixel[0]}, {pixel[1]}, {pixel[2]}")
        if self.zoom_active:
            return
        if self._moving and self._active >= 0:
            rect = QtCore.QRectF(self._marquees[self._active])
            rect.moveTopLeft(pos - self._move_offset)
            bounds = QtCore.QRectF(0, 0, self._pixmap.width(), self._pixmap.height())
            rect.moveLeft(min(max(rect.left(), 0), bounds.width() - rect.width()))
            rect.moveTop(min(max(rect.top(), 0), bounds.height() - rect.height()))
            self._marquees[self._active] = rect
        elif self._drag_start is not None:
            self._marquees[self._active] = QtCore.QRectF(
                self._drag_start, pos
            ).normalized()
        else:
            return
        self.update()

    def mouseReleaseEvent(self, event):
        if self._moving:
            self._moving = False
            self.setCursor(QtCore.Qt.CrossCursor)
        if self._drag_start is not None:
            self._drag_start = None
            rect = self._marquees[self._active]
            if rect.width() < 4 or rect.height() < 4:
                del self._marquees[self._active]
                self._active = len(self._marquees) - 1
                self.update()
        self.selection_changed.emit()


class PreviewPane(QtWidgets.QWidget):
    """Llenç + barra d'eines: marquesines, zoom al mateix panell, girar i mirall."""

    zoom_requested = QtCore.Signal()

    def __init__(self):
        super().__init__()
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.canvas = PreviewCanvas()
        self.rotation = 0        # 0/90/180/270 en sentit horari
        self.mirrored = False

        toolbar = QtWidgets.QHBoxLayout()
        toolbar.setSpacing(4)

        def button(text, tooltip, slot):
            b = QtWidgets.QPushButton(text)
            b.setToolTip(tooltip)
            b.clicked.connect(slot)
            toolbar.addWidget(b)
            return b

        button("Auto", "Marquesina a les vores de l'original", self.canvas.auto_locate)
        button("Copia", "Duplica la marquesina activa", self.canvas.copy_marquee)
        button("Esborra", "Esborra la marquesina activa", self.canvas.delete_active)
        button("Cap", "Treu totes les marquesines", self.canvas.clear_selection)
        button("Zoom", "Escaneja la marquesina activa ampliada",
               self.zoom_requested.emit)
        self.back_btn = button("◀ Torna", "Torna a la previsualització completa",
                               self._back_from_zoom)
        self.back_btn.setVisible(False)
        button("⟳", "Gira 90° el resultat", self._rotate)
        button("⇋", "Mirall del resultat", self._mirror)
        toolbar.addStretch(1)
        self.info = QtWidgets.QLabel("")
        toolbar.addWidget(self.info)

        layout.addLayout(toolbar)
        layout.addWidget(self.canvas, 1)
        self.canvas.selection_changed.connect(self._update_info)
        self.canvas.hover_rgb.connect(self._show_rgb)
        self._rgb = ""

    def show_zoom(self, image: Image.Image):
        self.canvas.set_zoom(image)
        self.back_btn.setVisible(True)
        self._update_info()

    def _back_from_zoom(self):
        self.canvas.clear_zoom()
        self.back_btn.setVisible(False)
        self._update_info()

    def _rotate(self):
        self.rotation = (self.rotation + 90) % 360
        self._update_info()

    def _mirror(self):
        self.mirrored = not self.mirrored
        self._update_info()

    def apply_orientation(self, image: Image.Image) -> Image.Image:
        if self.mirrored:
            image = image.transpose(Image.FLIP_LEFT_RIGHT)
        if self.rotation:
            image = image.rotate(-self.rotation, expand=True)
        return image

    def _show_rgb(self, text):
        self._rgb = text
        self._update_info()

    def _update_info(self):
        parts = []
        if self.canvas.zoom_active:
            parts.append("Zoom — «◀ Torna» per sortir")
        else:
            area = self.canvas.selection_mm()
            count = self.canvas.marquee_count()
            if area:
                parts.append(f"{count} marq. | activa: {area[2]:.0f} × {area[3]:.0f} mm")
            else:
                parts.append("Sense marquesina: s'escaneja tot")
        if self.rotation or self.mirrored:
            orientation = []
            if self.rotation:
                orientation.append(f"⟳{self.rotation}°")
            if self.mirrored:
                orientation.append("mirall")
            parts.append(" ".join(orientation))
        if self._rgb:
            parts.append(self._rgb)
        self.info.setText("  |  ".join(parts))
