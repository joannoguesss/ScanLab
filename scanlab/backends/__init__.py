"""Selección del backend según el sistema operativo."""

import sys

from scanlab.backends.base import ScannerBackend


def get_backend() -> ScannerBackend:
    if sys.platform == "win32":
        # TWAIN (el camí de l'Epson Scan) i, si no, WIA.
        from scanlab.backends.windows_backend import WindowsBackend

        return WindowsBackend()
    if sys.platform == "darwin":
        # El V500 no funciona con el backend libre de SANE (protocolo ESC/I-2);
        # en macOS usamos ImageCaptureCore con el driver ICA oficial de Epson.
        from scanlab.backends.ica_backend import IcaBackend

        return IcaBackend()
    from scanlab.backends.sane_backend import SaneBackend

    return SaneBackend()
