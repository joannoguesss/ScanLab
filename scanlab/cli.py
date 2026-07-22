"""CLI de ScanLab: permite probar el núcleo sin interfaz gráfica.

    python -m scanlab list
    python -m scanlab caps [--device ID]
    python -m scanlab scan -o salida.jpg [--dpi 300] [--mode color] [--source flatbed]
    python -m scanlab preview -o preview.jpg
"""

import argparse
import sys

from scanlab.backends import get_backend
from scanlab.backends.base import ScannerError
from scanlab.settings import ScanSettings


def _pick_device(backend, device_id: str | None):
    if device_id:
        return device_id
    devices = backend.list_devices()
    if not devices:
        raise ScannerError(
            "No se detecta ningún escáner. Comprueba que está conectado y encendido."
        )
    return devices[0].id


def main(argv=None):
    parser = argparse.ArgumentParser(prog="scanlab", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="Lista los escáneres detectados")

    caps = sub.add_parser("caps", help="Muestra las capacidades del escáner")
    caps.add_argument("--device")

    for name, dpi in (("scan", 300), ("preview", 75)):
        p = sub.add_parser(name)
        p.add_argument("-o", "--output", required=True, help="Archivo de salida (jpg/png/tiff)")
        p.add_argument("--device")
        p.add_argument("--dpi", type=int, default=dpi)
        p.add_argument("--mode", default="color", choices=["color", "gray", "lineart"])
        p.add_argument(
            "--source", default="flatbed", choices=["flatbed", "transparency", "negative"]
        )
        p.add_argument("--depth", type=int, default=8, choices=[8, 16])
        p.add_argument(
            "--area", type=float, nargs=4, metavar=("X", "Y", "ANCHO", "ALTO"),
            help="Área en mm desde la esquina superior izquierda",
        )

    args = parser.parse_args(argv)
    backend = get_backend()

    try:
        if args.command == "list":
            devices = backend.list_devices()
            if not devices:
                print("No se detecta ningún escáner.")
                return 1
            for dev in devices:
                print(f"{dev.id}\t{dev.vendor} {dev.model}")
            return 0

        device_id = _pick_device(backend, args.device)

        if args.command == "caps":
            import json

            with backend.open(device_id) as dev:
                print(json.dumps(dev.capabilities()))
            return 0

        settings = ScanSettings(
            resolution=args.dpi,
            mode=args.mode,
            source=args.source,
            depth=args.depth,
            area=tuple(args.area) if args.area else None,
        )
        with backend.open(device_id) as dev:
            print(f"Escaneando a {settings.resolution} dpi ({settings.mode})...")
            image = dev.scan(settings)
        image.save(args.output)
        print(f"Guardado: {args.output} ({image.width}x{image.height}px)")
        return 0

    except ScannerError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
