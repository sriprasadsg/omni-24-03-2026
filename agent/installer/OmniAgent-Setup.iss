; OmniAgent-Setup.iss — Inno Setup 6 installer script
; Produces: dist/OmniAgent-Setup.exe
; Build:    iscc.exe OmniAgent-Setup.iss   (Windows only, requires Inno Setup 6)

#define MyAppName      "Enterprise OmniAgent"
#define MyAppVersion   "2.1.0"
#define MyAppPublisher "Enterprise OmniAgent"
#define MyServiceName  "OmniAgentRust"
#define MyExeName      "omni-agent.exe"
#define MyInstallDir   "{autopf}\OmniAgent"

[Setup]
AppId={{B4E7C1D2-3F8A-4E9B-A012-5C6D7E8F90A1}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={#MyInstallDir}
DefaultGroupName={#MyAppName}
OutputDir=dist
OutputBaseFilename=OmniAgent-Setup
Compression=lzma2/ultra64
SolidCompression=yes
PrivilegesRequired=admin
MinVersion=10.0.17763
WizardStyle=modern
UninstallDisplayName={#MyAppName}
VersionInfoVersion={#MyAppVersion}
VersionInfoDescription=Enterprise OmniAgent Installer

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "firstrun"; Description: "Run evidence collection immediately after install"; GroupDescription: "Evidence Collection:"; Flags: checked

[Files]
; NOTE: omni-agent.exe is a pre-built Rust binary — build with: cargo build --release
Source: "..\target\release\{#MyExeName}";  DestDir: "{app}"; Flags: ignoreversion; Check: FileExists(ExpandConstant('{src}\..\target\release\{#MyExeName}'))
Source: "Collect-Evidence.ps1";             DestDir: "{app}"; Flags: ignoreversion
Source: "Configure-Agent.ps1";              DestDir: "{app}"; Flags: ignoreversion
Source: "uninstall_agent.ps1";              DestDir: "{app}"; Flags: ignoreversion
; Spyglass evidence collection
Source: "..\build\spyglass\unified-collection.ps1"; DestDir: "{app}\.spyglass\evidence"; Flags: ignoreversion
Source: "Collect-Evidence.ps1";             DestDir: "{app}\.spyglass\evidence"; Flags: ignoreversion

[Icons]
Name: "{group}\Configure OmniAgent";    Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{app}\Configure-Agent.ps1"""
Name: "{group}\Collect Evidence Now";   Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{app}\Collect-Evidence.ps1"""
Name: "{group}\Uninstall OmniAgent";   Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-ExecutionPolicy Bypass -File ""{app}\uninstall_agent.ps1"""

[Code]
var
  ConfigPage: TInputQueryWizardPage;

procedure InitializeWizard;
begin
  ConfigPage := CreateInputQueryPage(wpSelectDir,
    'Platform Connection', 'Enter your OmniAgent platform connection details.',
    'These settings are saved to config.yaml in the installation directory.');
  ConfigPage.Add('Platform URL (e.g. http://192.168.1.100:5000):', False);
  ConfigPage.Add('Tenant Registration Key (from Settings > Agents):', False);
  ConfigPage.Values[0] := 'http://localhost:5000';
end;

function PSEscape(S: String): String;
begin
  { Escape single quotes for interpolation into a single-quoted PowerShell
    string literal (CR-03): PowerShell escapes an embedded ' by doubling it. }
  StringChangeEx(S, '''', '''''', True);
  Result := S;
end;

function GetApiUrl(Param: String): String;
begin Result := PSEscape(ConfigPage.Values[0]); end;

function GetRegKey(Param: String): String;
begin Result := PSEscape(ConfigPage.Values[1]); end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = ConfigPage.ID then begin
    if Trim(ConfigPage.Values[0]) = '' then begin
      MsgBox('Platform URL is required.', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

[Run]
; Write config.yaml
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; \
  Parameters: "-NonInteractive -ExecutionPolicy Bypass -Command ""$cfg = 'api_base_url: {code:GetApiUrl}' + [Environment]::NewLine + 'registration_key: {code:GetRegKey}' + [Environment]::NewLine + 'interval_seconds: 60' + [Environment]::NewLine + 'evidence_collection: true' + [Environment]::NewLine + 'evidence_interval_hours: 24'; Set-Content -Path '{app}\config.yaml' -Encoding UTF8 -Value $cfg"""; \
  Flags: runhidden; StatusMsg: "Writing configuration...";

; Install and start Windows service
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; \
  Parameters: "-NonInteractive -ExecutionPolicy Bypass -Command ""sc.exe create '{#MyServiceName}' binPath= '`""{app}\{#MyExeName}`""' start= delayed-auto obj= LocalSystem DisplayName= 'Enterprise OmniAgent (Rust)' | Out-Null; sc.exe description '{#MyServiceName}' 'Enterprise security compliance agent - evidence, CIS/PCI/ISO checks.' | Out-Null; sc.exe failure '{#MyServiceName}' reset= 86400 actions= restart/5000/restart/5000/restart/5000 | Out-Null; Start-Service '{#MyServiceName}' -ErrorAction SilentlyContinue"""; \
  Flags: runhidden; StatusMsg: "Installing Windows service..."; Check: FileExists(ExpandConstant('{app}\{#MyExeName}'));

; Register daily evidence collection scheduled task
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; \
  Parameters: "-NonInteractive -ExecutionPolicy Bypass -Command ""$a=New-ScheduledTaskAction -Execute 'powershell.exe' -Argument '-NonInteractive -ExecutionPolicy Bypass -File `""{app}\Collect-Evidence.ps1`""'; $t=New-ScheduledTaskTrigger -Daily -At '06:00'; $p=New-ScheduledTaskPrincipal -UserId SYSTEM -RunLevel Highest; Register-ScheduledTask -TaskName OmniAgentEvidenceCollection -Action $a -Trigger $t -Principal $p -Force | Out-Null"""; \
  Flags: runhidden; StatusMsg: "Scheduling daily evidence collection...";

; Run first evidence collection (if task selected)
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; \
  Parameters: "-NonInteractive -ExecutionPolicy Bypass -File ""{app}\Collect-Evidence.ps1"""; \
  Flags: runhidden waituntilidle; StatusMsg: "Running initial evidence collection..."; Tasks: firstrun;

; Run unified spyglass evidence collection (post-config)
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; \
  Parameters: "-NonInteractive -ExecutionPolicy Bypass -File ""{app}\.spyglass\evidence\unified-collection.ps1"" -BuildRoot ""{app}\.spyglass\evidence"""; \
  Flags: runhidden waituntilidle; StatusMsg: "Running Spyglass evidence collection...";

[UninstallRun]
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; \
  Parameters: "-NonInteractive -ExecutionPolicy Bypass -Command ""Stop-Service '{#MyServiceName}' -Force -EA SilentlyContinue; sc.exe delete '{#MyServiceName}' | Out-Null; Unregister-ScheduledTask -TaskName OmniAgentEvidenceCollection -Confirm:$false -EA SilentlyContinue"""; \
  Flags: runhidden;

[UninstallDelete]
Type: filesandordirs; Name: "{app}\.spyglass"
