"""Backend TWAIN per a Windows (el mateix camí que fa servir l'Epson Scan).

El V500 no ofereix un driver WIA que funcioni: l'Epson Scan parla amb
l'escàner per TWAIN. Aquest backend fa el mateix amb pytwain.

L'API de pytwain ha canviat de noms entre versions (CamelCase antic vs
snake_case nou), així que totes les crides passen per `_call`, que prova els
noms possibles.
"""

import logging
import os
import tempfile

from PIL import Image, ImageOps

from scanlab.backends.base import DeviceInfo, ScannerBackend, ScannerDevice, ScannerError
from scanlab.settings import ScanSettings

# Valors TWAIN que necessitem (per si la versió de pytwain no els exporta).
_TWPT = {"lineart": 0, "gray": 1, "color": 2}   # TWPT_BW / TWPT_GRAY / TWPT_RGB
_TWPT_NAMES = {"lineart": "TWPT_BW", "gray": "TWPT_GRAY", "color": "TWPT_RGB"}
_TWUN_INCHES = 0
_TWLP_REFLECTIVE = 0
_TWLP_TRANSMISSIVE = 1


def _twain_module():
    try:
        import twain
    except ImportError as exc:
        raise ScannerError(
            "Falta el paquet pytwain (pip install pytwain) per parlar amb el "
            "driver de l'Epson."
        ) from exc
    # pytwain escriu els seus errors a stderr; els recollim nosaltres amb més
    # context, així que el silenciem per no embrutar el registre.
    logging.getLogger("twain").setLevel(logging.CRITICAL)
    return twain


def _call(obj, names, *args, **kwargs):
    """Crida el primer mètode que existeixi d'entre `names`."""
    for name in names:
        method = getattr(obj, name, None)
        if callable(method):
            return method(*args, **kwargs)
    raise ScannerError(
        f"La versió de pytwain instal·lada no té cap d'aquests mètodes: "
        f"{', '.join(names)}"
    )


def _const(twain, name, default):
    value = getattr(twain, name, None)
    return default if value is None else value


def _dsm_candidates() -> list[dict]:
    """Gestors TWAIN (DSM) a provar, en ordre.

    A 64 bits pytwain busca `twaindsm.dll`, que Windows NO porta i s'ha
    d'instal·lar a part. El clàssic `twain_32.dll` sí que ve amb Windows, però
    només es pot carregar des d'un procés de 32 bits (per això ScanLab porta
    l'ajudant `ScanLab-worker32.exe`).
    """
    candidates: list[dict] = [{}]  # heurística de pytwain
    windir = os.environ.get("WINDIR")
    if windir:
        candidates.append({"dsm_name": os.path.join(windir, "twain_32.dll")})
    return candidates


def _source_manager(twain):
    errors = []
    for kwargs in _dsm_candidates():
        for args in ((0,), ()):
            try:
                return twain.SourceManager(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001 - volem el motiu exacte
                detail = str(exc)
                if detail not in errors:
                    errors.append(detail)
    hint = ""
    if any("twaindsm" in e.lower() for e in errors):
        hint = (" Aquest procés és de 64 bits i Windows no porta twaindsm.dll; "
                "ScanLab hauria de fer servir l'ajudant de 32 bits.")
    raise ScannerError(
        "No s'ha pogut iniciar TWAIN." + hint + " Detalls: " + " | ".join(errors)
    )


def _source_names(sm):
    try:
        names = getattr(sm, "source_list", None)
    except Exception:  # noqa: BLE001 - la propietat pot petar segons la versió
        names = None
    if names is None:
        names = _call(sm, ("GetSourceList", "get_source_list"))
    return [str(n) for n in names]


class TwainDevice(ScannerDevice):
    def __init__(self, source, manager, twain):
        self._source = source
        self._manager = manager
        self._twain = twain

    # --- utilitats ---

    def _set_cap(self, cap_name, type_name, value, required=True):
        twain = self._twain
        cap = getattr(twain, cap_name, None)
        if cap is None:
            if required:
                raise ScannerError(f"Aquesta versió de pytwain no coneix {cap_name}.")
            return False
        cap_type = getattr(twain, type_name, None)
        try:
            _call(self._source, ("set_capability", "SetCapability"),
                  cap, cap_type, value)
            return True
        except Exception as exc:  # noqa: BLE001
            if required:
                raise ScannerError(
                    f"El driver no accepta {cap_name} = {value!r}: {exc}"
                ) from exc
            return False

    def capabilities(self) -> dict:
        return {
            "modes": list(_TWPT),
            "sources": ["flatbed", "transparency", "negative"],
            "resolutions": (50, 12800),
            "note": (
                "Via TWAIN (driver Epson Scan). El mode pel·lícula depèn del "
                "driver: si falla, escaneja des de l'Epson Scan original."
            ),
        }

    # --- escaneig ---

    def scan(self, settings: ScanSettings) -> Image.Image:
        twain = self._twain
        if settings.mode not in _TWPT:
            raise ScannerError(f"Mode desconegut: {settings.mode!r}")

        # Unitats en polzades perquè l'àrea i la resolució siguin coherents.
        self._set_cap("ICAP_UNITS", "TWTY_UINT16",
                      _const(twain, "TWUN_INCHES", _TWUN_INCHES), required=False)

        pixel_type = _const(twain, _TWPT_NAMES[settings.mode], _TWPT[settings.mode])
        self._set_cap("ICAP_PIXELTYPE", "TWTY_UINT16", pixel_type)
        self._set_cap("ICAP_XRESOLUTION", "TWTY_FIX32", float(settings.resolution))
        self._set_cap("ICAP_YRESOLUTION", "TWTY_FIX32", float(settings.resolution))
        if settings.mode in ("color", "gray"):
            self._set_cap("ICAP_BITDEPTH", "TWTY_UINT16",
                          16 if settings.depth == 16 else 8, required=False)

        if settings.source != "flatbed":
            light_path = _const(twain, "TWLP_TRANSMISSIVE", _TWLP_TRANSMISSIVE)
            if not self._set_cap("CAP_LIGHTPATH", "TWTY_UINT16", light_path,
                                 required=False):
                raise ScannerError(
                    "Aquest driver TWAIN no permet la unitat de transparències. "
                    "Escaneja la pel·lícula amb l'Epson Scan original."
                )
        else:
            self._set_cap("CAP_LIGHTPATH", "TWTY_UINT16",
                          _const(twain, "TWLP_REFLECTIVE", _TWLP_REFLECTIVE),
                          required=False)

        if settings.area:
            x, y, w, h = (v / 25.4 for v in settings.area)  # mm -> polzades
            try:
                _call(self._source, ("set_image_layout", "SetImageLayout"),
                      (x, y, x + w, y + h))
            except Exception as exc:  # noqa: BLE001
                raise ScannerError(
                    f"El driver no accepta l'àrea seleccionada: {exc}"
                ) from exc

        # Decidim el mecanisme de transferència ABANS d'escanejar: cada
        # `request_acquire` mou el carro, no volem escanejar dos cops.
        path, file_format = self._prepare_file_transfer()

        try:
            _call(self._source, ("request_acquire", "RequestAcquire"), 0, 0)
        except Exception as exc:  # noqa: BLE001
            raise ScannerError(f"El driver no ha pogut iniciar l'escaneig: {exc}") from exc

        if file_format is not None:
            image = self._transfer_to_file(path)
        else:
            image = self._transfer_natively()

        if settings.source == "negative":
            image = ImageOps.invert(image.convert("RGB"))
        return image

    def _prepare_file_transfer(self):
        """Configura la transferència a fitxer; retorna (ruta, format) o (None, None)."""
        twain = self._twain
        xfermech = getattr(twain, "ICAP_XFERMECH", None)
        file_mech = getattr(twain, "TWSX_FILE", 1)
        if xfermech is None:
            return None, None
        for fmt_name, suffix in (("TWFF_TIFF", ".tif"), ("TWFF_BMP", ".bmp")):
            fmt = getattr(twain, fmt_name, None)
            if fmt is None:
                continue
            path = tempfile.mktemp(prefix="scanlab_twain_", suffix=suffix)
            try:
                _call(self._source, ("set_capability", "SetCapability"),
                      xfermech, getattr(twain, "TWTY_UINT16", None), file_mech)
                try:
                    self._source.file_xfer_params = (path, fmt)
                except Exception:  # noqa: BLE001
                    _call(self._source, ("SetXferFileName", "set_xfer_file_name"),
                          path, fmt)
                return path, fmt
            except Exception:  # noqa: BLE001 - provem el format següent
                continue
        # Sense transferència a fitxer: tornem a mode natiu (memòria).
        try:
            _call(self._source, ("set_capability", "SetCapability"),
                  xfermech, getattr(twain, "TWTY_UINT16", None),
                  getattr(twain, "TWSX_NATIVE", 0))
        except Exception:  # noqa: BLE001
            pass
        return None, None

    def _transfer_to_file(self, path: str) -> Image.Image:
        try:
            _call(self._source, ("xfer_image_by_file", "XferImageByFile"))
        except Exception as exc:  # noqa: BLE001
            raise ScannerError(f"Error en transferir la imatge: {exc}") from exc
        if not os.path.exists(path):
            raise ScannerError("El driver no ha escrit cap imatge.")
        image = Image.open(path)
        image.load()
        os.remove(path)
        return image

    def _transfer_natively(self) -> Image.Image:
        twain = self._twain
        try:
            result = _call(self._source, ("xfer_image_natively", "XferImageNatively"))
        except Exception as exc:  # noqa: BLE001
            raise ScannerError(f"Error en transferir la imatge: {exc}") from exc
        handle = result[0] if isinstance(result, tuple) else result
        path = tempfile.mktemp(prefix="scanlab_twain_", suffix=".bmp")
        try:
            _call(twain, ("dib_to_bm_file", "DIBToBMFile"), handle, path)
        finally:
            try:
                _call(twain, ("global_handle_free", "GlobalHandleFree"), handle)
            except Exception:  # noqa: BLE001
                pass
        image = Image.open(path)
        image.load()
        os.remove(path)
        return image

    def close(self) -> None:
        for obj in (self._source, self._manager):
            try:
                if obj is not None:
                    _call(obj, ("close", "destroy", "Destroy"))
            except Exception:  # noqa: BLE001 - tancar mai ha de petar
                pass
        self._source = None
        self._manager = None


class TwainBackend(ScannerBackend):
    def list_devices(self) -> list[DeviceInfo]:
        twain = _twain_module()
        sm = _source_manager(twain)
        try:
            names = _source_names(sm)
        finally:
            try:
                _call(sm, ("close", "destroy", "Destroy"))
            except Exception:  # noqa: BLE001
                pass
        return [DeviceInfo(id=name, vendor="", model=name) for name in names]

    def open(self, device_id: str) -> TwainDevice:
        twain = _twain_module()
        sm = _source_manager(twain)
        try:
            source = _call(sm, ("open_source", "OpenSource"), device_id)
        except Exception as exc:  # noqa: BLE001
            try:
                _call(sm, ("close", "destroy", "Destroy"))
            except Exception:  # noqa: BLE001
                pass
            raise ScannerError(f"No s'ha pogut obrir {device_id!r}: {exc}") from exc
        if source is None:
            raise ScannerError(f"El driver no ha obert {device_id!r}.")
        return TwainDevice(source, sm, twain)
