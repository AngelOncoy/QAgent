; Instalador de QAgent para Windows (Inno Setup 6) — TA-06.
; No se compila a mano: lo llama `python scripts/construir_windows.py`, que pasa la versión
; con /DVersion=x.y.z y antes genera dist\windows\QAgent\ con PyInstaller.

#ifndef Version
  #define Version "0.0.0"
#endif

[Setup]
; AppId identifica a QAgent para actualizar y desinstalar: no cambiarlo nunca.
AppId={{CFA402C7-D47F-4796-B105-2AAFBD4DFF14}
AppName=QAgent
AppVersion={#Version}
AppVerName=QAgent {#Version}
AppPublisher=Equipo QAgent - Taller Integrador I (UPAO)
AppPublisherURL=https://github.com/AngelOncoy/QAgent
DefaultDirName={autopf}\QAgent
DefaultGroupName=QAgent
DisableProgramGroupPage=yes
; Sin permisos de administrador: se instala para el usuario actual (o para todos, si elige).
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
InfoBeforeFile=requisitos.txt
SetupIconFile=qagent.ico
UninstallDisplayIcon={app}\QAgent.exe
OutputDir=..\..\dist\windows
OutputBaseFilename=QAgent-{#Version}-instalador
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Imágenes del asistente (Inno Setup 6.6 o superior): panel izquierdo de las páginas de
; bienvenida y fin, e imagen pequeña de las demás. Un archivo por escala de pantalla
; (100 % a 250 %); Setup elige el que mejor encaja.
WizardImageFile=asistente\panel-100.png,asistente\panel-125.png,asistente\panel-150.png,asistente\panel-175.png,asistente\panel-200.png,asistente\panel-225.png,asistente\panel-250.png
WizardSmallImageFile=asistente\pequena-100.png,asistente\pequena-125.png,asistente\pequena-150.png,asistente\pequena-175.png,asistente\pequena-200.png,asistente\pequena-225.png,asistente\pequena-250.png

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "escritorio"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\..\dist\windows\QAgent\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\QAgent"; Filename: "{app}\QAgent.exe"
Name: "{group}\Desinstalar QAgent"; Filename: "{uninstallexe}"
Name: "{autodesktop}\QAgent"; Filename: "{app}\QAgent.exe"; Tasks: escritorio

[Run]
Filename: "{app}\QAgent.exe"; Description: "{cm:LaunchProgram,QAgent}"; Flags: nowait postinstall skipifsilent
