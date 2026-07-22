#!/bin/sh
# ScanLab — empaquetado macOS: .app con PyInstaller + DMG de arrastrar.
# Uso: sh packaging/macos/build_dmg.sh
# Resultado: dist/ScanLab.dmg
set -e
cd "$(dirname "$0")/../.."

PY=.venv/bin/python
if [ ! -x "$PY" ]; then
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt
fi
.venv/bin/pip show pyinstaller >/dev/null 2>&1 || .venv/bin/pip install pyinstaller

echo "[1/3] Compilant ScanLab.app..."
.venv/bin/pyinstaller --noconfirm --clean --windowed --name ScanLab \
    --osx-bundle-identifier com.joan.scanlab launcher.py

echo "[2/3] Preparant el DMG (arrossega a Aplicacions)..."
STAGING="dist/dmg-staging"
rm -rf "$STAGING" dist/ScanLab.dmg
mkdir -p "$STAGING"
cp -R dist/ScanLab.app "$STAGING/"
ln -s /Applications "$STAGING/Applications"

echo "[3/3] Creant dist/ScanLab.dmg..."
hdiutil create -volname "ScanLab" -srcfolder "$STAGING" -ov -format UDZO \
    dist/ScanLab.dmg >/dev/null
rm -rf "$STAGING"

echo "Fet: dist/ScanLab.dmg"
