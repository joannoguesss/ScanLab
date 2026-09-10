"""Punt d'entrada de l'ajudant d'escaneig de 32 bits (ScanLab-worker32.exe).

Molts drivers TWAIN d'escàners antics —el del V500 entre ells— només són de
32 bits, i un procés de 64 bits no els pot carregar. La interfície de ScanLab
és de 64 bits (PySide6 no existeix per a 32), així que delega l'escaneig en
aquest executable petit, que només porta Pillow i pytwain.

Rep els mateixos arguments que la CLI: `ScanLab-worker32.exe scan -o …`.
"""

import sys

from scanlab.cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
