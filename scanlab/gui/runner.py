"""Ejecuta los escaneos en un proceso aparte para no congelar la interfaz.

Se reutiliza la CLI (`python -m scanlab scan …`), que ya está probada; además
así el run loop de Cocoa del escáner no se mezcla con el de Qt.
"""

import os
import sys
import tempfile

from PySide6 import QtCore

from scanlab.settings import ScanSettings

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class ScanRunner(QtCore.QObject):
    finished = QtCore.Signal(str)   # ruta del TIFF temporal escaneado
    failed = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._process: QtCore.QProcess | None = None
        self._output = ""

    def busy(self) -> bool:
        return (
            self._process is not None
            and self._process.state() != QtCore.QProcess.NotRunning
        )

    def scan(self, settings: ScanSettings):
        if self.busy():
            self.failed.emit("Ya hay un escaneo en curso.")
            return
        self._output = tempfile.mktemp(suffix=".tiff", prefix="scanlab_gui_")
        scan_args = [
            "scan",
            "-o", self._output,
            "--dpi", str(settings.resolution),
            "--mode", settings.mode,
            "--source", settings.source,
            "--depth", str(settings.depth),
        ]
        if settings.area:
            scan_args += ["--area"] + [f"{v:.2f}" for v in settings.area]
        if getattr(sys, "frozen", False):
            # App empaquetada (PyInstaller): ens rellancem a nosaltres mateixos.
            args = ["--scan-worker"] + scan_args
        else:
            args = ["-m", "scanlab"] + scan_args
        process = QtCore.QProcess(self)
        process.setWorkingDirectory(_PROJECT_ROOT)
        process.setProcessChannelMode(QtCore.QProcess.MergedChannels)
        process.finished.connect(self._on_finished)
        self._process = process
        process.start(sys.executable, args)

    def _on_finished(self, code, _status):
        output = bytes(self._process.readAllStandardOutput()).decode(errors="replace")
        if code == 0 and os.path.exists(self._output):
            self.finished.emit(self._output)
        else:
            detail = output.strip().splitlines()[-1] if output.strip() else f"código {code}"
            self.failed.emit(detail)
