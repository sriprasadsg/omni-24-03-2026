; ============================================================
; OmniAgent Windows Installer
; Builds a self-contained Windows EXE installer.
; Requires: NSIS 3.x  (https://nsis.sourceforge.io)
;
; Standalone (interactive):
;   makensis omni-agent.nsi
;
; Per-tenant (silent, baked config — used by the backend):
;   makensis /DBAKED_API_URL="http://192.168.1.1:5000" ^
;            /DBAKED_TENANT_ID="tenant_abc" ^
;            /DBAKED_REG_KEY="reg_xyz" ^
;            /DOUTFILE="OmniAgent-TenantName-Setup.exe" ^
;            omni-agent.nsi
; ============================================================

!include "MUI2.nsh"
!include "nsDialogs.nsh"
!include "LogicLib.nsh"

; ── Product metadata ─────────────────────────────────────────
!define PRODUCT_NAME        "OmniAgent"
!define PRODUCT_VERSION     "2.0.0"
!define PRODUCT_PUBLISHER   "Enterprise OmniAgent AI Platform"
!define PRODUCT_UNINST_KEY  "Software\Microsoft\Windows\CurrentVersion\Uninstall\OmniAgent"
!define PRODUCT_REG_KEY     "Software\OmniAgent"
!define SVC_NAME            "OmniAgent"
!define SVC_DISPLAY         "Enterprise Omni Agent"
!define SVC_DESCRIPTION     "AI-Powered Enterprise Security Agent"

; ── Output file (override via /DOUTFILE=... at build time) ───
!ifndef OUTFILE
    !define OUTFILE "OmniAgent-Setup.exe"
!endif

Name          "${PRODUCT_NAME} ${PRODUCT_VERSION}"
OutFile       "${OUTFILE}"
InstallDir    "$PROGRAMFILES64\OmniAgent"
InstallDirRegKey HKLM "${PRODUCT_REG_KEY}" "InstallDir"
RequestExecutionLevel admin
SetCompressor  lzma

; ── Runtime config variables ──────────────────────────────────
Var APIUrl
Var TenantID
Var RegistrationKey
Var Interval

; ── Interactive-mode UI variables (only needed without baked config) ─
!ifndef BAKED_API_URL
Var Dialog
Var APIUrlCtrl
Var TenantIDCtrl
Var RegKeyCtrl
Var IntervalCtrl
!endif

; ── Finish page text ──────────────────────────────────────────
!ifdef BAKED_API_URL
    !define MUI_FINISHPAGE_TEXT "OmniAgent has been installed and configured for your tenant.$\r$\n$\r$\nService: ${SVC_NAME}$\r$\nPath:    $INSTDIR$\r$\n$\r$\nThe agent is running and will register with your platform automatically.$\r$\n$\r$\nManage via services.msc or: sc query OmniAgent"
!else
    !define MUI_FINISHPAGE_TEXT "OmniAgent has been installed as a Windows Service.$\r$\n$\r$\nService: ${SVC_NAME}$\r$\nPath:    $INSTDIR$\r$\n$\r$\nThe agent will register with the platform on first start using the embedded registration key.$\r$\n$\r$\nManage via services.msc or: sc query OmniAgent"
!endif

; ── Pages ─────────────────────────────────────────────────────
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!ifndef BAKED_API_URL
    Page custom ConfigPageCreate ConfigPageLeave
!endif
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_NOAUTOCLOSE
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

; ── Interactive config page (skipped when BAKED_API_URL is set) ─
!ifndef BAKED_API_URL

Function ConfigPageCreate
    !insertmacro MUI_HEADER_TEXT "Agent Configuration" "Configure the connection to your OmniAgent platform."
    nsDialogs::Create 1018
    Pop $Dialog
    ${If} $Dialog == error
        Abort
    ${EndIf}

    ${NSD_CreateLabel}  0   10u 100% 10u "Platform API Base URL:"
    Pop $0
    ${NSD_CreateText}   0   22u 100% 13u "http://192.168.1.100:5000"
    Pop $APIUrlCtrl

    ${NSD_CreateLabel}  0   46u 100% 10u "Tenant ID:"
    Pop $0
    ${NSD_CreateText}   0   58u 100% 13u ""
    Pop $TenantIDCtrl

    ${NSD_CreateLabel}  0   82u 100% 10u "Registration Key (from Platform > Agents > Install):"
    Pop $0
    ${NSD_CreateText}   0   94u 100% 13u ""
    Pop $RegKeyCtrl

    ${NSD_CreateLabel}  0  118u  60u 10u "Poll interval (seconds):"
    Pop $0
    ${NSD_CreateNumber} 62u 118u 30u 13u "30"
    Pop $IntervalCtrl

    nsDialogs::Show
FunctionEnd

Function ConfigPageLeave
    ${NSD_GetText} $APIUrlCtrl    $APIUrl
    ${NSD_GetText} $TenantIDCtrl  $TenantID
    ${NSD_GetText} $RegKeyCtrl    $RegistrationKey
    ${NSD_GetText} $IntervalCtrl  $Interval

    ${If} $APIUrl == ""
        MessageBox MB_OK|MB_ICONEXCLAMATION "Platform API URL is required."
        Abort
    ${EndIf}
    ${If} $TenantID == ""
        MessageBox MB_OK|MB_ICONEXCLAMATION "Tenant ID is required."
        Abort
    ${EndIf}
    ${If} $RegistrationKey == ""
        MessageBox MB_OK|MB_ICONEXCLAMATION "Registration Key is required. Copy it from Platform > Agents > Install."
        Abort
    ${EndIf}
    ${If} $Interval == ""
        StrCpy $Interval "30"
    ${EndIf}
FunctionEnd

!endif ; !BAKED_API_URL

; ── Main install section ──────────────────────────────────────
Section "${PRODUCT_NAME}" SEC_MAIN
    SectionIn RO

    ; Load baked tenant config (per-tenant installer built by backend)
    !ifdef BAKED_API_URL
        StrCpy $APIUrl          "${BAKED_API_URL}"
        StrCpy $TenantID        "${BAKED_TENANT_ID}"
        StrCpy $RegistrationKey "${BAKED_REG_KEY}"
        StrCpy $Interval        "30"
    !endif

    SetOutPath "$INSTDIR"

    ; Stop and remove existing service on upgrade
    ExecWait 'sc stop ${SVC_NAME}' $0
    Sleep 2000
    ExecWait 'sc delete ${SVC_NAME}' $0
    Sleep 1000

    ; Copy Rust agent binary
    File "omni-agent-rs\target\release\omni-agent.exe"

    ; ── Spyglass evidence collection ──────────────────────────────────
    CreateDirectory "$INSTDIR\.spyglass\evidence"
    SetOutPath "$INSTDIR\.spyglass\evidence"
    File "..\build\spyglass\unified-collection.ps1"
    File "..\agent\installer\Collect-Evidence.ps1"

    ; Write tenant-specific config.yaml
    FileOpen  $0 "$INSTDIR\config.yaml" w
    FileWrite $0 "api_base_url: $APIUrl$\r$\n"
    FileWrite $0 "tenant_id: $TenantID$\r$\n"
    FileWrite $0 "agent_id: ''$\r$\n"
    FileWrite $0 "agent_token: ''$\r$\n"
    FileWrite $0 "registration_key: $RegistrationKey$\r$\n"
    FileWrite $0 "interval_seconds: $Interval$\r$\n"
    FileWrite $0 "max_cpu_percent: 20$\r$\n"
    FileWrite $0 "agentic_mode_enabled: false$\r$\n"
    FileClose $0

    ; Run Spyglass evidence collection post-install
    ExecWait 'powershell.exe -ExecutionPolicy Bypass -File "$INSTDIR\.spyglass\evidence\unified-collection.ps1" -InstallDir "$INSTDIR" -BuildRoot "$INSTDIR\.spyglass\evidence"' $0

    ; Register and start Windows Service
    ExecWait 'sc create ${SVC_NAME} binPath= "$\"$INSTDIR\omni-agent.exe$\"" start= auto DisplayName= "${SVC_DISPLAY}"' $0
    ExecWait 'sc description ${SVC_NAME} "${SVC_DESCRIPTION}"' $0
    ExecWait 'sc failure ${SVC_NAME} reset= 86400 actions= restart/5000/restart/10000/restart/30000' $0
    ExecWait 'sc start ${SVC_NAME}' $0

    ; Add/Remove Programs entry
    WriteRegStr   HKLM "${PRODUCT_UNINST_KEY}" "DisplayName"     "${PRODUCT_NAME}"
    WriteRegStr   HKLM "${PRODUCT_UNINST_KEY}" "DisplayVersion"  "${PRODUCT_VERSION}"
    WriteRegStr   HKLM "${PRODUCT_UNINST_KEY}" "Publisher"       "${PRODUCT_PUBLISHER}"
    WriteRegStr   HKLM "${PRODUCT_UNINST_KEY}" "InstallDir"      "$INSTDIR"
    WriteRegStr   HKLM "${PRODUCT_UNINST_KEY}" "DisplayIcon"     "$INSTDIR\omni-agent.exe"
    WriteRegStr   HKLM "${PRODUCT_UNINST_KEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
    WriteRegDWORD HKLM "${PRODUCT_UNINST_KEY}" "NoModify"        1
    WriteRegDWORD HKLM "${PRODUCT_UNINST_KEY}" "NoRepair"        1
    WriteRegStr   HKLM "${PRODUCT_REG_KEY}"    "InstallDir"      "$INSTDIR"

    WriteUninstaller "$INSTDIR\Uninstall.exe"
    CreateDirectory  "$SMPROGRAMS\${PRODUCT_NAME}"
    CreateShortcut   "$SMPROGRAMS\${PRODUCT_NAME}\Uninstall ${PRODUCT_NAME}.lnk" "$INSTDIR\Uninstall.exe"
SectionEnd

; ── Uninstall section ─────────────────────────────────────────
Section "Uninstall"
    ExecWait 'sc stop ${SVC_NAME}'
    Sleep 3000
    ExecWait 'sc delete ${SVC_NAME}'

    ; Spyglass evidence cleanup
    Delete "$INSTDIR\.spyglass\evidence\unified-collection.ps1"
    Delete "$INSTDIR\.spyglass\evidence\Collect-Evidence.ps1"
    Delete "$INSTDIR\.spyglass\evidence\spyglass.json"
    Delete "$INSTDIR\.spyglass\evidence\evidence_output.json"
    RMDir  "$INSTDIR\.spyglass\evidence"
    RMDir  "$INSTDIR\.spyglass"

    Delete "$INSTDIR\omni-agent.exe"
    Delete "$INSTDIR\config.yaml"
    Delete "$INSTDIR\omni-agent.log"
    Delete "$INSTDIR\buffer.db"
    Delete "$INSTDIR\Uninstall.exe"
    RMDir  "$INSTDIR"

    Delete "$SMPROGRAMS\${PRODUCT_NAME}\*.*"
    RMDir  "$SMPROGRAMS\${PRODUCT_NAME}"

    DeleteRegKey HKLM "${PRODUCT_UNINST_KEY}"
    DeleteRegKey HKLM "${PRODUCT_REG_KEY}"
SectionEnd
