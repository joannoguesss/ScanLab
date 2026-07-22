"""Parámetros de escaneo comunes a todos los backends."""

from dataclasses import dataclass


@dataclass
class ScanSettings:
    resolution: int = 300          # dpi
    mode: str = "color"            # color | gray | lineart
    source: str = "flatbed"        # flatbed | transparency | negative
    depth: int = 8                 # bits por canal (8 o 16; en lineart se ignora)
    # Área en mm (x, y, ancho, alto) desde la esquina superior izquierda.
    # None = cama completa.
    area: tuple[float, float, float, float] | None = None
