; Instalador de ScanLab para Windows (Inno Setup 6)
; Compilar DESPUES de ejecutar build.bat:
;   abrir este archivo con Inno Setup y pulsar Compile.
; Resultado: packaging\windows\Output\ScanLab-Setup.exe

#define AppName "ScanLab"
#define AppVersion "0.1.5"
#define AppPublisher "Joan"
#define AppExe "ScanLab.exe"

[Setup]
AppId={{7E9C3B1A-5D24-4F8E-9A61-SCANLAB0V500}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
OutputBaseFilename=ScanLab-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
SetupIconFile=..\icons\ScanLab.ico
; Instalar encima de una version anterior la reemplaza (mismo AppId).

[Languages]
Name: "catalan"; MessagesFile: "compiler:Languages\Catalan.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Files]
Source: "..\..\dist\ScanLab\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
; Acceso directo visible para desinstalar, ademas del de Configuracion > Aplicaciones.
Name: "{group}\Desinstalar {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; Flags: unchecked

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
