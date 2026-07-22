"""Ventana "Ajustes de guardar archivo", como la de Epson Scan.

Carpeta + prefijo + número inicial de 3 cifras, formato con opciones, y las
casillas de sobrescribir, mostrar antes de escanear y abrir carpeta al acabar.
"""

import os
import subprocess
from dataclasses import dataclass

from PySide6 import QtWidgets

FORMATS = {
    "JPEG (*.jpg)": "jpg",
    "TIFF (*.tif)": "tif",
    "PNG (*.png)": "png",
    "BITMAP (*.bmp)": "bmp",
    "PDF (*.pdf)": "pdf",
}


@dataclass
class SaveSettings:
    folder: str = os.path.expanduser("~/Pictures")
    prefix: str = "img"
    start_number: int = 1
    format_label: str = "JPEG (*.jpg)"
    jpeg_quality: int = 85
    overwrite: bool = False
    show_before_scan: bool = True
    open_folder: bool = False
    multipage_pdf: bool = False  # acumular páginas hasta «Terminar PDF»

    @property
    def extension(self) -> str:
        return FORMATS[self.format_label]

    def next_path(self) -> str:
        """Siguiente nombre libre: prefijo + número de 3 cifras."""
        number = self.start_number
        while True:
            path = os.path.join(self.folder, f"{self.prefix}{number:03d}.{self.extension}")
            if self.overwrite or not os.path.exists(path):
                self.start_number = number + 1
                return path
            number += 1

    def save_pdf_pages(self, pages) -> str:
        """Guarda varias imágenes como un único PDF multipágina."""
        os.makedirs(self.folder, exist_ok=True)
        pages = [p.convert("RGB") if p.mode not in ("RGB", "L") else p for p in pages]
        number = self.start_number
        while True:
            path = os.path.join(self.folder, f"{self.prefix}{number:03d}.pdf")
            if self.overwrite or not os.path.exists(path):
                break
            number += 1
        self.start_number = number + 1
        pages[0].save(path, save_all=True, append_images=pages[1:], resolution=100.0)
        if self.open_folder:
            subprocess.run(["open", self.folder], check=False)
        return path

    def save_image(self, image) -> str:
        os.makedirs(self.folder, exist_ok=True)
        path = self.next_path()
        options = {}
        if self.extension == "jpg":
            options = {"quality": self.jpeg_quality}
            if image.mode not in ("RGB", "L"):
                image = image.convert("RGB")
        if self.extension == "pdf" and image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        if self.extension in ("jpg", "tif", "png", "bmp"):
            image.save(path, **options)
        else:
            image.save(path, resolution=100.0)
        if self.open_folder:
            subprocess.run(["open", self.folder], check=False)
        return path


class FileSaveDialog(QtWidgets.QDialog):
    def __init__(self, settings: SaveSettings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configuració de desar el fitxer")
        self._settings = settings

        layout = QtWidgets.QVBoxLayout(self)

        folder_group = QtWidgets.QGroupBox("Ubicació")
        folder_row = QtWidgets.QHBoxLayout(folder_group)
        self._folder = QtWidgets.QLineEdit(settings.folder)
        browse = QtWidgets.QPushButton("Navega…")
        browse.clicked.connect(self._browse)
        folder_row.addWidget(self._folder, 1)
        folder_row.addWidget(browse)
        layout.addWidget(folder_group)

        name_group = QtWidgets.QGroupBox("Nom del fitxer (prefix + número de 3 xifres)")
        name_row = QtWidgets.QFormLayout(name_group)
        self._prefix = QtWidgets.QLineEdit(settings.prefix)
        self._start = QtWidgets.QSpinBox()
        self._start.setRange(1, 999)
        self._start.setValue(settings.start_number)
        name_row.addRow("Prefix:", self._prefix)
        name_row.addRow("Número inicial:", self._start)
        layout.addWidget(name_group)

        format_group = QtWidgets.QGroupBox("Format d'imatge")
        format_row = QtWidgets.QFormLayout(format_group)
        self._format = QtWidgets.QComboBox()
        self._format.addItems(list(FORMATS))
        self._format.setCurrentText(settings.format_label)
        self._quality = QtWidgets.QSpinBox()
        self._quality.setRange(10, 100)
        self._quality.setValue(settings.jpeg_quality)
        self._multipage = QtWidgets.QCheckBox(
            "PDF multipàgina (acumula pàgines fins a «Acaba el PDF»)"
        )
        self._multipage.setChecked(settings.multipage_pdf)
        format_row.addRow("Tipus:", self._format)
        format_row.addRow("Qualitat JPEG:", self._quality)
        format_row.addRow(self._multipage)
        layout.addWidget(format_group)

        self._overwrite = QtWidgets.QCheckBox(
            "Sobreescriu els fitxers amb el mateix nom"
        )
        self._overwrite.setChecked(settings.overwrite)
        self._show_before = QtWidgets.QCheckBox(
            "Mostra aquesta finestra abans d'escanejar"
        )
        self._show_before.setChecked(settings.show_before_scan)
        self._open_folder = QtWidgets.QCheckBox(
            "Obre la carpeta d'imatges després d'escanejar"
        )
        self._open_folder.setChecked(settings.open_folder)
        for box in (self._overwrite, self._show_before, self._open_folder):
            layout.addWidget(box)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Tria una carpeta", self._folder.text()
        )
        if folder:
            self._folder.setText(folder)

    def accept(self):
        s = self._settings
        s.folder = self._folder.text()
        s.prefix = self._prefix.text() or "img"
        s.start_number = self._start.value()
        s.format_label = self._format.currentText()
        s.jpeg_quality = self._quality.value()
        s.overwrite = self._overwrite.isChecked()
        s.show_before_scan = self._show_before.isChecked()
        s.open_folder = self._open_folder.isChecked()
        s.multipage_pdf = self._multipage.isChecked()
        super().accept()
