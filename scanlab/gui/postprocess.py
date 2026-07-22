"""Ajustes de imagen equivalentes a los de Epson Scan.

El V500 aplica algunos por hardware (Digital ICE usa el canal infrarrojo), pero
ImageCaptureCore no expone esa parte, así que aquí se implementan por software
sobre la imagen escaneada.
"""

from dataclasses import dataclass, field

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

_LEVELS = {"low": 1, "medium": 2, "high": 3}


@dataclass
class Adjustments:
    unsharp_mask: bool = False
    unsharp_level: str = "medium"        # low | medium | high
    descreening: bool = False
    color_restoration: bool = False
    backlight_correction: bool = False
    backlight_level: str = "medium"
    dust_removal: bool = False
    dust_level: str = "medium"
    auto_exposure: bool = False
    text_enhancement: bool = False
    brightness: int = 0                  # -100..100
    contrast: int = 0                    # -100..100
    saturation: int = 0                  # -100..100 (solo color)
    color_balance: tuple[int, int, int] = field(default=(0, 0, 0))  # R,G,B -100..100
    threshold: int = 128                 # 0..255 (solo Blanco y negro)
    apply_threshold: bool = False
    # Histograma: niveles por canal {"master"|"r"|"g"|"b": (negro, blanco, gamma)}
    levels: dict[str, tuple[int, int, float]] | None = None
    # Corrección tonal: LUT maestra de 256 valores (0..255)
    curve_lut: list[int] | None = None


def levels_lut(black: int, white: int, gamma: float) -> list[int]:
    """LUT de niveles estilo histograma de Epson Scan (negro/blanco/gamma)."""
    white = max(white, black + 1)
    lut = []
    for i in range(256):
        v = min(max(i, black), white)
        v = (v - black) / (white - black)
        lut.append(round(255 * v ** (1 / gamma)))
    return lut


def apply_levels(image: Image.Image, levels: dict) -> Image.Image:
    """Aplica niveles de histograma (negro/blanco/gamma por canal) a una imagen."""
    return _apply_levels(image, levels)


def _apply_levels(image: Image.Image, levels: dict) -> Image.Image:
    master = levels.get("master")
    if image.mode in ("RGB", "RGBA"):
        bands = list(image.convert("RGB").split())
        for i, key in enumerate(("r", "g", "b")):
            per_channel = levels.get(key)
            if per_channel:
                bands[i] = bands[i].point(levels_lut(*per_channel))
            if master:
                bands[i] = bands[i].point(levels_lut(*master))
        return Image.merge("RGB", bands)
    if master:
        return image.point(levels_lut(*master) * len(image.getbands()))
    return image


def apply(image: Image.Image, adj: Adjustments) -> Image.Image:
    is_color = image.mode in ("RGB", "RGBA")

    if adj.levels:
        image = _apply_levels(image, adj.levels)
    if adj.curve_lut:
        image = image.point(list(adj.curve_lut) * len(image.getbands()))

    if adj.dust_removal:
        size = {1: 3, 2: 3, 3: 5}[_LEVELS[adj.dust_level]]
        image = image.filter(ImageFilter.MedianFilter(size))

    if adj.descreening:
        image = image.filter(ImageFilter.GaussianBlur(0.8))

    if adj.auto_exposure or adj.color_restoration:
        image = ImageOps.autocontrast(image, cutoff=1)

    if adj.color_restoration and is_color:
        image = ImageEnhance.Color(image).enhance(1.25)

    if adj.backlight_correction:
        gamma = {1: 1.15, 2: 1.35, 3: 1.6}[_LEVELS[adj.backlight_level]]
        lut = [round(255 * (i / 255) ** (1 / gamma)) for i in range(256)]
        image = image.point(lut * len(image.getbands()))

    if adj.brightness:
        image = ImageEnhance.Brightness(image).enhance(1 + adj.brightness / 100)
    if adj.contrast:
        image = ImageEnhance.Contrast(image).enhance(1 + adj.contrast / 100)
    if adj.saturation and is_color:
        image = ImageEnhance.Color(image).enhance(1 + adj.saturation / 100)

    if any(adj.color_balance) and is_color:
        bands = list(image.split())
        for i, delta in enumerate(adj.color_balance):
            if delta:
                bands[i] = ImageEnhance.Brightness(bands[i]).enhance(1 + delta / 200)
        image = Image.merge("RGB", bands[:3])

    if adj.unsharp_mask:
        percent = {1: 80, 2: 130, 3: 200}[_LEVELS[adj.unsharp_level]]
        image = image.filter(ImageFilter.UnsharpMask(radius=2, percent=percent, threshold=2))

    if adj.text_enhancement and not is_color:
        image = ImageOps.autocontrast(image, cutoff=2).filter(
            ImageFilter.UnsharpMask(radius=1, percent=150, threshold=1)
        )

    if adj.apply_threshold:
        image = image.convert("L").point(lambda p: 255 if p >= adj.threshold else 0).convert("1")

    return image
