"""Informe de diagnòstic: què veu ScanLab del sistema i de l'escàner.

Serveix per enganxar-lo a un informe d'error. No llança mai excepcions: si
alguna comprovació falla, el motiu forma part de l'informe.
"""

import platform
import struct
import sys

import scanlab


def _section(lines, title):
    lines.append("")
    lines.append(f"== {title} ==")


def _twain_section(lines):
    _section(lines, "TWAIN (el camí que fa servir l'Epson Scan)")
    try:
        import twain
    except Exception as exc:  # noqa: BLE001
        lines.append(f"pytwain NO disponible: {exc}")
        return
    lines.append(f"pytwain: {getattr(twain, '__version__', 'versió desconeguda')}")
    try:
        from scanlab.backends.twain_backend import _source_manager, _source_names

        sm = _source_manager(twain)
        try:
            names = _source_names(sm)
            lines.append(f"Fonts TWAIN trobades: {len(names)}")
            for name in names:
                lines.append(f"  - {name}")
            if not names:
                lines.append(
                    "  (cap: instal·la l'Epson Scan, o el driver és de 32 bits "
                    "i aquest ScanLab és de 64)"
                )
        finally:
            try:
                sm.close()
            except Exception:  # noqa: BLE001
                pass
    except Exception as exc:  # noqa: BLE001
        lines.append(f"Error en llistar fonts TWAIN: {exc}")


def _wia_section(lines):
    _section(lines, "WIA (sistema d'escaneig de Windows)")
    try:
        import pythoncom
        import win32com.client
    except Exception as exc:  # noqa: BLE001
        lines.append(f"pywin32 NO disponible: {exc}")
        return
    try:
        pythoncom.CoInitialize()
        manager = win32com.client.Dispatch("WIA.DeviceManager")
        infos = manager.DeviceInfos
        total = int(infos.Count)
        lines.append(f"Aparells WIA: {total}")
        for i in range(1, total + 1):
            info = infos(i)
            try:
                name = str(info.Properties("Name").Value)
            except Exception:  # noqa: BLE001
                name = "(sense nom)"
            try:
                kind = int(info.Type)
            except Exception:  # noqa: BLE001
                kind = -1
            lines.append(f"  - {name} (tipus {kind}; 1 = escàner)")
        if total == 0:
            lines.append("  (cap: el driver WIA no està instal·lat o no el dona)")
    except Exception as exc:  # noqa: BLE001
        lines.append(f"Error en consultar WIA: {exc}")


def _sane_section(lines):
    _section(lines, "SANE")
    try:
        import sane

        sane.init()
        devices = sane.get_devices()
        lines.append(f"Aparells SANE: {len(devices)}")
        for dev in devices:
            lines.append(f"  - {dev}")
    except Exception as exc:  # noqa: BLE001
        lines.append(f"SANE no disponible: {exc}")


def _ica_section(lines):
    _section(lines, "ImageCaptureCore (macOS)")
    try:
        from scanlab.backends.ica_backend import IcaBackend

        devices = IcaBackend().list_devices()
        lines.append(f"Escàners trobats: {len(devices)}")
        for dev in devices:
            lines.append(f"  - {dev.model} ({dev.id})")
    except Exception as exc:  # noqa: BLE001
        lines.append(f"Error: {exc}")


def report() -> str:
    lines = [f"ScanLab {scanlab.__version__} — informe de diagnòstic"]
    _section(lines, "Sistema")
    lines.append(f"Plataforma: {platform.platform()}")
    lines.append(f"Python: {sys.version.split()[0]} "
                 f"({struct.calcsize('P') * 8} bits)")
    lines.append(f"Empaquetat (PyInstaller): {bool(getattr(sys, 'frozen', False))}")

    if sys.platform == "win32":
        _twain_section(lines)
        _wia_section(lines)
    elif sys.platform == "darwin":
        _ica_section(lines)
    else:
        _sane_section(lines)

    _section(lines, "Escàners que veu ScanLab")
    try:
        from scanlab.backends import get_backend

        backend = get_backend()
        devices = backend.list_devices()
        if devices:
            for dev in devices:
                lines.append(f"  - {dev.id} | {dev.vendor} {dev.model}")
        else:
            lines.append("  (cap)")
        for error in getattr(backend, "errors", []):
            lines.append(f"  error: {error}")
    except Exception as exc:  # noqa: BLE001
        lines.append(f"Error: {exc}")

    return "\n".join(lines)
