; Salesforce Translation Handler - Inno Setup Script
; ---------------------------------------------------
; Builds a Windows installer from the PyInstaller output directory.
;
; Usage:
;   iscc installer/stx_installer.iss
;
; Expects PyInstaller --onedir output in dist/SalesforceTranslationHandler/
; or --onefile output as dist/SalesforceTranslationHandler.exe

#define MyAppName "Salesforce Translation Handler"
#define MyAppVersion "3.0.0"
#define MyAppPublisher "Salesforce Translation Handler Contributors"
#define MyAppURL "https://github.com/sourav98hazra/Salesforce-Translation-Handler"
#define MyAppExeName "SalesforceTranslationHandler.exe"

[Setup]
AppId={{B8A3F2E1-4C5D-6E7F-8A9B-0C1D2E3F4A5B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={autopf}\SalesforceTranslationHandler
DefaultGroupName={#MyAppName}
LicenseFile=..\LICENSE
OutputDir=..\dist\installer
OutputBaseFilename=SalesforceTranslationHandler_Setup_{#MyAppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
UninstallDisplayIcon={app}\{#MyAppExeName}
SetupIconFile=..\src\stx\gui\assets\logo.ico
; SignTool placeholder - uncomment and configure for code-signing:
; SignTool=signtool sign /f "$q{#SetupSetting("SignToolCertFile")}$q" /p "$q{#SetupSetting("SignToolCertPassword")}$q" /t http://timestamp.digicert.com /fd sha256 $f

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Include all files from the PyInstaller --onedir output.
; Run 'python installer/build_installer.py' first to produce dist/SalesforceTranslationHandler/
Source: "..\dist\SalesforceTranslationHandler\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\SalesforceTranslationHandler\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandirs; Name: "{app}\__pycache__"
Type: filesandirs; Name: "{app}\*.pyc"
Type: dirifempty; Name: "{app}"
Type: filesandirs; Name: "{localappdata}\SalesforceTranslationHandler\cache"
Type: dirifempty; Name: "{localappdata}\SalesforceTranslationHandler"

[Code]
// Placeholder for custom code-signing logic during install/uninstall.
// The SignTool directive in [Setup] handles signing at build time.
// This section can be extended for runtime certificate validation if needed.

procedure CurStepChanged(CurStep: TSetupStep);
begin
  // Post-install actions can be added here
  if CurStep = ssPostInstall then
  begin
    // Example: write version info to registry for update checking
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  // Pre-uninstall cleanup
  if CurUninstallStep = usUninstall then
  begin
    // Clean up user-specific cached data
    DelTree(ExpandConstant('{localappdata}\SalesforceTranslationHandler'), True, True, True);
  end;
end;
