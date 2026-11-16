#include "branding.iss"

[Setup]
AppId={{B3F1D2A4-6C7E-4E39-9A51-2D0C7B6E4F10}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
SetupIconFile=..\branding\logo.ico
DefaultDirName={localappdata}\Programs\YTDownloaderHelper
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
OutputDir=..\installer_output
OutputBaseFilename=YTDownloaderHelper-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\YTDownloaderHelper.exe

[Tasks]
Name: "autostart"; Description: "Start the helper automatically when I sign in"; GroupDescription: "Options:"

[Files]
Source: "..\dist\YTDownloaderHelper\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Registry]
Root: HKCU; Subkey: "Software\Google\Chrome\NativeMessagingHosts\com.ytdl.helper"; ValueType: string; ValueData: "{app}\native\com.ytdl.helper.json"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Microsoft\Edge\NativeMessagingHosts\com.ytdl.helper"; ValueType: string; ValueData: "{app}\native\com.ytdl.helper.json"; Flags: uninsdeletekey

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\YTDownloaderHelper.exe"
Name: "{group}\Chrome extension folder"; Filename: "{app}\extension"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\YTDownloaderHelper.exe"
Name: "{userstartup}\{#AppName}"; Filename: "{app}\YTDownloaderHelper.exe"; Tasks: autostart

[Run]
Filename: "{app}\YTDownloaderHelper.exe"; Description: "Start the helper now"; Flags: nowait postinstall skipifsilent
Filename: "{app}\extension"; Description: "Open the extension folder (then load it in chrome://extensions)"; Flags: postinstall shellexec skipifsilent
