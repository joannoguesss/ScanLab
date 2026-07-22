# Guía de instalación de ScanLab

Cómo instalar ScanLab en cada sistema. En todos los casos hay **dos pasos**:
instalar el driver de Epson del V500 (una sola vez) y luego ScanLab.

> Los instaladores están en la página de
> [**Releases**](https://github.com/joannoguesss/ScanLab/releases).

---

## macOS

### 1. Driver de Epson (una sola vez)

1. Descarga el driver ICA oficial:
   **https://ftp.epson.com/drivers/ESICA_5.8.23.dmg** (compatible hasta
   macOS 26 Tahoe, Apple Silicon incluido).
2. Ábrelo y ejecuta `Epson Scanner ICA Driver.pkg`. Te pedirá tu contraseña
   de administrador.

### 2. ScanLab

1. Descarga **`ScanLab.dmg`** de las [Releases](https://github.com/joannoguesss/ScanLab/releases).
2. Ábrelo y **arrastra ScanLab a la carpeta Applications**.
3. La primera vez, macOS puede avisar de que la app no está firmada por un
   desarrollador identificado. Solución: **clic derecho sobre ScanLab.app →
   Abrir → Abrir**. (Solo hace falta la primera vez.)

   Si aun así no abre, en el Terminal:
   ```sh
   xattr -dr com.apple.quarantine /Applications/ScanLab.app
   ```
4. Conecta y enciende el escáner por USB, abre ScanLab y pulsa
   **Previsualitza**.

---

## Windows (10/11)

### 1. Driver de Epson (una sola vez)

1. Ve a la página de soporte del V500:
   https://epson.com/Support/Scanners/Perfection-Series/Epson-Perfection-V500-Photo/s/SPT_B11B189011
2. Elige tu Windows en el desplegable y descarga e instala
   **"Scanner Driver and EPSON Scan Utility"** (`PerfV500_3770_AM.exe`).
   Esto instala el driver WIA que usa ScanLab.

### 2. ScanLab

1. Descarga **`ScanLab-Setup.exe`** de las [Releases](https://github.com/joannoguesss/ScanLab/releases).
2. Ejecútalo. Si Windows SmartScreen avisa (instalador sin firmar), pulsa
   **"Más información" → "Ejecutar de todas formas"**.
3. Sigue el asistente (catalán o castellano). Al acabar tendrás ScanLab en el
   menú Inicio.

> ¿Prefieres compilarlo tú? Sigue
> [packaging/windows/COMPILAR-EN-WINDOWS.md](packaging/windows/COMPILAR-EN-WINDOWS.md).

---

## Arch Linux / Manjaro (AUR)

### 1. Driver de Epson (una sola vez)

El V500 necesita el driver propietario `epkowa` de Epson:

```sh
yay -S iscan iscan-plugin-gt-x770 sane
```

Comprueba que el escáner se ve: `scanimage -L` (debe aparecer `epkowa:...`).

### 2. ScanLab

Mientras el paquete no esté publicado en el AUR, compílalo desde el repo:

```sh
git clone https://github.com/joannoguesss/ScanLab.git
cd ScanLab/packaging/aur
makepkg -si
```

Después: ejecuta `scanlab` o búscalo en el menú de aplicaciones.

---

## Otras distribuciones Linux (Debian, Ubuntu, Fedora…)

Sin paquete por ahora; instalación manual:

```sh
# 1. Dependencias del sistema (ejemplo Debian/Ubuntu)
sudo apt install sane sane-utils python3-venv git

# 2. Driver de Epson: descarga "Image Scan! for Linux" (iscan) y el plugin
#    GT-X770 de http://support.epson.net/linux/en/imagescan.php
#    (paquetes .deb/.rpm; instala iscan y iscan-plugin-gt-x770)

# 3. ScanLab
git clone https://github.com/joannoguesss/ScanLab.git
cd ScanLab
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python launcher.py
```

---

## Problemas frecuentes

| Síntoma | Solución |
|---|---|
| «No es detecta cap escàner» | Comprueba cable USB y que el piloto esté en verde fijo; evita hubs. |
| macOS: no aparece tras instalar el driver | Desconecta y reconecta el USB; reinicia si es necesario. |
| Windows: aparece en Epson Scan pero no en ScanLab | Reinstala el driver de Epson: ScanLab usa el driver WIA que instala ese paquete. |
| Linux: `scanimage -L` no muestra `epkowa` | Falta `iscan-plugin-gt-x770`; sin ese plugin el V500 no funciona en Linux. |
| Los negativos salen sin invertir | Selecciona el tipo de película correcto (negativa en color / B/N). |
