"""Executa els escaneigs en un procés a part per no congelar la interfície.

En mode desenvolupament es reutilitza la CLI (`python -m scanlab …`); dins
d'una app empaquetada amb PyInstaller ens rellancem a nosaltres mateixos amb
`--scan-worker`. La sortida del procés es desa a un registre per poder
diagnosticar errors (config.LOG_PATH).
"""

import os
import sys
import tempfile
import time

from PySide6 import QtCore

from scanlab.gui import config
from scanlab.settings import ScanSettings

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def worker_command(cli_args: list[str]) -> tuple[str, list[str], str]:
    """(programa, arguments, directori de treball) per al procés d'escaneig."""
    if getattr(sys, "frozen", False):
        return sys.executable, ["--scan-worker"] + cli_args, ""
    return sys.executable, ["-m", "scanlab"] + cli_args, _PROJECT_ROOT


def _log(text: str):
    try:
        os.makedirs(os.path.dirname(config.LOG_PATH), exist_ok=True)
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(config.LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(f"\n--- {stamp} ---\n{text}\n")
    except OSError:
        pass


class ScanRunner(QtCore.QObject):
    finished = QtCore.Signal(str)   # ruta del TIFF temporal escanejat
    failed = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._process: QtCore.QProcess | None = None
        self._output = ""
        self.last_output = ""  # sortida completa de l'últim procés (per a diàlegs)

    def busy(self) -> bool:
        return (
            self._process is not None
            and self._process.state() != QtCore.QProcess.NotRunning
        )

    def scan(self, settings: ScanSettings):
        if self.busy():
            self.failed.emit("Ja hi ha un escaneig en curs.")
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
        program, args, workdir = worker_command(scan_args)
        process = QtCore.QProcess(self)
        if workdir:
            process.setWorkingDirectory(workdir)
        process.setProcessChannelMode(QtCore.QProcess.MergedChannels)
        process.finished.connect(self._on_finished)
        process.errorOccurred.connect(self._on_error)
        self._process = process
        process.start(program, args)

    def _on_error(self, error):
        if error == QtCore.QProcess.FailedToStart:
            message = "No s'ha pogut iniciar el procés d'escaneig."
            _log(message)
            self.last_output = message
            self.failed.emit(message)

    def _on_finished(self, code, _status):
        output = bytes(self._process.readAllStandardOutput()).decode(errors="replace")
        self.last_output = output
        _log(f"exit={code}\n{output.strip()}")
        if code == 0 and os.path.exists(self._output):
            self.finished.emit(self._output)
        else:
            lines = [l for l in output.strip().splitlines() if l.strip()]
            detail = lines[-1] if lines else f"codi {code}"
            self.failed.emit(detail)
