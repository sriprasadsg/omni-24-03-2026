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

# Re-read before every action, not just at logon: the agent rewrites
# tray-config.json once it registers, and again after a reinstall. A tray that
# loaded it earlier (empty token, no pinned certificate) otherwise fails every
# ticket and chat before the request reaches the server.
function Sync-TrayConfig {
    try { $c = Get-Content -Raw -Path $ConfigPath | ConvertFrom-Json } catch { return }
    if (-not $c) { return }
    $script:cfg     = $c
    $script:Base    = ([string]$c.api_base_url).TrimEnd('/')
    $script:AgentId = $c.agent_id
    $script:Token   = if ($c.token) { $c.token } else { $c.agent_token }
    $script:Headers = @{ Authorization = "Bearer $($script:Token)" }
    $script:ChatUi  = if ($c.chat_ui) { $c.chat_ui } else { "$env:ProgramData\OmniAgent\chat_ui.ps1" }
    $script:EnrollProblem = [string]$c.enrollment_problem

    # This server's default deployment terminates TLS with a self-signed cert.
    # The Rust agent's own HTTP client trusts it because the installer pinned it
    # (server_ca_cert in config.yaml, passed here as server_cert_der_b64), but
    # Invoke-RestMethod here is a separate .NET TLS stack that knows nothing about
    # that config. Without this, every call below fails with a generic "trust
    # relationship" error that the catch blocks turn into "Could not reach the
    # server." / "check connection.", even though the server is perfectly
    # reachable. Agents installed before pinning still use accept_invalid_certs.
    try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch { }
    if ($c.server_cert_der_b64) {
        # Pinned: accept the server only if it presents exactly the certificate the
        # installer shipped (same rule as the Rust agent's own connections).
        $Pinned = [string]$c.server_cert_der_b64
        try {
            [Net.ServicePointManager]::ServerCertificateValidationCallback = {
                param($sender, $cert, $chain, $errors)
                $cert -ne $null -and [Convert]::ToBase64String($cert.GetRawCertData()) -eq $Pinned
            }.GetNewClosure()
        } catch { }
    } elseif ($c.accept_invalid_certs) {
        try { [Net.ServicePointManager]::ServerCertificateValidationCallback = { $true } } catch { }
    }
}
Sync-TrayConfig

$Templates = @(
    @{ Name='Install Software'; Type='task';     Priority='medium'; Prefix='Software Install Request: ' },
    @{ Name='Access Request';   Type='task';     Priority='medium'; Prefix='Access Request: ' },
    @{ Name='Report an Issue';  Type='bug';      Priority='high';   Prefix='Issue: ' },
    @{ Name='Hardware Request'; Type='task';     Priority='low';    Prefix='Hardware Request: ' },
    @{ Name='Security Concern'; Type='security'; Priority='high';   Prefix='Security Concern: ' },
    @{ Name='Custom Request';   Type='task';     Priority='medium'; Prefix='' }
)

# Failures used to show only "check connection", whatever happened, so nobody
# could tell an unenrolled agent from a certificate or server problem. Say what
# went wrong, and keep a per-user log for IT.
$TrayLog = Join-Path $(if ($env:LOCALAPPDATA) { $env:LOCALAPPDATA } else { $env:TEMP }) 'OmniAgent\tray.log'
function Write-TrayLog([string]$text) {
    try {
        $dir = Split-Path -Parent $TrayLog
        if (-not (Test-Path $dir)) { [void](New-Item -ItemType Directory -Path $dir -Force) }
        if ((Test-Path $TrayLog) -and (Get-Item $TrayLog).Length -gt 1MB) { Remove-Item $TrayLog -Force }
        Add-Content -Path $TrayLog -Value ("{0:u} {1}" -f (Get-Date), $text)
    } catch { }
}

# Without a token every request is refused, so don't send one: tell the user
# why (the agent publishes the reason in tray-config.json).
function Test-Enrolled($statusLabel) {
    if ($Token -and $AgentId) { return $true }
    $why = if ($EnrollProblem) { $EnrollProblem } else { 'The agent has not finished enrolling with the platform yet. Try again in a few minutes.' }
    $statusLabel.ForeColor = 'Firebrick'
    $statusLabel.Text = "This computer is not connected to IT support. $why"
    Write-TrayLog "not enrolled: $why"
    return $false
}

function Get-FailureText($err) {
    $ex = $err.Exception
    while ($ex -and -not ($ex -is [System.Net.WebException]) -and $ex.InnerException) { $ex = $ex.InnerException }
    $code = $null
    try { if ($ex.Response) { $code = [int]$ex.Response.StatusCode } } catch { }
    # The API answers {"detail": ...} or, from its error handler, {"error": ...}.
    $raw = [string]$err.ErrorDetails.Message
    $detail = $null
    try { $j = $raw | ConvertFrom-Json; $detail = @($j.detail, $j.error, $j.message) | Where-Object { $_ } | Select-Object -First 1 } catch { }
    if (-not $detail -and $raw) { $detail = $raw.Substring(0, [Math]::Min(200, $raw.Length)) }
    # Agent routes answer 401/403 only when the agent token is missing or invalid.
    if ($code -eq 401 -or $code -eq 403) { return "The platform refused this computer's agent ($detail). Ask IT to re-enroll it." }
    if ($code -eq 404) { return "The platform does not know this computer ($detail). Ask IT to re-enroll it." }
    if ($code) { return "The server answered $code. $detail" }
    switch ([string]$ex.Status) {
        'TrustFailure'          { return 'The server certificate does not match the one this agent trusts. Reinstall the agent from the platform.' }
        'SecureChannelFailure'  { return 'A secure (TLS) connection to the server could not be set up.' }
        'NameResolutionFailure' { return "The server name in $Base cannot be resolved." }
        'ConnectFailure'        { return "Cannot connect to the server at $Base." }
        'Timeout'               { return 'The server did not answer in time.' }
    }
    return "Request failed: $($err.Exception.Message)"
}

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
    Sync-TrayConfig
    $f = New-Object System.Windows.Forms.Form
    $f.Text = "Raise a Ticket - $($tpl.Name)"
    $f.Size = New-Object System.Drawing.Size(440, 350)
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
    $status.Location = '12,232'; $status.Size = '312,72'; $status.ForeColor = 'DimGray'; $f.Controls.Add($status)

    $submit = New-Object System.Windows.Forms.Button
    $submit.Text = 'Submit'; $submit.Location = '332,262'; $submit.Size = '80,28'; $f.Controls.Add($submit)
    $submit.Add_Click({
        $t = $title.Text.Trim()
        if ($t.Length -eq 0 -or $t -eq $tpl.Prefix.Trim()) { $status.ForeColor = 'Firebrick'; $status.Text = 'Please enter a title.'; return }
        Sync-TrayConfig
        if (-not (Test-Enrolled $status)) { return }
        $status.ForeColor = 'DimGray'; $status.Text = 'Submitting...'; $submit.Enabled = $false
        $uri = "$Base/api/agents/$AgentId/ticket"
        try {
            $body = @{
                title = $t; description = $desc.Text; type = $tpl.Type; priority = $tpl.Priority
                tags = @('user-raised', 'tray'); endpoint_info = (Get-EndpointInfo)
            } | ConvertTo-Json -Depth 5
            $r = Invoke-RestMethod -Method Post -Uri $uri -Headers $Headers -ContentType 'application/json' -Body $body
            $status.ForeColor = 'ForestGreen'; $status.Text = "Ticket $($r.ticket_number) created."
            Write-TrayLog "ticket $($r.ticket_number) created"
            Start-Sleep -Seconds 2; $f.Close()
        } catch {
            $why = Get-FailureText $_
            Write-TrayLog "ticket failed: POST $uri -> $why ($($_.Exception.Message))"
            $status.ForeColor = 'Firebrick'; $status.Text = "Ticket not sent. $why"; $submit.Enabled = $true
        }
    }.GetNewClosure())
    [void]$f.ShowDialog()
}

# ── Chat: initiate a session then open the shared chat window ────────────────────
function Start-ChatWithIT {
    Sync-TrayConfig
    $f = New-Object System.Windows.Forms.Form
    $f.Text = 'Chat with IT Support'; $f.Size = New-Object System.Drawing.Size(420, 300)
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
    $status.Location = '12,172'; $status.Size = '292,80'; $status.ForeColor = 'DimGray'; $f.Controls.Add($status)

    $go = New-Object System.Windows.Forms.Button
    $go.Text = 'Start Chat'; $go.Location = '312,196'; $go.Size = '84,28'; $f.Controls.Add($go)
    $go.Add_Click({
        if ($subj.Text.Trim().Length -eq 0 -or $msg.Text.Trim().Length -eq 0) {
            $status.ForeColor = 'Firebrick'; $status.Text = 'Subject and message are required.'; return
        }
        Sync-TrayConfig
        if (-not (Test-Enrolled $status)) { return }
        if (-not (Test-Path $ChatUi)) {
            Write-TrayLog "chat failed: chat window script missing at $ChatUi"
            $status.ForeColor = 'Firebrick'
            $status.Text = 'The chat window component is missing. Restart the OmniAgent service or reinstall the agent.'
            return
        }
        $status.ForeColor = 'DimGray'; $status.Text = 'Connecting...'; $go.Enabled = $false
        $uri = "$Base/api/agent-chat/sessions/initiate"
        try {
            $body = @{ agent_id = $AgentId; subject = $subj.Text.Trim(); message = $msg.Text.Trim() } | ConvertTo-Json
            $sess = Invoke-RestMethod -Method Post -Uri $uri -Headers $Headers -ContentType 'application/json' -Body $body
        } catch {
            $why = Get-FailureText $_
            Write-TrayLog "chat failed: POST $uri -> $why ($($_.Exception.Message))"
            $status.ForeColor = 'Firebrick'; $status.Text = "Chat not started. $why"; $go.Enabled = $true
            return
        }
        try {
            $sessCfg = @{
                session_id = $sess.id; backend_url = $Base; token = $Token
                subject = $subj.Text.Trim(); initial = ''; sender = ''
                accept_invalid_certs = [bool]$cfg.accept_invalid_certs
                server_cert_der_b64 = $cfg.server_cert_der_b64
            } | ConvertTo-Json
            # ProgramData is where the agent drops the admin's close signal, but
            # it can be read-only for standard users on hardened machines; the
            # window still closes when the session does (it polls the status).
            $sessPath = "$env:ProgramData\OmniAgent\chat_$($sess.id).json"
            try { Set-Content -Path $sessPath -Value $sessCfg -Encoding UTF8 }
            catch {
                $sessPath = Join-Path (Split-Path -Parent $TrayLog) "chat_$($sess.id).json"
                Set-Content -Path $sessPath -Value $sessCfg -Encoding UTF8
            }
            Start-Process powershell -ArgumentList @(
                '-NoProfile','-WindowStyle','Hidden','-ExecutionPolicy','Bypass','-File',"`"$ChatUi`"","`"$sessPath`"")
            Write-TrayLog "chat $($sess.id) started"
            $f.Close()
        } catch {
            Write-TrayLog "chat window failed to open for session $($sess.id): $($_.Exception.Message)"
            $status.ForeColor = 'Firebrick'
            $status.Text = "IT has your message, but the chat window could not open: $($_.Exception.Message)"
            $go.Enabled = $true
        }
    }.GetNewClosure())
    [void]$f.ShowDialog()
}

# ── Status ──────────────────────────────────────────────────────────────────────
function Show-Status($notify) {
    Sync-TrayConfig
    $svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    $state = if ($svc) { $svc.Status } else { 'Not installed' }
    $enrolled = if ($Token -and $AgentId) { 'connected' } elseif ($EnrollProblem) { "not connected - $EnrollProblem" } else { 'not connected yet' }
    $msg = "Agent service: $state`nServer: $Base`nAgent ID: $AgentId`nIT support: $enrolled"
    if ($msg.Length -gt 255) { $msg = $msg.Substring(0, 252) + '...' }   # balloon text limit
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
