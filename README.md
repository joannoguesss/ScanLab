# ScanLab

Aplicació d'escaneig multiplataforma (macOS, Windows, Linux) per a l'**Epson
Perfection V500 Photo** (GT-X770), inspirada en l'EPSON Scan clàssic: control
professional amb previsualització, marquesines múltiples, histograma en viu,
correcció tonal, mode pel·lícula (positius i negatius) i desat per lots.

## Per què

El V500 no funciona amb el backend lliure `epson2` de SANE (parla el protocol
ESC/I-2, no l'ESC/I clàssic), així que cada sistema fa servir la seva via
nativa:

| Sistema  | Backend | Driver necessari |
|----------|---------|------------------|
| macOS    | ImageCaptureCore (PyObjC) | [ICA Scanner Driver 5.8.23](https://ftp.epson.com/drivers/ESICA_5.8.23.dmg) d'Epson (fins a macOS 26 Tahoe) |
| Windows  | WIA (pywin32) | «Scanner Driver and EPSON Scan Utility» d'Epson |
| Linux    | SANE (python-sane) | `iscan` + `iscan-plugin-gt-x770` (driver epkowa) |

## Instal·lació

- **macOS**: baixa `ScanLab.dmg` de les [releases](../../releases), obre'l i
  arrossega ScanLab a Aplicacions. Instal·la abans el driver ICA d'Epson.
- **Windows**: baixa i executa `ScanLab-Setup.exe` de les
  [releases](../../releases). Instal·la abans el driver d'Epson.
  Per compilar-lo tu mateix: [packaging/windows/COMPILAR-EN-WINDOWS.md](packaging/windows/COMPILAR-EN-WINDOWS.md).
- **Arch Linux (AUR)**: `packaging/aur/PKGBUILD` (paquet `scanlab`).

## Funcionalitats

- Previsualització amb fins a 50 marquesines (dibuixar, moure, copiar,
  auto-localitzar), «Escaneja-ho tot» (una per fitxer), zoom integrat,
  girar/mirall i densitòmetre RGB.
- Histograma integrat en viu: ombra/gamma/llum arrossegables per canal.
- Correcció tonal amb corba editable; brillantor, contrast, saturació,
  balanç RGB, llindar B/N, màscara d'enfocament, destramat, contrallum i
  eliminació de pols (per programari).
- Pel·lícula: positius, negatius en color i B/N (inversió automàtica).
- 50–12800 ppp, color 24/48 bits, grisos 8/16 bits, B/N.
- Desat amb prefix + numeració, JPEG/TIFF/PNG/BMP/PDF, PDF multipàgina.
- Menú «Visualitza»: mides en mm, àrea, quadrícula de terços, centre.
- Tota la configuració es conserva entre sessions.

## Desenvolupament

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m scanlab.gui       # interfície gràfica
.venv/bin/python -m scanlab list      # CLI: escàners detectats
.venv/bin/python -m scanlab scan -o foto.tiff --dpi 600
sh packaging/macos/build_dmg.sh       # empaquetar per a macOS
```

Les releases es compilen automàticament amb GitHub Actions en etiquetar
`vX.Y.Z`.

## Llicència

MIT — vegeu [LICENSE](LICENSE).
