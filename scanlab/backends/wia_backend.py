"""Backend WIA per a Windows (Windows Image Acquisition, via COM).

Requereix el driver oficial d'Epson per al V500 instal·lat (l'«Epson Scan»
de Windows instal·la també el driver WIA). Dependència: pywin32.
"""

import os
import tempfile

from PIL import Image, ImageOps

from scanlab.backends.base import DeviceInfo, ScannerBackend, ScannerDevice, ScannerError
from scanlab.settings import ScanSettings

# Identificadors de propietats WIA (Windows Image Acquisition 2.0)
WIA_INTENT = "6146"          # 1 color, 2 grisos, 4 text/B-N
WIA_DPI_X = "6147"
WIA_DPI_Y = "6148"
WIA_START_X = "6149"         # en píxels a la resolució triada
WIA_START_Y = "6150"
WIA_EXTENT_X = "6151"
WIA_EXTENT_Y = "6152"
WIA_BIT_DEPTH = "4104"
WIA_DOC_HANDLING = "3088"    # 2 = pla; els valors de transparències depenen del driver

FORMAT_BMP = "{B96B3CAB-0728-11D3-9D7B-0000F81EF32E}"

_INTENTS = {"color": 1, "gray": 2, "lineart": 4}

_PROP_NAMES = {
    WIA_INTENT: "el tipus d'imatge",
    WIA_DPI_X: "la resolució horitzontal",
    WIA_DPI_Y: "la resolució vertical",
    WIA_START_X: "l'inici horitzontal de l'àrea",
    WIA_START_Y: "l'inici vertical de l'àrea",
    WIA_EXTENT_X: "l'amplada de l'àrea",
    WIA_EXTENT_Y: "l'alçada de l'àrea",
    WIA_BIT_DEPTH: "la profunditat de color",
}

_SCANNER_DEVICE_TYPE = 1


def _com():
    try:
        import pythoncom
        import win32com.client
    except ImportError as exc:
        raise ScannerError(
            "El backend WIA necessita pywin32 (pip install pywin32)."
        ) from exc
    pythoncom.CoInitialize()
    return win32com.client


class WiaDevice(ScannerDevice):
    def __init__(self, device, client):
        self._device = device
        self._client = client

    def _item(self):
        return self._device.Items(1)

    @staticmethod
    def _set(properties, prop_id: str, value, required=True) -> bool:
        """Fixa una propietat WIA. Amb `required=False` no falla si el driver
        no la deixa escriure (moltes són de només lectura segons el model)."""
        try:
            properties(prop_id).Value = value
            return True
        except Exception as exc:
            if not required:
                return False
            name = _PROP_NAMES.get(prop_id, prop_id)
            raise ScannerError(
                f"El driver no accepta {name} = {value!r}: {exc}"
            ) from exc

    def capabilities(self) -> dict:
        return {
            "modes": list(_INTENTS),
            "sources": ["flatbed"],
            "resolutions": (50, 6400),
            "note": (
                "Amb WIA el mode transparències/negatius depèn del driver; "
                "si falla, fes servir l'Epson Scan de Windows per a pel·lícula."
            ),
        }

    def scan(self, settings: ScanSettings) -> Image.Image:
        if settings.mode not in _INTENTS:
            raise ScannerError(f"Mode desconegut: {settings.mode!r}")
        item = self._item()
        props = item.Properties

        self._set(props, WIA_INTENT, _INTENTS[settings.mode])
        self._set(props, WIA_DPI_X, settings.resolution)
        self._set(props, WIA_DPI_Y, settings.resolution)
        if settings.mode == "color":
            # Molts drivers (el de l'Epson entre ells) la deriven del tipus
            # d'imatge i no la deixen escriure: si falla, no passa res.
            self._set(props, WIA_BIT_DEPTH, 48 if settings.depth == 16 else 24,
                      required=False)

        if settings.source != "flatbed":
            # Molts drivers WIA no exposen la unitat de transparències; ho
            # intentem i, si no, avisem clarament.
            try:
                self._device.Properties(WIA_DOC_HANDLING).Value = 0x40  # TRANSPARENCY
            except Exception as exc:
                raise ScannerError(
                    "Aquest driver WIA no permet escanejar pel·lícula; "
                    "prova-ho amb el flatbed o amb l'Epson Scan original."
                ) from exc

        if settings.area:
            x, y, w, h = settings.area
            to_px = settings.resolution / 25.4
            self._set(props, WIA_START_X, round(x * to_px))
            self._set(props, WIA_START_Y, round(y * to_px))
            self._set(props, WIA_EXTENT_X, round(w * to_px))
            self._set(props, WIA_EXTENT_Y, round(h * to_px))

        try:
            wia_image = item.Transfer(FORMAT_BMP)
        except Exception:
            # Alguns drivers només transfereixen via el diàleg comú de WIA.
            try:
                dialog = self._client.Dispatch("WIA.CommonDialog")
                wia_image = dialog.ShowTransfer(item, FORMAT_BMP)
            except Exception as exc:
                raise ScannerError(f"Error durant l'escaneig WIA: {exc}") from exc
        if wia_image is None:
            raise ScannerError("El driver WIA no ha retornat cap imatge.")

        path = tempfile.mktemp(suffix=".bmp", prefix="scanlab_wia_")
        wia_image.SaveFile(path)
        image = Image.open(path)
        image.load()
        os.remove(path)
        if settings.source == "negative":
            image = ImageOps.invert(image.convert("RGB"))
        return image

    def close(self) -> None:
        self._device = None


class WiaBackend(ScannerBackend):
    def __init__(self):
        self._infos = {}
        self._client = None

    def list_devices(self) -> list[DeviceInfo]:
        client = _com()
        self._client = client
        try:
            manager = client.Dispatch("WIA.DeviceManager")
            infos = manager.DeviceInfos
        except Exception as exc:
            raise ScannerError(f"No s'ha pogut obrir el gestor WIA: {exc}") from exc
        devices = []
        # Les col·leccions WIA són COM 1-indexades; no sempre són iterables
        # directament des de win32com, així que fem servir Count + índex.
        for i in range(1, int(infos.Count) + 1):
            info = infos(i)
            try:
                if int(info.Type) != _SCANNER_DEVICE_TYPE:
                    continue
            except Exception:
                pass  # si Type falla, l'incloem igualment

            def _prop(name, default=""):
                try:
                    return str(info.Properties(name).Value)
                except Exception:
                    return default

            device_id = str(info.DeviceID)
            self._infos[device_id] = info
            devices.append(DeviceInfo(
                id=device_id,
                vendor=_prop("Manufacturer"),
                model=_prop("Name", "Escàner WIA"),
            ))
        return devices

    def open(self, device_id: str) -> WiaDevice:
        if device_id not in self._infos:
            self.list_devices()
        if device_id not in self._infos:
            raise ScannerError(f"No es troba l'escàner {device_id!r}")
        try:
            return WiaDevice(self._infos[device_id].Connect(), self._client)
        except Exception as exc:
            text = str(exc).lower()
            if "ocupado" in text or "busy" in text or "ocupat" in text:
                raise ScannerError(
                    "L'escàner està ocupat: tanca l'Epson Scan (o el programa "
                    "que l'estigui fent servir) i torna-ho a provar."
                ) from exc
            raise ScannerError(f"No s'ha pogut obrir {device_id!r}: {exc}") from exc
