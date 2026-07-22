"""Punt d'entrada únic per a l'app empaquetada (PyInstaller, .app, .exe).

Sense arguments obre la interfície gràfica. Amb `--scan-worker` actua com el
procés de escaneig que la GUI llança en segon pla (dins d'un executable
empaquetat no hi ha cap `python -m scanlab` disponible).
"""

import sys


def main():
    argv = sys.argv[1:]
    if argv and argv[0] == "--scan-worker":
        from scanlab.cli import main as cli_main

        sys.exit(cli_main(argv[1:]))
    from scanlab.gui.window import run

    run()


if __name__ == "__main__":
    main()
