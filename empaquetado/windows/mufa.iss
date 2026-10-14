; Instalador de mufa para Windows (Inno Setup 6).
;   uv run pyinstaller empaquetado/mufa.spec --noconfirm --distpath dist
;   iscc /DVersion=0.1.2 empaquetado\windows\mufa.iss
; Instala la carpeta dist\mufa en Archivos de programa (pide permiso de
; administrador), con acceso en el menú Inicio, desinstalador en
; «Aplicaciones instaladas» y, si se quiere, un ícono en el escritorio.
; Los datos de cada persona quedan en C:\Users\<persona>\.mufa: desinstalar
; no los borra.

#ifndef Version
  #define Version "0.0.0"
#endif

[Setup]
; El AppId identifica a mufa en Windows: no se cambia nunca (las
; actualizaciones lo usan para reemplazar la versión instalada).
AppId={{A1385FE9-0106-4114-842B-F89862114551}
AppName=mufa
AppVersion={#Version}
AppVerName=mufa {#Version}
AppPublisher=mufa
AppPublisherURL=https://mufa.pages.dev
AppSupportURL=https://github.com/DecoTaco22/mufa/issues
AppUpdatesURL=https://github.com/DecoTaco22/mufa/releases
AppCopyright=Copyright (C) 2026 los autores de mufa
VersionInfoVersion={#Version}
VersionInfoDescription=Instalador de mufa
VersionInfoProductName=mufa
DefaultDirName={autopf}\mufa
DefaultGroupName=mufa
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
LicenseFile=..\..\LICENSE
SetupIconFile=..\mufa.ico
UninstallDisplayIcon={app}\mufa.exe
UninstallDisplayName=mufa
WizardStyle=modern
; Si mufa está abierta al actualizar, se cierra antes de reemplazarla.
CloseApplications=yes
RestartApplications=no
Compression=lzma2/max
SolidCompression=yes
OutputDir=..\..\dist
OutputBaseFilename=mufa-instalador-windows

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "escritorio"; Description: "Crear un ícono en el escritorio"; GroupDescription: "Accesos directos:"

[Files]
Source: "..\..\dist\mufa\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; Al actualizar no quedan archivos de la versión anterior.
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\mufa"; Filename: "{app}\mufa.exe"; Comment: "Monitoreo, auditoría y respaldos de tu red"
Name: "{autodesktop}\mufa"; Filename: "{app}\mufa.exe"; Tasks: escritorio

[Run]
; runasoriginaluser: mufa se abre con tu usuario, no como administrador.
Filename: "{app}\mufa.exe"; Description: "Abrir mufa"; Flags: nowait postinstall skipifsilent runasoriginaluser
; La actualización desde la app corre el instalador sin ventanas (/SILENT /REABRIR=1):
; al terminar vuelve a abrir mufa.
Filename: "{app}\mufa.exe"; Flags: nowait runasoriginaluser; Check: Reabrir

[Code]
const
  WEBVIEW2 = 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';

function TieneWebView2: Boolean;
var
  Version: String;
begin
  Result :=
    (RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0')) or
    (RegQueryStringValue(HKLM, WEBVIEW2, 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0')) or
    (RegQueryStringValue(HKCU, WEBVIEW2, 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0'));
end;

function Reabrir: Boolean;
begin
  Result := WizardSilent and (ExpandConstant('{param:REABRIR|0}') = '1');
end;

function InitializeSetup: Boolean;
var
  Codigo: Integer;
begin
  Result := True;
  // Windows 11 y Windows 10 actualizado ya lo traen.
  if not TieneWebView2 then
    if MsgBox('mufa necesita Microsoft Edge WebView2, que no está en esta computadora.' + #13#10#13#10 +
              '¿Abrir la página de Microsoft para descargarlo? (Después vuelve a abrir este instalador.)',
              mbConfirmation, MB_YESNO) = IDYES then
    begin
      ShellExec('open', 'https://developer.microsoft.com/microsoft-edge/webview2/', '', '', SW_SHOWNORMAL, ewNoWait, Codigo);
      Result := False;
    end;
end;
