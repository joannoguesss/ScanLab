"""Backend ImageCaptureCore (macOS). Requiere el driver ICA de Epson instalado.

ImageCaptureCore es asíncrono (delegados + run loop de Cocoa); aquí se envuelve
en llamadas síncronas bombeando el run loop hasta que llega cada callback.
"""

import os
import tempfile

import Foundation
import ImageCaptureCore as ICC
import objc
from PIL import Image, ImageOps

from scanlab.backends.base import DeviceInfo, ScannerBackend, ScannerDevice, ScannerError
from scanlab.settings import ScanSettings

_FUNCTIONAL_UNITS = {
    "flatbed": ICC.ICScannerFunctionalUnitTypeFlatbed,
    "transparency": ICC.ICScannerFunctionalUnitTypePositiveTransparency,
    "negative": ICC.ICScannerFunctionalUnitTypeNegativeTransparency,
}

_PIXEL_TYPES = {
    "color": (ICC.ICScannerPixelDataTypeRGB, 8),
    "gray": (ICC.ICScannerPixelDataTypeGray, 8),
    "lineart": (ICC.ICScannerPixelDataTypeBW, 1),
}


def _invert(image: Image.Image) -> Image.Image:
    if image.mode in ("RGB", "L"):
        return ImageOps.invert(image)
    if image.mode.startswith("I;16"):
        return image.point(lambda v: 65535 - v)
    return ImageOps.invert(image.convert("RGB"))


def _pump(condition, timeout: float, what: str):
    """Bombea el run loop hasta que condition() sea cierta o venza el timeout."""
    loop = Foundation.NSRunLoop.currentRunLoop()
    deadline = Foundation.NSDate.dateWithTimeIntervalSinceNow_(timeout)
    while not condition():
        if deadline.timeIntervalSinceNow() <= 0:
            raise ScannerError(f"Tiempo agotado esperando: {what}")
        loop.runMode_beforeDate_(
            Foundation.NSDefaultRunLoopMode,
            Foundation.NSDate.dateWithTimeIntervalSinceNow_(0.1),
        )


class _BrowserDelegate(Foundation.NSObject):
    def init(self):
        self = objc.super(_BrowserDelegate, self).init()
        if self is None:
            return None
        self.devices = []
        self.done = False
        return self

    def deviceBrowser_didAddDevice_moreComing_(self, browser, device, more):
        self.devices.append(device)
        if not more:
            self.done = True

    def deviceBrowser_didRemoveDevice_moreGoing_(self, browser, device, more):
        if device in self.devices:
            self.devices.remove(device)


class _ScannerDelegate(Foundation.NSObject):
    def init(self):
        self = objc.super(_ScannerDelegate, self).init()
        if self is None:
            return None
        self.reset()
        return self

    def reset(self):
        self.session_open = False
        self.ready = False
        self.unit_selected = False
        self.scan_done = False
        self.scanned_urls = []
        self.error = None

    def _set_error(self, error):
        if error is not None:
            self.error = str(error.localizedDescription())

    def device_didOpenSessionWithError_(self, device, error):
        self._set_error(error)
        self.session_open = True

    def deviceDidBecomeReady_(self, device):
        self.ready = True

    def device_didCloseSessionWithError_(self, device, error):
        pass

    def device_didEncounterError_(self, device, error):
        self._set_error(error)

    def scannerDevice_didSelectFunctionalUnit_error_(self, scanner, unit, error):
        self._set_error(error)
        self.unit_selected = True

    def scannerDevice_didScanToURL_(self, scanner, url):
        self.scanned_urls.append(url.path())

    def scannerDevice_didCompleteScanWithError_(self, scanner, error):
        self._set_error(error)
        self.scan_done = True


class _Browser:
    """Mantiene vivo el ICDeviceBrowser: si se para, macOS invalida los dispositivos."""

    def __init__(self):
        self._delegate = _BrowserDelegate.alloc().init()
        self._browser = ICC.ICDeviceBrowser.alloc().init()
        self._browser.setDelegate_(self._delegate)
        self._browser.setBrowsedDeviceTypeMask_(
            ICC.ICDeviceTypeMaskScanner | ICC.ICDeviceLocationTypeMaskLocal
        )
        self._browser.start()

    def devices(self, timeout: float = 10.0):
        try:
            _pump(
                lambda: self._delegate.done or self._delegate.devices,
                timeout,
                "detección de escáneres",
            )
        except ScannerError:
            return []  # sin dispositivos
        # Pequeño margen por si llegan más dispositivos en tanda.
        Foundation.NSRunLoop.currentRunLoop().runMode_beforeDate_(
            Foundation.NSDefaultRunLoopMode,
            Foundation.NSDate.dateWithTimeIntervalSinceNow_(0.5),
        )
        return list(self._delegate.devices)


class IcaDevice(ScannerDevice):
    def __init__(self, device):
        self._device = device
        self._delegate = _ScannerDelegate.alloc().init()
        device.setDelegate_(self._delegate)
        device.requestOpenSession()
        _pump(lambda: self._delegate.session_open, 30, "apertura de sesión con el escáner")
        self._raise_if_error()
        _pump(lambda: self._delegate.ready, 30, "escáner listo")

    def _raise_if_error(self):
        if self._delegate.error:
            err, self._delegate.error = self._delegate.error, None
            raise ScannerError(err)

    def _unit(self):
        return self._device.selectedFunctionalUnit()

    def capabilities(self) -> dict:
        unit = self._unit()
        # Se compactan los valores contiguos en rangos (min, max): el V500
        # anuncia todos los enteros de 50 a 6400.
        resolutions = []
        idx_set = unit.supportedResolutions()
        idx = idx_set.firstIndex()
        run_start = None
        prev = None
        while idx != Foundation.NSNotFound:
            value = int(idx)
            if run_start is None:
                run_start = value
            elif value != prev + 1:
                resolutions.append((run_start, prev) if run_start != prev else run_start)
                run_start = value
            prev = value
            idx = idx_set.indexGreaterThanIndex_(idx)
        if run_start is not None:
            resolutions.append((run_start, prev) if run_start != prev else run_start)
        available = [int(t) for t in self._device.availableFunctionalUnitTypes()]
        units = [name for name, t in _FUNCTIONAL_UNITS.items() if t in available]
        size = unit.physicalSize()
        return {
            "modes": list(_PIXEL_TYPES),
            "sources": units,
            "resolutions": resolutions,
            "physical_size": (float(size.width), float(size.height)),
            "measurement_unit": int(unit.measurementUnit()),
        }

    def _select_unit(self, source: str):
        wanted = _FUNCTIONAL_UNITS[source]
        if int(self._unit().type()) == int(wanted):
            return
        available = [int(t) for t in self._device.availableFunctionalUnitTypes()]
        if int(wanted) not in available:
            raise ScannerError(f"El escáner no ofrece la fuente {source!r}")
        self._delegate.unit_selected = False
        self._device.requestSelectFunctionalUnit_(wanted)
        _pump(lambda: self._delegate.unit_selected, 30, f"selección de fuente {source!r}")
        self._raise_if_error()

    def scan(self, settings: ScanSettings) -> Image.Image:
        if settings.mode not in _PIXEL_TYPES:
            raise ScannerError(f"Modo desconocido: {settings.mode!r} (usa {list(_PIXEL_TYPES)})")
        if settings.source not in _FUNCTIONAL_UNITS:
            raise ScannerError(
                f"Fuente desconocida: {settings.source!r} (usa {list(_FUNCTIONAL_UNITS)})"
            )
        self._select_unit(settings.source)
        unit = self._unit()

        supported = unit.supportedResolutions()
        dpi = settings.resolution
        if not supported.containsIndex_(dpi):
            near = supported.indexGreaterThanOrEqualToIndex_(dpi)
            if near == Foundation.NSNotFound:
                near = supported.lastIndex()
            dpi = int(near)
        unit.setResolution_(dpi)

        pixel_type, bit_depth = _PIXEL_TYPES[settings.mode]
        if settings.mode in ("color", "gray") and settings.depth == 16:
            bit_depth = 16
        unit.setPixelDataType_(pixel_type)
        unit.setBitDepth_(bit_depth)

        unit.setMeasurementUnit_(ICC.ICScannerMeasurementUnitInches)
        physical = unit.physicalSize()
        if settings.area:
            x, y, w, h = (v / 25.4 for v in settings.area)  # mm -> pulgadas
        else:
            x, y, w, h = 0.0, 0.0, float(physical.width), float(physical.height)
        unit.setScanArea_(Foundation.NSMakeRect(x, y, w, h))

        out_dir = tempfile.mkdtemp(prefix="scanlab_")
        self._device.setTransferMode_(ICC.ICScannerTransferModeFileBased)
        self._device.setDownloadsDirectory_(Foundation.NSURL.fileURLWithPath_(out_dir))
        self._device.setDocumentName_("scanlab")
        self._device.setDocumentUTI_("public.tiff")

        self._delegate.scan_done = False
        self._delegate.scanned_urls = []
        self._device.requestScan()
        _pump(lambda: self._delegate.scan_done, 600, "escaneo")
        self._raise_if_error()
        if not self._delegate.scanned_urls:
            raise ScannerError("El escaneo terminó pero no produjo ningún archivo.")

        path = self._delegate.scanned_urls[-1]
        image = Image.open(path)
        image.load()
        os.remove(path)
        if settings.source == "negative":
            # El driver ICA no invierte los negativos; lo hacemos aquí para que
            # previsualización y escaneo salgan ya en positivo.
            image = _invert(image)
        return image

    def close(self) -> None:
        self._device.requestCloseSession()


class IcaBackend(ScannerBackend):
    def __init__(self):
        self._devices = {}
        self._browser = _Browser()

    def list_devices(self) -> list[DeviceInfo]:
        devices = self._browser.devices()
        infos = []
        for dev in devices:
            dev_id = str(dev.persistentIDString() or dev.name())
            self._devices[dev_id] = dev
            infos.append(DeviceInfo(id=dev_id, vendor="", model=str(dev.name())))
        return infos

    def open(self, device_id: str) -> IcaDevice:
        if device_id not in self._devices:
            self.list_devices()
        if device_id not in self._devices:
            raise ScannerError(f"No se encuentra el escáner {device_id!r}")
        return IcaDevice(self._devices[device_id])
