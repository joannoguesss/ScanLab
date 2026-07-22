"""Contrato que debe cumplir cada backend de escaneo (SANE, WIA...)."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from PIL import Image

from scanlab.settings import ScanSettings


class ScannerError(Exception):
    """Error de comunicación o configuración con el escáner."""


@dataclass
class DeviceInfo:
    id: str
    vendor: str
    model: str


class ScannerDevice(ABC):
    @abstractmethod
    def capabilities(self) -> dict:
        """Opciones soportadas: resoluciones, modos, fuentes, tamaño de cama."""

    @abstractmethod
    def scan(self, settings: ScanSettings) -> Image.Image:
        """Ejecuta un escaneo y devuelve la imagen."""

    @abstractmethod
    def close(self) -> None: ...

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class ScannerBackend(ABC):
    @abstractmethod
    def list_devices(self) -> list[DeviceInfo]: ...

    @abstractmethod
    def open(self, device_id: str) -> ScannerDevice: ...
