; Installer Windows di Kalendae (Inno Setup 6)
; Compilazione:  iscc /DMyAppVersion=0.2.0 packaging\kalendae.iss
; Richiede prima:  python scripts\build.py

#define MyAppName "Kalendae"
#ifndef MyAppVersion
  #define MyAppVersion "0.2.0"
#endif
#define MyAppExe "Kalendae.exe"

[Setup]
AppId={{8E6F2A54-3C1B-4D7E-9A10-6B2C5D4E7F81}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher=Francesco Franchino
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=Kalendae-{#MyAppVersion}-windows-setup
SetupIconFile=..\build\kalendae.ico
UninstallDisplayIcon={app}\{#MyAppExe}
LicenseFile=..\LICENSE
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
; installazione per il solo utente, senza diritti di amministratore (si può scegliere "per tutti")
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "autostart"; Description: "Avvia Kalendae all'accesso (per ricevere i promemoria)"; GroupDescription: "Opzioni:"; Flags: unchecked

[Files]
Source: "..\dist\Kalendae\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: autostart

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{cmd}"; Parameters: "/C taskkill /IM {#MyAppExe} /F"; Flags: runhidden; RunOnceId: "StopKalendae"
