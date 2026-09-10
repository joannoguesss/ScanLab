"""Windows: prova TWAIN primer i WIA després.

El V500 funciona per TWAIN (és el que fa servir l'Epson Scan); el seu suport
WIA sovint no existeix. Altres escàners moderns només porten WIA, així que
oferim els dos i identifiquem cada aparell amb un prefix.
"""

from scanlab.backends.base import DeviceInfo, ScannerBackend, ScannerDevice, ScannerError


class WindowsBackend(ScannerBackend):
    def __init__(self):
        self._backends = {}
        self.errors: list[str] = []

    def _backend(self, prefix: str) -> ScannerBackend:
        if prefix not in self._backends:
            if prefix == "twain":
                from scanlab.backends.twain_backend import TwainBackend

                self._backends[prefix] = TwainBackend()
            else:
                from scanlab.backends.wia_backend import WiaBackend

                self._backends[prefix] = WiaBackend()
        return self._backends[prefix]

    def list_devices(self) -> list[DeviceInfo]:
        devices = []
        self.errors = []
        for prefix in ("twain", "wia"):
            try:
                for device in self._backend(prefix).list_devices():
                    devices.append(DeviceInfo(
                        id=f"{prefix}:{device.id}",
                        vendor=device.vendor,
                        model=f"{device.model} [{prefix.upper()}]",
                    ))
            except Exception as exc:  # noqa: BLE001 - un camí pot fallar i l'altre no
                self.errors.append(f"{prefix.upper()}: {exc}")
        return devices

    def open(self, device_id: str) -> ScannerDevice:
        prefix, _, real_id = device_id.partition(":")
        if prefix not in ("twain", "wia") or not real_id:
            raise ScannerError(f"Identificador d'escàner desconegut: {device_id!r}")
        return self._backend(prefix).open(real_id)
