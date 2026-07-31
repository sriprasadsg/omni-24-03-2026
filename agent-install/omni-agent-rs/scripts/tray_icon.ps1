<#
    OmniAgent endpoint tray helper.

    Runs in the interactive user session (launched by a logon scheduled task),
    since the OmniAgent service itself runs in session 0 and cannot show a tray
    icon. Provides: Raise a Ticket, Chat with IT Support, and Agent Status.

    Reads C:\ProgramData\OmniAgent\tray-config.json (written by the agent after
    registration) for api_base_url / agent_id / agent_token / chat_ui path.
    Optional arg 1 overrides the config path.
#>
param([string]$ConfigPath = "$env:ProgramData\OmniAgent\tray-config.json")
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

# Hide this helper's own console window. The tray must live ONLY as a
# notification-area icon: the logon task launches powershell.exe, and if its
# console stays visible the user can close it and take the tray icon down with
# it. -WindowStyle Hidden is not reliable on PS 5.1, so hide the window here.
# (The background telemetry runs in the separate session-0 service, untouched.)
try {
    $hideSig = @'
[DllImport("kernel32.dll")] public static extern System.IntPtr GetConsoleWindow();
[DllImport("user32.dll")]   public static extern bool ShowWindow(System.IntPtr hWnd, int nCmdShow);
'@
    $win = Add-Type -MemberDefinition $hideSig -Name 'TrayWin' -Namespace 'Native' -PassThru
    $hWnd = $win::GetConsoleWindow()
    if ($hWnd -ne [System.IntPtr]::Zero) { [void]$win::ShowWindow($hWnd, 0) }  # 0 = SW_HIDE
} catch { }

# The download installer registers 'OmniAgentRust'; the MSI/service binary uses
# 'OmniAgent'. Resolve whichever exists so status works under either install path.
$ServiceName = @('OmniAgentRust','OmniAgent') |
    Where-Object { Get-Service -Name $_ -ErrorAction SilentlyContinue } |
    Select-Object -First 1
if (-not $ServiceName) { $ServiceName = 'OmniAgentRust' }

# The agent writes tray-config.json only after it has registered and obtained a
# token. On a fresh boot the tray may start first — wait rather than die.
$cfg = $null
for ($i = 0; $i -lt 60; $i++) {
    if (Test-Path $ConfigPath) {
        try { $cfg = Get-Content -Raw -Path $ConfigPath | ConvertFrom-Json; if ($cfg.agent_token) { break } } catch { }
    }
    Start-Sleep -Seconds 5
}
if (-not $cfg) { exit 0 }   # give up quietly; next logon retries

$Base     = ($cfg.api_base_url).TrimEnd('/')
$AgentId  = $cfg.agent_id
$Token    = $cfg.token
if (-not $Token) { $Token = $cfg.agent_token }
$Headers  = @{ Authorization = "Bearer $Token" }
$ChatUi   = if ($cfg.chat_ui) { $cfg.chat_ui } else { "$env:ProgramData\OmniAgent\chat_ui.ps1" }

$Templates = @(
    @{ Name='Install Software'; Type='task';     Priority='medium'; Prefix='Software Install Request: ' },
    @{ Name='Access Request';   Type='task';     Priority='medium'; Prefix='Access Request: ' },
    @{ Name='Report an Issue';  Type='bug';      Priority='high';   Prefix='Issue: ' },
    @{ Name='Hardware Request'; Type='task';     Priority='low';    Prefix='Hardware Request: ' },
    @{ Name='Security Concern'; Type='security'; Priority='high';   Prefix='Security Concern: ' },
    @{ Name='Custom Request';   Type='task';     Priority='medium'; Prefix='' }
)

function Get-EndpointInfo {
    @{
        hostname   = $env:COMPUTERNAME
        username   = $env:USERNAME
        os_name    = 'Windows'
        os_version = [System.Environment]::OSVersion.Version.ToString()
    }
}

# ── Ticket dialog ───────────────────────────────────────────────────────────────
function Show-TicketDialog($tpl) {
    $f = New-Object System.Windows.Forms.Form
    $f.Text = "Raise a Ticket - $($tpl.Name)"
    $f.Size = New-Object System.Drawing.Size(440, 340)
    $f.StartPosition = 'CenterScreen'; $f.TopMost = $true

    $lblT = New-Object System.Windows.Forms.Label
    $lblT.Text = 'Title'; $lblT.Location = '12,12'; $lblT.AutoSize = $true; $f.Controls.Add($lblT)
    $title = New-Object System.Windows.Forms.TextBox
    $title.Location = '12,32'; $title.Size = '400,24'; $title.Text = $tpl.Prefix; $f.Controls.Add($title)

    $lblD = New-Object System.Windows.Forms.Label
    $lblD.Text = 'Description'; $lblD.Location = '12,64'; $lblD.AutoSize = $true; $f.Controls.Add($lblD)
    $desc = New-Object System.Windows.Forms.TextBox
    $desc.Location = '12,84'; $desc.Size = '400,140'; $desc.Multiline = $true; $desc.ScrollBars = 'Vertical'; $f.Controls.Add($desc)

    $status = New-Object System.Windows.Forms.Label
    $status.Location = '12,232'; $status.Size = '400,20'; $status.ForeColor = 'DimGray'; $f.Controls.Add($status)

    $submit = New-Object System.Windows.Forms.Button
    $submit.Text = 'Submit'; $submit.Location = '332,262'; $submit.Size = '80,28'; $f.Controls.Add($submit)
    $submit.Add_Click({
        $t = $title.Text.Trim()
        if ($t.Length -eq 0 -or $t -eq $tpl.Prefix.Trim()) { $status.ForeColor = 'Firebrick'; $status.Text = 'Please enter a title.'; return }
        $status.ForeColor = 'DimGray'; $status.Text = 'Submitting...'; $submit.Enabled = $false
        try {
            $body = @{
                title = $t; description = $desc.Text; type = $tpl.Type; priority = $tpl.Priority
                tags = @('user-raised', 'tray'); endpoint_info = (Get-EndpointInfo)
            } | ConvertTo-Json -Depth 5
            $r = Invoke-RestMethod -Method Post -Uri "$Base/api/agents/$AgentId/ticket" -Headers $Headers -ContentType 'application/json' -Body $body
            $status.ForeColor = 'ForestGreen'; $status.Text = "Ticket $($r.ticket_number) created."
            Start-Sleep -Seconds 2; $f.Close()
        } catch {
            $status.ForeColor = 'Firebrick'; $status.Text = 'Failed to submit - check connection.'; $submit.Enabled = $true
        }
    }.GetNewClosure())
    [void]$f.ShowDialog()
}

# ── Chat: initiate a session then open the shared chat window ────────────────────
function Start-ChatWithIT {
    $f = New-Object System.Windows.Forms.Form
    $f.Text = 'Chat with IT Support'; $f.Size = New-Object System.Drawing.Size(420, 260)
    $f.StartPosition = 'CenterScreen'; $f.TopMost = $true

    $lblS = New-Object System.Windows.Forms.Label
    $lblS.Text = 'Subject'; $lblS.Location = '12,12'; $lblS.AutoSize = $true; $f.Controls.Add($lblS)
    $subj = New-Object System.Windows.Forms.TextBox
    $subj.Location = '12,32'; $subj.Size = '384,24'; $f.Controls.Add($subj)

    $lblM = New-Object System.Windows.Forms.Label
    $lblM.Text = 'Message'; $lblM.Location = '12,64'; $lblM.AutoSize = $true; $f.Controls.Add($lblM)
    $msg = New-Object System.Windows.Forms.TextBox
    $msg.Location = '12,84'; $msg.Size = '384,80'; $msg.Multiline = $true; $f.Controls.Add($msg)

    $status = New-Object System.Windows.Forms.Label
    $status.Location = '12,172'; $status.Size = '384,20'; $status.ForeColor = 'DimGray'; $f.Controls.Add($status)

    $go = New-Object System.Windows.Forms.Button
    $go.Text = 'Start Chat'; $go.Location = '312,196'; $go.Size = '84,28'; $f.Controls.Add($go)
    $go.Add_Click({
        if ($subj.Text.Trim().Length -eq 0 -or $msg.Text.Trim().Length -eq 0) {
            $status.ForeColor = 'Firebrick'; $status.Text = 'Subject and message are required.'; return
        }
        $status.ForeColor = 'DimGray'; $status.Text = 'Connecting...'; $go.Enabled = $false
        try {
            $body = @{ agent_id = $AgentId; subject = $subj.Text.Trim(); message = $msg.Text.Trim() } | ConvertTo-Json
            $sess = Invoke-RestMethod -Method Post -Uri "$Base/api/agent-chat/sessions/initiate" -Headers $Headers -ContentType 'application/json' -Body $body
            $sessCfg = @{
                session_id = $sess.id; backend_url = $Base; token = $Token
                subject = $subj.Text.Trim(); initial = ''; sender = ''
            } | ConvertTo-Json
            $sessPath = "$env:ProgramData\OmniAgent\chat_$($sess.id).json"
            Set-Content -Path $sessPath -Value $sessCfg -Encoding UTF8
            Start-Process powershell -ArgumentList @(
                '-NoProfile','-WindowStyle','Hidden','-ExecutionPolicy','Bypass','-File',"`"$ChatUi`"","`"$sessPath`"")
            $f.Close()
        } catch {
            $status.ForeColor = 'Firebrick'; $status.Text = 'Could not reach the server.'; $go.Enabled = $true
        }
    }.GetNewClosure())
    [void]$f.ShowDialog()
}

# ── Status ──────────────────────────────────────────────────────────────────────
function Show-Status($notify) {
    $svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    $state = if ($svc) { $svc.Status } else { 'Not installed' }
    $msg = "Agent service: $state`nServer: $Base`nAgent ID: $AgentId"
    $notify.BalloonTipTitle = 'OmniAgent Status'
    $notify.BalloonTipText  = $msg
    $notify.ShowBalloonTip(6000)
}

# ── Tray icon + menu ────────────────────────────────────────────────────────────
$notify = New-Object System.Windows.Forms.NotifyIcon
$notify.Icon = [System.Drawing.SystemIcons]::Shield
$notify.Text = 'OmniAgent - IT Support'
$notify.Visible = $true

$menu = New-Object System.Windows.Forms.ContextMenuStrip

$ticketRoot = New-Object System.Windows.Forms.ToolStripMenuItem 'Raise a Ticket'
foreach ($tpl in $Templates) {
    $item = New-Object System.Windows.Forms.ToolStripMenuItem $tpl.Name
    $captured = $tpl
    $item.Add_Click({ Show-TicketDialog $captured }.GetNewClosure())
    [void]$ticketRoot.DropDownItems.Add($item)
}
[void]$menu.Items.Add($ticketRoot)

$chatItem = New-Object System.Windows.Forms.ToolStripMenuItem 'Chat with IT Support'
$chatItem.Add_Click({ Start-ChatWithIT })
[void]$menu.Items.Add($chatItem)

[void]$menu.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator))

$statusItem = New-Object System.Windows.Forms.ToolStripMenuItem 'Agent Status'
$statusItem.Add_Click({ Show-Status $notify })
[void]$menu.Items.Add($statusItem)

$notify.ContextMenuStrip = $menu
$notify.Add_MouseClick({ if ($_.Button -eq 'Left') { Show-Status $notify } })

# Hidden form keeps the message loop alive without a taskbar window.
$ctx = New-Object System.Windows.Forms.ApplicationContext
[System.Windows.Forms.Application]::Run($ctx)
$notify.Visible = $false
$notify.Dispose()
