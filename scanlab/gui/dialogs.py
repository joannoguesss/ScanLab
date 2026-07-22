"""Diálogos avanzados del Modo Profesional: Histograma, Corrección tonal
y tamaño de destino personalizado — como en Epson Scan."""

from PIL import Image
from PySide6 import QtCore, QtGui, QtWidgets

from scanlab.gui.postprocess import levels_lut

_CHANNELS = {"RGB (mestre)": "master", "Vermell": "r", "Verd": "g", "Blau": "b"}


class _HistogramView(QtWidgets.QWidget):
    """Histograma de 256 niveles con marcadores arrastrables de sombra,
    medios tonos (gamma) y luz, como en Epson Scan."""

    MARKER_H = 14
    changed = QtCore.Signal()

    def __init__(self):
        super().__init__()
        self.setMinimumSize(300, 160)
        self._counts = [0] * 256
        self.black = 0
        self.white = 255
        self.gamma = 1.0
        self._dragging = None  # "black" | "gamma" | "white"

    def set_histogram(self, counts):
        self._counts = counts or [0] * 256
        self.update()

    def set_levels(self, black, white, gamma):
        self.black, self.white, self.gamma = black, white, gamma
        self.update()

    # --- geometría ---

    def _x(self, value: float) -> float:
        return value / 255 * (self.width() - 12) + 6

    def _value(self, x: float) -> float:
        return min(max((x - 6) / (self.width() - 12) * 255, 0), 255)

    def _gamma_value(self) -> float:
        """Posición (0-255) del marcador de medios tonos según la gamma."""
        t = 0.5 ** self.gamma
        return self.black + t * (self.white - self.black)

    # --- pintura ---

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        hist_h = self.height() - self.MARKER_H
        painter.fillRect(self.rect(), QtGui.QColor(245, 245, 245))
        top = max(self._counts) or 1
        painter.setPen(QtGui.QColor(90, 90, 90))
        for i, count in enumerate(self._counts):
            h = (count / top) * (hist_h - 8)
            x = round(self._x(i))
            painter.drawLine(x, hist_h, x, round(hist_h - h))

        for value, color in ((self.black, QtGui.QColor(0, 0, 0)),
                             (self._gamma_value(), QtGui.QColor(130, 130, 130)),
                             (self.white, QtGui.QColor(200, 160, 0))):
            x = self._x(value)
            painter.setPen(QtGui.QPen(color, 1, QtCore.Qt.DashLine))
            painter.drawLine(round(x), 0, round(x), hist_h)
            triangle = QtGui.QPolygonF([
                QtCore.QPointF(x, hist_h + 2),
                QtCore.QPointF(x - 6, self.height() - 1),
                QtCore.QPointF(x + 6, self.height() - 1),
            ])
            painter.setPen(QtGui.QPen(QtGui.QColor(60, 60, 60), 1))
            painter.setBrush(color)
            painter.drawPolygon(triangle)

    # --- arrastre ---

    def _marker_at(self, x: float):
        candidates = {
            "black": self._x(self.black),
            "gamma": self._x(self._gamma_value()),
            "white": self._x(self.white),
        }
        name, distance = min(
            ((n, abs(x - mx)) for n, mx in candidates.items()), key=lambda p: p[1]
        )
        return name if distance <= 10 else None

    def mousePressEvent(self, event):
        self._dragging = self._marker_at(event.position().x())
        if self._dragging:
            self.mouseMoveEvent(event)

    def mouseMoveEvent(self, event):
        if not self._dragging:
            return
        value = self._value(event.position().x())
        if self._dragging == "black":
            self.black = int(min(value, self.white - 2))
        elif self._dragging == "white":
            self.white = int(max(value, self.black + 2))
        else:  # gamma: la posición fija qué entrada se convierte en gris medio
            import math

            t = (value - self.black) / max(self.white - self.black, 1)
            t = min(max(t, 0.02), 0.98)
            self.gamma = min(max(math.log(t) / math.log(0.5), 0.10), 9.99)
        self.update()
        self.changed.emit()

    def mouseReleaseEvent(self, event):
        self._dragging = None


class HistogramPanel(QtWidgets.QGroupBox):
    """Histograma INTEGRAT a la finestra principal, sempre visible.

    Es pot arrossegar ombra/mitjos/llum sobre el mateix histograma i l'efecte
    es veu a l'instant a la previsualització (senyal levels_changed)."""

    levels_changed = QtCore.Signal(object)  # dict {canal: (negre, blanc, gamma)}
    close_requested = QtCore.Signal()       # la creueta ✕ del panell

    def __init__(self, preview_provider, levels: dict | None = None, parent=None):
        super().__init__("Histograma", parent)
        self._preview_provider = preview_provider
        self.levels = dict(levels or {})

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(4)
        header = QtWidgets.QHBoxLayout()
        self._channel = QtWidgets.QComboBox()
        self._channel.addItems(list(_CHANNELS))
        header.addWidget(self._channel, 1)
        close_btn = QtWidgets.QToolButton()
        close_btn.setText("✕")
        close_btn.setToolTip("Amaga l'histograma (Eines ▸ Histograma per tornar-lo)")
        close_btn.setAutoRaise(True)
        close_btn.clicked.connect(self.close_requested.emit)
        header.addWidget(close_btn)
        layout.addLayout(header)

        self._view = _HistogramView()
        self._view.setMinimumSize(260, 120)
        layout.addWidget(self._view, 1)

        row = QtWidgets.QHBoxLayout()
        self._black = QtWidgets.QSpinBox()
        self._black.setRange(0, 253)
        self._gamma = QtWidgets.QDoubleSpinBox()
        self._gamma.setRange(0.10, 9.99)
        self._gamma.setSingleStep(0.05)
        self._gamma.setValue(1.0)
        self._white = QtWidgets.QSpinBox()
        self._white.setRange(2, 255)
        self._white.setValue(255)
        for label, widget in (("Ombra:", self._black),
                              ("Gamma:", self._gamma),
                              ("Llum:", self._white)):
            row.addWidget(QtWidgets.QLabel(label))
            row.addWidget(widget)
        row.addStretch(1)
        layout.addLayout(row)

        buttons = QtWidgets.QHBoxLayout()
        reset_channel = QtWidgets.QPushButton("Restableix el canal")
        reset_all = QtWidgets.QPushButton("Restableix-ho tot")
        reset_channel.clicked.connect(self._reset_channel)
        reset_all.clicked.connect(self._reset_all)
        buttons.addWidget(reset_channel)
        buttons.addWidget(reset_all)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        self._loading = False
        self._channel.currentTextChanged.connect(self._load_channel)
        self._view.changed.connect(self._from_view)
        for widget in (self._black, self._white):
            widget.valueChanged.connect(self._from_spinboxes)
        self._gamma.valueChanged.connect(self._from_spinboxes)
        self.refresh()

    def _key(self):
        return _CHANNELS[self._channel.currentText()]

    def refresh(self):
        """Recarga el histograma desde la previsualización actual."""
        preview = self._preview_provider()
        if preview is not None:
            key = self._key()
            if key == "master" or preview.mode not in ("RGB", "RGBA"):
                counts = preview.convert("L").histogram()
            else:
                band = {"r": 0, "g": 1, "b": 2}[key]
                counts = preview.convert("RGB").split()[band].histogram()
            self._view.set_histogram(counts)
        self._load_channel()

    def _load_channel(self):
        self._loading = True
        black, white, gamma = self.levels.get(self._key(), (0, 255, 1.0))
        self._black.setValue(int(black))
        self._white.setValue(int(white))
        self._gamma.setValue(float(gamma))
        self._view.set_levels(int(black), int(white), float(gamma))
        self._loading = False
        if self.isVisible():
            self.refresh_histogram_only()

    def refresh_histogram_only(self):
        preview = self._preview_provider()
        if preview is None:
            return
        key = self._key()
        if key == "master" or preview.mode not in ("RGB", "RGBA"):
            counts = preview.convert("L").histogram()
        else:
            band = {"r": 0, "g": 1, "b": 2}[key]
            counts = preview.convert("RGB").split()[band].histogram()
        self._view.set_histogram(counts)

    def _from_view(self):
        self._loading = True
        self._black.setValue(self._view.black)
        self._white.setValue(self._view.white)
        self._gamma.setValue(self._view.gamma)
        self._loading = False
        self._store()

    def _from_spinboxes(self):
        if self._loading:
            return
        self._view.set_levels(
            self._black.value(), self._white.value(), self._gamma.value()
        )
        self._store()

    def _store(self):
        black, white, gamma = (
            self._black.value(), self._white.value(), self._gamma.value()
        )
        if (black, white, round(gamma, 2)) == (0, 255, 1.0):
            self.levels.pop(self._key(), None)
        else:
            self.levels[self._key()] = (black, white, gamma)
        self.levels_changed.emit(dict(self.levels))

    def _reset_channel(self):
        self.levels.pop(self._key(), None)
        self._load_channel()
        self.levels_changed.emit(dict(self.levels))

    def _reset_all(self):
        self.levels.clear()
        self._load_channel()
        self.levels_changed.emit(dict(self.levels))


def curve_lut_from_points(points) -> list[int]:
    """LUT de 256 valors a partir dels punts de la corba (interp. lineal)."""
    lut = []
    pts = sorted(points)
    for x in range(256):
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            if x0 <= x <= x1:
                t = (x - x0) / (x1 - x0) if x1 > x0 else 0
                lut.append(round(y0 + t * (y1 - y0)))
                break
        else:
            lut.append(x)
    return lut


class _CurveView(QtWidgets.QWidget):
    """Curva de tonos con puntos arrastrables (entrada → salida)."""

    changed = QtCore.Signal()

    def __init__(self, points):
        super().__init__()
        self.setMinimumSize(280, 280)
        self.points = list(points)  # [(x, y)] ordenados, extremos incluidos
        self._drag_index = None

    def lut(self) -> list[int]:
        return curve_lut_from_points(self.points)

    def _to_widget(self, point):
        x, y = point
        return QtCore.QPointF(
            x / 255 * (self.width() - 12) + 6,
            (255 - y) / 255 * (self.height() - 12) + 6,
        )

    def _to_curve(self, pos):
        x = (pos.x() - 6) / (self.width() - 12) * 255
        y = 255 - (pos.y() - 6) / (self.height() - 12) * 255
        return (min(max(round(x), 0), 255), min(max(round(y), 0), 255))

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.fillRect(self.rect(), QtGui.QColor(245, 245, 245))
        painter.setPen(QtGui.QColor(200, 200, 200))
        for i in range(1, 4):
            x = round(i * self.width() / 4)
            y = round(i * self.height() / 4)
            painter.drawLine(x, 0, x, self.height())
            painter.drawLine(0, y, self.width(), y)
        painter.setPen(QtGui.QPen(QtGui.QColor(40, 40, 40), 2))
        path = QtGui.QPainterPath()
        pts = sorted(self.points)
        path.moveTo(self._to_widget(pts[0]))
        for p in pts[1:]:
            path.lineTo(self._to_widget(p))
        painter.drawPath(path)
        painter.setBrush(QtGui.QColor(255, 255, 255))
        for p in pts:
            painter.drawEllipse(self._to_widget(p), 4, 4)

    def mousePressEvent(self, event):
        pos = event.position()
        for i, p in enumerate(self.points):
            if (self._to_widget(p) - pos).manhattanLength() < 10:
                self._drag_index = i
                return
        # doble uso: clic en zona libre añade un punto (máx. 16)
        if len(self.points) < 16:
            self.points.append(self._to_curve(pos))
            self._drag_index = self.points.index(self.points[-1])
            self.update()

    def mouseMoveEvent(self, event):
        if self._drag_index is None:
            return
        x, y = self._to_curve(event.position())
        old_x = self.points[self._drag_index][0]
        # los extremos solo se mueven en vertical
        if old_x in (0, 255):
            x = old_x
        self.points[self._drag_index] = (x, y)
        self.update()

    def mouseReleaseEvent(self, event):
        self._drag_index = None
        self.changed.emit()


class ToneCurveDialog(QtWidgets.QDialog):
    PRESETS = {
        "Lineal": [(0, 0), (255, 255)],
        "Més contrast": [(0, 0), (64, 48), (192, 208), (255, 255)],
        "Aclareix les ombres": [(0, 16), (96, 128), (255, 255)],
        "Enfosqueix les llums": [(0, 0), (160, 128), (255, 236)],
    }

    def __init__(self, points, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Correcció tonal")
        layout = QtWidgets.QVBoxLayout(self)

        presets = QtWidgets.QComboBox()
        presets.addItems(list(self.PRESETS))
        layout.addWidget(presets)

        self._view = _CurveView(points or self.PRESETS["Lineal"])
        layout.addWidget(self._view, 1)
        hint = QtWidgets.QLabel(
            "Arrossega els punts; fes clic a la corba per afegir-ne."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        presets.currentTextChanged.connect(
            lambda name: (self._view.points.clear(),
                          self._view.points.extend(self.PRESETS[name]),
                          self._view.update())
        )

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def points(self):
        return sorted(self._view.points)

    def lut(self):
        return self._view.lut()


class CustomSizeDialog(QtWidgets.QDialog):
    """Mida de destinació personalitzada (com «Personalitza…» a l'Epson Scan)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Mida de destinació personalitzada")
        form = QtWidgets.QFormLayout(self)
        self.name = QtWidgets.QLineEdit("Personalitzada")
        self.width_mm = QtWidgets.QDoubleSpinBox()
        self.width_mm.setRange(5, 400)
        self.width_mm.setValue(100)
        self.width_mm.setSuffix(" mm")
        self.height_mm = QtWidgets.QDoubleSpinBox()
        self.height_mm.setRange(5, 400)
        self.height_mm.setValue(150)
        self.height_mm.setSuffix(" mm")
        form.addRow("Nom:", self.name)
        form.addRow("Amplada:", self.width_mm)
        form.addRow("Alçada:", self.height_mm)
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)
