# Compilar ScanLab en Windows

Guía paso a paso para compilar ScanLab en un PC con Windows 10/11.

## 1. Requisitos (una sola vez)

1. **Python 3.12 o superior**: descárgalo de https://www.python.org/downloads/
   - Al instalarlo, **marca la casilla "Add python.exe to PATH"**.
2. **Driver del escáner**: instala el "Scanner Driver and EPSON Scan Utility"
   del V500 para Windows desde la web de Epson (es el que instala el driver
   WIA que usa ScanLab):
   https://epson.com/Support/Scanners/Perfection-Series/Epson-Perfection-V500-Photo/s/SPT_B11B189011
3. *(Solo para crear el instalador)* **Inno Setup 6**:
   https://jrsoftware.org/isdl.php

## 2. Llevar el proyecto al PC

Cualquiera de las dos:
- Clonar el repositorio de GitHub (cuando esté subido):
  `git clone https://github.com/<usuario>/ScanLab.git`
- O copiar la carpeta `ScanLab` entera con un USB (NO hace falta copiar
  `.venv` ni `dist` ni `build`; solo el código).

## 3. Compilar

Doble clic en:

```
packaging\windows\build.bat
```

El script crea el entorno, instala las dependencias (PySide6, Pillow,
pywin32) y compila con PyInstaller. Al acabar tendrás:

```
dist\ScanLab\ScanLab.exe
```

Ese `.exe` ya funciona: pruébalo con el escáner conectado por USB.

## 4. Crear el instalador (opcional)

1. Abre `packaging\windows\installer.iss` con Inno Setup.
2. Pulsa **Compile** (Ctrl+F9).
3. El instalador queda en `packaging\windows\Output\ScanLab-Setup.exe`.

## Notas

- El backend de Windows usa **WIA** (el sistema de escaneo integrado de
  Windows) a través del driver de Epson. La cama plana funciona con todos
  los ajustes; el modo transparencias/negativos por WIA depende del driver
  y puede no estar disponible (ScanLab avisa si es el caso).
- Si `build.bat` falla en PyInstaller con Python muy nuevo, instala
  Python 3.12 y borra la carpeta `.venv-win` antes de reintentar.
