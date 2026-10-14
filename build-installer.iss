; Shout installer (Inno Setup 6). Built by build.ps1 from dist\Shout into .\ShoutSetup.exe.
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{8C5E2A57-4B1D-4E8B-9F0A-5D3C2B7E1A64}
AppName=Shout
AppVersion={#AppVersion}
AppPublisher=Shout
AppComments=Offline diktálás magyarul és angolul
; {autopf}: %LOCALAPPDATA%\Programs for "just me", Program Files for "all users" (asked on the first page)
DefaultDirName={autopf}\Shout
DisableDirPage=no
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
; models, history and the autostart value are per user by design, even in an all-users install
UsedUserAreasWarning=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
AppMutex=ShoutSingleInstance
CloseApplications=yes
OutputDir=.
OutputBaseFilename=ShoutSetup
SetupIconFile=assets\shout.ico
UninstallDisplayIcon={app}\app\assets\shout.ico
UninstallDisplayName=Shout
WizardStyle=modern
Compression=lzma2/ultra64
SolidCompression=yes

[Languages]
Name: "hu"; MessagesFile: "compiler:Languages\Hungarian.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
hu.AutoStart=Indítás a Windows-zal
en.AutoStart=Start with Windows
hu.DeleteData=Töröljem a letöltött beszédfelismerő modelleket (kb. 3,5 GB), az előzményeket és a beállításokat is?
en.DeleteData=Also delete the downloaded speech models (about 3.5 GB), history and settings?

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "autostart"; Description: "{cm:AutoStart}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "dist\Shout\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\Shout"; Filename: "{app}\Shout.exe"; IconFilename: "{app}\app\assets\shout.ico"; AppUserModelID: "Shout.Shout"
Name: "{autodesktop}\Shout"; Filename: "{app}\Shout.exe"; IconFilename: "{app}\app\assets\shout.ico"; AppUserModelID: "Shout.Shout"; Tasks: desktopicon

[Registry]
; Same value the in-app "Indítás a Windows-zal" switch writes; -X tray starts hidden in the tray.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Shout"; ValueData: """{app}\Shout.exe"" -X tray"; Tasks: autostart

[Run]
Filename: "{app}\Shout.exe"; Description: "{cm:LaunchProgram,Shout}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    { the app's own autostart switch may have created this even if the installer task was off }
    RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'Shout');
    if (not UninstallSilent) and (MsgBox(CustomMessage('DeleteData'), mbConfirmation, MB_YESNO) = IDYES) then
    begin
      DelTree(ExpandConstant('{localappdata}\Shout'), True, True, True);
      DelTree(ExpandConstant('{userappdata}\Shout'), True, True, True);
    end;
  end;
end;
