"""Finestra principal de ScanLab (basada en el mode professional de l'EPSON Scan).

Sense selector de modes: tots els controls del mode professional, amb
l'histograma integrat i sempre visible. Menús: «Eines» (correcció tonal,
configuració de desar) i «Visualitza» (superposicions de la selecció).
"""

import os
import sys
from dataclasses import asdict

from PIL import Image
from PySide6 import QtCore, QtGui, QtWidgets

from scanlab.gui import config
from scanlab.gui.dialogs import (
    CustomSizeDialog, HistogramPanel, ToneCurveDialog, curve_lut_from_points,
)
from scanlab.gui.filesave import FORMATS, FileSaveDialog, SaveSettings
from scanlab.gui.postprocess import Adjustments, apply as apply_adjustments
from scanlab.gui.preview import PreviewPane
from scanlab.gui.runner import (
    ScanRunner, set_worker32, using_worker32, worker32_available, worker_command,
)
from scanlab.settings import ScanSettings

PREVIEW_DPI = 75

LEVELS = {"Baix": "low", "Mitjà": "medium", "Alt": "high"}

TARGET_SIZES_MM = {
    "Original": None,
    "10 × 15 cm": (100, 150),
    "13 × 18 cm": (130, 180),
    "20 × 25 cm": (200, 250),
    "A4 (210 × 297 mm)": (210, 297),
    "Carta (216 × 279 mm)": (216, 279),
}


def _level_combo() -> QtWidgets.QComboBox:
    combo = QtWidgets.QComboBox()
    combo.addItems(list(LEVELS))
    combo.setCurrentText("Mitjà")
    return combo


def _slider(minimum=-100, maximum=100, value=0) -> QtWidgets.QSlider:
    slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
    slider.setRange(minimum, maximum)
    slider.setValue(value)
    return slider


class TargetSizeCombo(QtWidgets.QComboBox):
    """Mida de destinació amb opció «Personalitza…», com l'Epson Scan."""

    def __init__(self):
        super().__init__()
        self.sizes = dict(TARGET_SIZES_MM)
        self.addItems(list(self.sizes))
        self.addItem("Personalitza…")
        self.activated.connect(self._maybe_custom)

    def _maybe_custom(self, index):
        if self.itemText(index) != "Personalitza…":
            return
        dialog = CustomSizeDialog(self)
        if dialog.exec():
            width, height = dialog.width_mm.value(), dialog.height_mm.value()
            name = f"{dialog.name.text()} ({width:.0f} × {height:.0f} mm)"
            self.sizes[name] = (width, height)
            self.insertItem(self.count() - 1, name)
            self.setCurrentText(name)
        else:
            self.setCurrentIndex(0)

    def target_mm(self):
        return self.sizes.get(self.currentText())


class SettingsPanel(QtWidgets.QWidget):
    """Controls d'escaneig (l'antic mode professional, ara únic)."""

    IMAGE_TYPES = [
        "Color de 48 bits",
        "Color de 24 bits",
        "Suavitzat de color",
        "Grisos de 16 bits",
        "Grisos de 8 bits",
        "Blanc i negre",
    ]
    RESOLUTIONS = ["50", "72", "96", "150", "200", "240", "300", "400", "600",
                   "800", "1200", "2400", "3200", "4800", "6400", "9600", "12800"]

    def __init__(self):
        super().__init__()
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        inner = QtWidgets.QWidget()
        scroll.setWidget(inner)
        outer.addWidget(scroll)
        layout = QtWidgets.QVBoxLayout(inner)

        original_box = QtWidgets.QGroupBox("Original")
        original = QtWidgets.QFormLayout(original_box)
        self.doc_type = QtWidgets.QComboBox()
        self.doc_type.addItems(["Reflectant", "Pel·lícula"])
        self.exposure_type = QtWidgets.QComboBox()
        self.exposure_type.addItems(["Foto", "Document"])
        self.film_type = QtWidgets.QComboBox()
        self.film_type.addItems(
            ["Pel·lícula positiva", "Pel·lícula negativa en color",
             "Pel·lícula negativa B/N"]
        )
        self.film_type.setEnabled(False)
        original.addRow("Tipus de document:", self.doc_type)
        original.addRow("Autoexposició:", self.exposure_type)
        original.addRow("Tipus de pel·lícula:", self.film_type)
        self.doc_type.currentTextChanged.connect(self._doc_changed)
        layout.addWidget(original_box)

        dest_box = QtWidgets.QGroupBox("Destinació")
        dest = QtWidgets.QFormLayout(dest_box)
        self.image_type = QtWidgets.QComboBox()
        self.image_type.addItems(self.IMAGE_TYPES)
        self.image_type.setCurrentText("Color de 24 bits")
        self.resolution = QtWidgets.QComboBox()
        self.resolution.setEditable(True)
        self.resolution.addItems(self.RESOLUTIONS)
        self.resolution.setCurrentText("300")
        self.target_size = TargetSizeCombo()
        self.scale = QtWidgets.QSpinBox()
        self.scale.setRange(10, 400)
        self.scale.setValue(100)
        self.scale.setSuffix(" %")
        dest.addRow("Tipus d'imatge:", self.image_type)
        dest.addRow("Resolució (ppp):", self.resolution)
        dest.addRow("Mida de destinació:", self.target_size)
        dest.addRow("Escala:", self.scale)
        layout.addWidget(dest_box)

        adj_box = QtWidgets.QGroupBox("Ajustos")
        adj = QtWidgets.QVBoxLayout(adj_box)

        self.auto_exposure = QtWidgets.QCheckBox("Autoexposició")
        self.auto_exposure.setChecked(True)
        adj.addWidget(self.auto_exposure)

        self.unsharp = QtWidgets.QCheckBox("Màscara d'enfocament")
        self.unsharp.setChecked(True)
        self.unsharp_level = _level_combo()
        adj.addLayout(self._with_level(self.unsharp, self.unsharp_level))

        self.descreening = QtWidgets.QCheckBox("Destramat")
        adj.addWidget(self.descreening)
        self.color_restore = QtWidgets.QCheckBox("Restauració del color")
        adj.addWidget(self.color_restore)

        self.backlight = QtWidgets.QCheckBox("Correcció de contrallum")
        self.backlight_level = _level_combo()
        adj.addLayout(self._with_level(self.backlight, self.backlight_level))

        self.dust = QtWidgets.QCheckBox("Eliminació de la pols")
        self.dust_level = _level_combo()
        adj.addLayout(self._with_level(self.dust, self.dust_level))

        sliders = QtWidgets.QFormLayout()
        sliders.setFieldGrowthPolicy(
            QtWidgets.QFormLayout.AllNonFixedFieldsGrow
        )
        self.brightness = _slider()
        self.contrast = _slider()
        self.saturation = _slider()
        self.balance_r = _slider()
        self.balance_g = _slider()
        self.balance_b = _slider()
        self.threshold = _slider(0, 255, 128)
        sliders.addRow("Brillantor:", self.brightness)
        sliders.addRow("Contrast:", self.contrast)
        sliders.addRow("Saturació:", self.saturation)
        sliders.addRow("Balanç vermell:", self.balance_r)
        sliders.addRow("Balanç verd:", self.balance_g)
        sliders.addRow("Balanç blau:", self.balance_b)
        sliders.addRow("Llindar (B/N):", self.threshold)
        adj.addLayout(sliders)

        layout.addWidget(adj_box)
        layout.addStretch(1)

        # Nivells de l'histograma (els fixa el HistogramPanel) i corba tonal.
        self.levels: dict = {}
        self.curve_points = None
        self.curve_lut = None

    @staticmethod
    def _with_level(checkbox, combo):
        row = QtWidgets.QHBoxLayout()
        row.addWidget(checkbox)
        row.addStretch(1)
        row.addWidget(QtWidgets.QLabel("Nivell:"))
        row.addWidget(combo)
        return row

    def _doc_changed(self, text):
        is_film = text == "Pel·lícula"
        self.film_type.setEnabled(is_film)
        self.exposure_type.setEnabled(not is_film)

    def open_curve(self):
        dialog = ToneCurveDialog(self.curve_points, self.window())
        if dialog.exec():
            self.curve_points = dialog.points()
            lut = dialog.lut()
            self.curve_lut = None if lut == list(range(256)) else lut

    def scan_settings(self) -> ScanSettings:
        if self.doc_type.currentText() == "Pel·lícula":
            film = self.film_type.currentText()
            source = "transparency" if film == "Pel·lícula positiva" else "negative"
        else:
            source = "flatbed"
        image_type = self.image_type.currentText()
        if image_type.startswith("Color") or image_type == "Suavitzat de color":
            mode = "color"
        else:
            mode = "gray"
        depth = 16 if "48" in image_type or "16" in image_type else 8
        try:
            dpi = int(self.resolution.currentText())
        except ValueError:
            dpi = 300
        return ScanSettings(resolution=dpi, mode=mode, source=source, depth=depth)

    def adjustments(self) -> Adjustments:
        return Adjustments(
            auto_exposure=self.auto_exposure.isChecked(),
            unsharp_mask=self.unsharp.isChecked(),
            unsharp_level=LEVELS[self.unsharp_level.currentText()],
            descreening=self.descreening.isChecked(),
            color_restoration=self.color_restore.isChecked(),
            backlight_correction=self.backlight.isChecked(),
            backlight_level=LEVELS[self.backlight_level.currentText()],
            dust_removal=self.dust.isChecked(),
            dust_level=LEVELS[self.dust_level.currentText()],
            brightness=self.brightness.value(),
            contrast=self.contrast.value(),
            saturation=self.saturation.value(),
            color_balance=(
                self.balance_r.value(), self.balance_g.value(), self.balance_b.value()
            ),
            threshold=self.threshold.value(),
            apply_threshold=self.image_type.currentText() == "Blanc i negre",
            levels=self.levels or None,
            curve_lut=self.curve_lut,
        )

    def target_mm(self):
        return self.target_size.target_mm()


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ScanLab — Epson Perfection V500 Photo")
        self.resize(1150, 780)

        self.save_settings = SaveSettings()
        self.runner = ScanRunner(self)
        self.runner.finished.connect(self._scan_finished)
        self.runner.failed.connect(self._scan_failed)
        self._pending = None       # ("preview" | "scan" | "zoom", panel)
        self._queue: list = []     # àrees mm pendents de «Escaneja-ho tot»
        self._queue_total = 0
        self._pdf_pages: list = []  # pàgines acumulades per al PDF multipàgina

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        root = QtWidgets.QHBoxLayout(central)

        self.preview = PreviewPane()
        self.preview.zoom_requested.connect(self._do_zoom)
        root.addWidget(self.preview, 1)

        side = QtWidgets.QVBoxLayout()

        self.settings_panel = SettingsPanel()
        side.addWidget(self.settings_panel, 1)

        # Histograma integrat, sempre visible.
        self.histogram = HistogramPanel(lambda: self.preview.canvas.image)
        self.histogram.levels_changed.connect(self._on_levels_changed)
        side.addWidget(self.histogram)

        buttons = QtWidgets.QGridLayout()
        buttons.setSpacing(6)
        self.preview_btn = QtWidgets.QPushButton("Previsualitza")
        self.scan_btn = QtWidgets.QPushButton("Escaneja")
        self.scan_btn.setDefault(True)
        self.scan_all_btn = QtWidgets.QPushButton("Escaneja-ho tot")
        self.scan_all_btn.setToolTip(
            "Escaneja totes les marquesines, una per fitxer"
        )
        save_btn = QtWidgets.QPushButton("Desa a…")
        self.preview_btn.clicked.connect(self._do_preview)
        self.scan_btn.clicked.connect(self._do_scan)
        self.scan_all_btn.clicked.connect(self._do_scan_all)
        save_btn.clicked.connect(self._file_save_dialog)
        buttons.addWidget(self.preview_btn, 0, 0)
        buttons.addWidget(self.scan_btn, 0, 1)
        buttons.addWidget(self.scan_all_btn, 1, 0)
        buttons.addWidget(save_btn, 1, 1)
        side.addLayout(buttons)

        self.finish_pdf_btn = QtWidgets.QPushButton("Acaba el PDF")
        self.finish_pdf_btn.setEnabled(False)
        self.finish_pdf_btn.clicked.connect(self._finish_pdf)
        side.addWidget(self.finish_pdf_btn)

        panel_widget = QtWidgets.QWidget()
        panel_widget.setLayout(side)
        panel_widget.setFixedWidth(400)
        root.addWidget(panel_widget)

        self._build_menu()
        self._load_state()
        self.statusBar().showMessage("A punt")

        # Pilot de connexió de l'escàner (verd/vermell) a la barra d'estat.
        self._connection_label = QtWidgets.QLabel()
        self.statusBar().addPermanentWidget(self._connection_label)
        self._set_connection(None)
        self._tried_worker32 = False
        self._poll_process: QtCore.QProcess | None = None
        self._poll_timer = QtCore.QTimer(self)
        self._poll_timer.setInterval(8000)
        self._poll_timer.timeout.connect(self._poll_connection)
        self._poll_timer.start()
        QtCore.QTimer.singleShot(300, self._poll_connection)

    # --- pilot de connexió ---

    def _set_connection(self, ok: bool | None):
        if ok is None:
            color, text = "#8a8a8a", "Comprovant l'escàner…"
        elif ok:
            color, text = "#2fa84f", "Escàner connectat"
        else:
            color, text = "#d9403e", "Escàner desconnectat"
        self._connection_label.setText(
            f'<span style="color:{color}; font-size:14px">●</span> {text}'
        )
        self._connection_label.setToolTip(
            "Eines ▸ Diagnòstic… per veure què detecta ScanLab"
        )

    def _poll_connection(self):
        if self.runner.busy():
            self._set_connection(True)  # si estem escanejant, està connectat
            return
        if (self._poll_process is not None
                and self._poll_process.state() != QtCore.QProcess.NotRunning):
            return
        program, args, workdir = worker_command(["list"])
        process = QtCore.QProcess(self)
        if workdir:
            process.setWorkingDirectory(workdir)
        process.finished.connect(lambda code, _s: self._connection_result(code))
        self._poll_process = process
        process.start(program, args)

    def _connection_result(self, code: int):
        """Si el camí de 64 bits no veu res, prova l'ajudant de 32 bits.

        Els drivers TWAIN antics només són de 32 bits i un procés de 64 no els
        pot carregar; el canvi és automàtic i es recorda.
        """
        if code == 0:
            self._set_connection(True)
            return
        if not using_worker32() and worker32_available() and not self._tried_worker32:
            self._tried_worker32 = True
            set_worker32(True)
            self._sync_worker32_action()
            self._poll_connection()
            return
        if using_worker32() and self._tried_worker32:
            set_worker32(False)   # tampoc va: tornem al camí principal
            self._sync_worker32_action()
        self._tried_worker32 = False
        self._set_connection(False)

    def _build_menu(self):
        # Guardem referències per evitar que PySide alliberi els menús natius.
        self._tools_menu = self.menuBar().addMenu("Eines")
        self._act_histogram = self._tools_menu.addAction("Histograma")
        self._act_histogram.setCheckable(True)
        self._act_histogram.setChecked(True)
        self._act_histogram.toggled.connect(self.histogram.setVisible)
        self.histogram.close_requested.connect(
            lambda: self._act_histogram.setChecked(False)
        )
        self._act_curve = self._tools_menu.addAction("Correcció tonal…")
        self._act_curve.triggered.connect(self.settings_panel.open_curve)
        self._tools_menu.addSeparator()
        self._act_save = self._tools_menu.addAction("Configuració de desar…")
        self._act_save.triggered.connect(self._file_save_dialog)
        self._act_diagnose = self._tools_menu.addAction("Diagnòstic…")
        self._act_diagnose.triggered.connect(self._open_diagnostics)
        self._act_worker32 = self._tools_menu.addAction("Usa l'ajudant de 32 bits")
        self._act_worker32.setCheckable(True)
        self._act_worker32.setEnabled(worker32_available())
        self._act_worker32.setChecked(using_worker32())
        self._act_worker32.setToolTip(
            "Necessari per als drivers TWAIN antics (i per escanejar pel·lícula)"
        )
        self._act_worker32.toggled.connect(self._toggle_worker32)

        self._view_menu = self.menuBar().addMenu("Visualitza")
        canvas = self.preview.canvas
        self._view_actions = []
        for text, attr, default in (
            ("Mides (mm)", "show_dims", True),
            ("Àrea (mm²)", "show_area", False),
            ("Quadrícula de terços", "show_thirds", False),
            ("Centre de la selecció", "show_center", False),
        ):
            action = self._view_menu.addAction(text)
            action.setCheckable(True)
            action.setChecked(default)
            setattr(canvas, attr, default)
            action.toggled.connect(
                lambda checked, a=attr: (setattr(canvas, a, checked), canvas.update())
            )
            self._view_actions.append(action)

    def _toggle_worker32(self, checked: bool):
        set_worker32(checked)
        self._tried_worker32 = False
        self._poll_connection()

    def _sync_worker32_action(self):
        """Reflecteix al menú el canvi automàtic, sense tornar-lo a disparar."""
        self._act_worker32.blockSignals(True)
        self._act_worker32.setChecked(using_worker32())
        self._act_worker32.blockSignals(False)

    def _open_diagnostics(self):
        """Informe de què veu ScanLab del sistema i de l'escàner (per a suport)."""
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Diagnòstic")
        dialog.resize(700, 480)
        layout = QtWidgets.QVBoxLayout(dialog)

        text = QtWidgets.QPlainTextEdit("Generant l'informe…")
        text.setReadOnly(True)
        text.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        text.setFont(
            QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont)
        )
        layout.addWidget(text, 1)

        buttons = QtWidgets.QHBoxLayout()
        copy_btn = QtWidgets.QPushButton("Copia")
        copy_btn.clicked.connect(
            lambda: QtWidgets.QApplication.clipboard().setText(text.toPlainText())
        )
        close_btn = QtWidgets.QPushButton("Tanca")
        close_btn.clicked.connect(dialog.accept)
        buttons.addWidget(copy_btn)
        buttons.addStretch(1)
        buttons.addWidget(close_btn)
        layout.addLayout(buttons)

        sections: list[str] = []

        def _run(command, header, then=None):
            program, args, workdir = command
            process = QtCore.QProcess(dialog)
            if workdir:
                process.setWorkingDirectory(workdir)
            process.setProcessChannelMode(QtCore.QProcess.MergedChannels)

            def _done(code, _status):
                output = bytes(process.readAllStandardOutput()).decode(
                    "utf-8", errors="replace"
                ).strip()
                if not output:
                    output = f"(sense sortida, codi {code})"
                sections.append(f"===== {header} =====\n{output}")
                text.setPlainText("\n\n".join(sections))
                if then is not None:
                    then()

            process.finished.connect(_done)
            process.start(program, args)

        def _also_32_bits():
            # L'informe del camí de 32 bits: és el que veu els drivers antics.
            if worker32_available() and not using_worker32():
                _run(worker_command(["diagnose"], force32=True), "AJUDANT DE 32 BITS")

        _run(worker_command(["diagnose"]), "PROCÉS PRINCIPAL", _also_32_bits)
        dialog.exec()

    def _on_levels_changed(self, levels):
        self.settings_panel.levels = dict(levels)
        self.preview.canvas.set_display_levels(levels)

    # --- persistència entre sessions ---

    def closeEvent(self, event):
        self._save_state()
        super().closeEvent(event)

    def _save_state(self):
        p = self.settings_panel
        custom_sizes = {
            name: list(size) for name, size in p.target_size.sizes.items()
            if name not in TARGET_SIZES_MM and size
        }
        state = {
            "original": {
                "doc_type": p.doc_type.currentText(),
                "exposure_type": p.exposure_type.currentText(),
                "film_type": p.film_type.currentText(),
            },
            "dest": {
                "image_type": p.image_type.currentText(),
                "resolution": p.resolution.currentText(),
                "target_size": p.target_size.currentText(),
                "custom_sizes": custom_sizes,
                "scale": p.scale.value(),
            },
            "adjust": {
                "auto_exposure": p.auto_exposure.isChecked(),
                "unsharp": p.unsharp.isChecked(),
                "unsharp_level": p.unsharp_level.currentText(),
                "descreening": p.descreening.isChecked(),
                "color_restore": p.color_restore.isChecked(),
                "backlight": p.backlight.isChecked(),
                "backlight_level": p.backlight_level.currentText(),
                "dust": p.dust.isChecked(),
                "dust_level": p.dust_level.currentText(),
                "brightness": p.brightness.value(),
                "contrast": p.contrast.value(),
                "saturation": p.saturation.value(),
                "balance": [p.balance_r.value(), p.balance_g.value(),
                            p.balance_b.value()],
                "threshold": p.threshold.value(),
            },
            "levels": {k: list(v) for k, v in p.levels.items()},
            "curve_points": (
                [list(pt) for pt in p.curve_points] if p.curve_points else None
            ),
            "save": asdict(self.save_settings),
            "view": [a.isChecked() for a in self._view_actions],
            "histogram_visible": self._act_histogram.isChecked(),
            "worker32": using_worker32(),
            "geometry": bytes(self.saveGeometry().toBase64()).decode("ascii"),
        }
        config.save(state)

    @staticmethod
    def _set_combo(combo, text):
        if text and combo.findText(text) >= 0:
            combo.setCurrentText(text)

    def _load_state(self):
        state = config.load()
        if not state:
            return
        p = self.settings_panel

        original = state.get("original", {})
        self._set_combo(p.doc_type, original.get("doc_type"))
        self._set_combo(p.exposure_type, original.get("exposure_type"))
        self._set_combo(p.film_type, original.get("film_type"))

        dest = state.get("dest", {})
        self._set_combo(p.image_type, dest.get("image_type"))
        if dest.get("resolution"):
            p.resolution.setCurrentText(str(dest["resolution"]))
        for name, size in dest.get("custom_sizes", {}).items():
            if name not in p.target_size.sizes:
                p.target_size.sizes[name] = tuple(size)
                p.target_size.insertItem(p.target_size.count() - 1, name)
        self._set_combo(p.target_size, dest.get("target_size"))
        if "scale" in dest:
            p.scale.setValue(int(dest["scale"]))

        adjust = state.get("adjust", {})
        for key, widget in (
            ("auto_exposure", p.auto_exposure), ("unsharp", p.unsharp),
            ("descreening", p.descreening), ("color_restore", p.color_restore),
            ("backlight", p.backlight), ("dust", p.dust),
        ):
            if key in adjust:
                widget.setChecked(bool(adjust[key]))
        self._set_combo(p.unsharp_level, adjust.get("unsharp_level"))
        self._set_combo(p.backlight_level, adjust.get("backlight_level"))
        self._set_combo(p.dust_level, adjust.get("dust_level"))
        for key, slider in (
            ("brightness", p.brightness), ("contrast", p.contrast),
            ("saturation", p.saturation), ("threshold", p.threshold),
        ):
            if key in adjust:
                slider.setValue(int(adjust[key]))
        balance = adjust.get("balance")
        if balance and len(balance) == 3:
            p.balance_r.setValue(int(balance[0]))
            p.balance_g.setValue(int(balance[1]))
            p.balance_b.setValue(int(balance[2]))

        levels = {k: tuple(v) for k, v in state.get("levels", {}).items()}
        if levels:
            p.levels = dict(levels)
            self.histogram.levels = dict(levels)
            self.histogram._load_channel()
        curve = state.get("curve_points")
        if curve:
            p.curve_points = [tuple(pt) for pt in curve]
            lut = curve_lut_from_points(p.curve_points)
            p.curve_lut = None if lut == list(range(256)) else lut

        saved = state.get("save", {})
        for key, value in saved.items():
            if hasattr(self.save_settings, key):
                setattr(self.save_settings, key, value)
        if self.save_settings.format_label not in FORMATS:
            self.save_settings.format_label = "JPEG (*.jpg)"

        view = state.get("view")
        if view:
            for action, checked in zip(self._view_actions, view):
                action.setChecked(bool(checked))
        self._act_histogram.setChecked(bool(state.get("histogram_visible", True)))
        if state.get("worker32"):
            # A la sessió anterior calia l'ajudant de 32 bits.
            set_worker32(True)
            self._act_worker32.blockSignals(True)
            self._act_worker32.setChecked(using_worker32())
            self._act_worker32.blockSignals(False)

        geometry = state.get("geometry")
        if geometry:
            self.restoreGeometry(
                QtCore.QByteArray.fromBase64(geometry.encode("ascii"))
            )

    # --- accions ---

    def _set_busy(self, message):
        for btn in (self.preview_btn, self.scan_btn, self.scan_all_btn):
            btn.setEnabled(False)
        self.statusBar().showMessage(message)

    def _set_idle(self, message="A punt"):
        for btn in (self.preview_btn, self.scan_btn, self.scan_all_btn):
            btn.setEnabled(True)
        self.finish_pdf_btn.setEnabled(bool(self._pdf_pages))
        self.finish_pdf_btn.setText(
            f"Acaba el PDF ({len(self._pdf_pages)} pàg.)" if self._pdf_pages
            else "Acaba el PDF"
        )
        self.statusBar().showMessage(message)

    def _do_preview(self):
        settings = self.settings_panel.scan_settings()
        preview = ScanSettings(
            resolution=PREVIEW_DPI, mode="color", source=settings.source
        )
        self._pending = ("preview", self.settings_panel)
        self._set_busy("Previsualitzant…")
        self.runner.scan(preview)

    def _do_scan(self):
        settings = self.settings_panel.scan_settings()
        area = self.preview.canvas.selection_mm()
        if area:
            settings.area = area
        if self.save_settings.show_before_scan:
            if not FileSaveDialog(self.save_settings, self).exec():
                return
        self._pending = ("scan", self.settings_panel)
        self._set_busy(f"Escanejant a {settings.resolution} ppp…")
        self.runner.scan(settings)

    def _do_scan_all(self):
        areas = self.preview.canvas.selections_mm()
        if not areas:
            QtWidgets.QMessageBox.information(
                self, "ScanLab",
                "No hi ha marquesines. Previsualitza i dibuixa'n almenys una."
            )
            return
        if self.save_settings.show_before_scan:
            if not FileSaveDialog(self.save_settings, self).exec():
                return
        self._queue = list(areas)
        self._queue_total = len(areas)
        self._next_in_queue()

    def _next_in_queue(self):
        area = self._queue.pop(0)
        settings = self.settings_panel.scan_settings()
        settings.area = area
        done = self._queue_total - len(self._queue)
        self._pending = ("scan", self.settings_panel)
        self._set_busy(
            f"Escanejant marquesina {done}/{self._queue_total} "
            f"a {settings.resolution} ppp…"
        )
        self.runner.scan(settings)

    def _do_zoom(self):
        if self.preview.canvas.zoom_active:
            return
        area = self.preview.canvas.selection_mm()
        if not area:
            QtWidgets.QMessageBox.information(
                self, "ScanLab",
                "Dibuixa o selecciona una marquesina per ampliar-la."
            )
            return
        settings = self.settings_panel.scan_settings()
        settings.resolution = 300
        settings.area = area
        settings.depth = 8
        self._pending = ("zoom", self.settings_panel)
        self._set_busy("Ampliant la marquesina…")
        self.runner.scan(settings)

    def _finish_pdf(self):
        if not self._pdf_pages:
            return
        try:
            saved = self.save_settings.save_pdf_pages(self._pdf_pages)
        except OSError as exc:
            self._set_idle(f"Error en desar el PDF: {exc}")
            return
        pages, self._pdf_pages = len(self._pdf_pages), []
        self._set_idle(f"PDF desat: {saved} ({pages} pàgines)")

    def _file_save_dialog(self):
        FileSaveDialog(self.save_settings, self).exec()

    # --- resultats ---

    def _scan_finished(self, path):
        stage, panel = self._pending or ("", None)
        self._pending = None
        image = Image.open(path)
        image.load()
        os.remove(path)

        if stage == "preview":
            self.preview.canvas.set_preview(image, PREVIEW_DPI)
            self.histogram.refresh_histogram_only()
            self.preview.canvas.set_display_levels(self.settings_panel.levels)
            self._set_idle(
                "Previsualització a punt: dibuixa la marquesina sobre la imatge"
            )
            return

        if stage == "zoom":
            self.preview.show_zoom(image)
            self._set_idle("Zoom a punt — «◀ Torna» per tornar a la previsualització")
            return

        # stage == "scan": aplicar ajustos, redimensionar i desar.
        image = apply_adjustments(image, panel.adjustments())
        image = self.preview.apply_orientation(image)
        target = panel.target_mm()
        settings = panel.scan_settings()
        if target:
            width_px = round(target[0] / 25.4 * settings.resolution)
            height_px = round(target[1] / 25.4 * settings.resolution)
            image = image.resize((width_px, height_px), Image.LANCZOS)
        if panel.scale.value() != 100:
            factor = panel.scale.value() / 100
            image = image.resize(
                (max(1, round(image.width * factor)),
                 max(1, round(image.height * factor))),
                Image.LANCZOS,
            )
        if self.save_settings.extension == "pdf" and self.save_settings.multipage_pdf:
            self._pdf_pages.append(image)
            message = f"Pàgina {len(self._pdf_pages)} acumulada per al PDF"
        else:
            try:
                saved = self.save_settings.save_image(image)
            except OSError as exc:
                self._queue = []
                self._set_idle(f"Error en desar: {exc}")
                return
            message = f"Desat: {saved} ({image.width}×{image.height}px)"

        if self._queue:
            self.statusBar().showMessage(message)
            self._next_in_queue()
        else:
            self._set_idle(message)

    def _scan_failed(self, message):
        self._pending = None
        self._queue = []
        self._set_idle(f"Error: {message}")
        box = QtWidgets.QMessageBox(
            QtWidgets.QMessageBox.Warning, "ScanLab", message,
            QtWidgets.QMessageBox.Ok, self,
        )
        detail = (self.runner.last_output or "").strip()
        if detail:
            box.setDetailedText(
                f"{detail}\n\nRegistre complet: {config.LOG_PATH}"
            )
        box.exec()


def _icon_path():
    base = getattr(sys, "_MEIPASS", None)  # app empaquetada amb PyInstaller
    if base:
        path = os.path.join(base, "ScanLab_1024.png")
    else:
        path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "..", "packaging", "icons", "ScanLab_1024.png",
        )
    return path if os.path.exists(path) else None


def run():
    app = QtWidgets.QApplication([])
    app.setApplicationName("ScanLab")
    icon = _icon_path()
    if icon:
        app.setWindowIcon(QtGui.QIcon(icon))
    window = MainWindow()
    window.show()
    app.exec()
