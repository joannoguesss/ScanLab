"""Backend SANE (macOS y Linux). El V500 usa el driver `epson2` (GT-X770)."""

import sane

from scanlab.backends.base import DeviceInfo, ScannerBackend, ScannerDevice, ScannerError
from scanlab.settings import ScanSettings

# Nombres genéricos de ScanLab -> valores que usa el driver epson2.
_MODES = {"color": "Color", "gray": "Gray", "lineart": "Binary"}
_SOURCES = {"flatbed": "Flatbed", "transparency": "Transparency Unit"}

_initialized = False


def _ensure_init():
    global _initialized
    if not _initialized:
        sane.init()
        _initialized = True


class SaneDevice(ScannerDevice):
    def __init__(self, dev):
        self._dev = dev

    def _option(self, name):
        for opt in self._dev.get_options():
            if opt[1] == name:
                return opt
        return None

    def capabilities(self) -> dict:
        caps = {}
        for generic, sane_name in (("modes", "mode"), ("sources", "source")):
            opt = self._option(sane_name)
            caps[generic] = list(opt[8]) if opt and isinstance(opt[8], (list, tuple)) else []
        res = self._option("resolution")
        caps["resolutions"] = res[8] if res else None
        for edge in ("br_x", "br_y"):
            opt = self._option(edge)
            constraint = opt[8] if opt else None
            caps["max_" + edge] = constraint[1] if isinstance(constraint, tuple) else None
        return caps

    def _set(self, name: str, value):
        try:
            setattr(self._dev, name, value)
        except Exception as exc:
            raise ScannerError(f"No se pudo fijar la opción '{name}' = {value!r}: {exc}") from exc

    def scan(self, settings: ScanSettings):
        if settings.mode not in _MODES:
            raise ScannerError(f"Modo desconocido: {settings.mode!r} (usa {list(_MODES)})")
        if settings.source not in _SOURCES:
            raise ScannerError(f"Fuente desconocida: {settings.source!r} (usa {list(_SOURCES)})")

        self._set("mode", _MODES[settings.mode])
        # La unidad de transparencias solo existe si el driver la anuncia.
        source_opt = self._option("source")
        if source_opt and isinstance(source_opt[8], (list, tuple)):
            wanted = _SOURCES[settings.source]
            if wanted not in source_opt[8]:
                raise ScannerError(
                    f"El escáner no ofrece la fuente {wanted!r}; disponibles: {list(source_opt[8])}"
                )
            self._set("source", wanted)
        self._set("resolution", settings.resolution)

        if settings.area:
            x, y, w, h = settings.area
            self._set("tl_x", x)
            self._set("tl_y", y)
            self._set("br_x", x + w)
            self._set("br_y", y + h)

        try:
            return self._dev.scan()
        except Exception as exc:
            raise ScannerError(f"Fallo durante el escaneo: {exc}") from exc

    def close(self) -> None:
        self._dev.close()


class SaneBackend(ScannerBackend):
    def list_devices(self) -> list[DeviceInfo]:
        _ensure_init()
        return [
            DeviceInfo(id=dev_id, vendor=vendor, model=model)
            for dev_id, vendor, model, _kind in sane.get_devices()
        ]

    def open(self, device_id: str) -> SaneDevice:
        _ensure_init()
        try:
            return SaneDevice(sane.open(device_id))
        except Exception as exc:
            raise ScannerError(f"No se pudo abrir {device_id!r}: {exc}") from exc
