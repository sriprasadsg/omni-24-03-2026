"""Embedded PowerShell WinForms scripts for the remote-control consent flow.

Holds the two script constants that `consent_ui.py` spawns into the
interactive session. They are extracted into their own file purely for the
500-line source cap (CLAUDE.md) — the Python public surface, session
bookkeeping, spawn path, and tests all live in `consent_ui.py`. Nothing
here changes behaviour from what an inline constant would do; these are two
string constants and nothing else.

Both scripts receive the untrusted requester identity ONLY through a
per-session JSON config file read with `ConvertFrom-Json` (T-74-08). The
identity is never interpolated into the script text or the command line.
"""

# Consent dialog (74-UI-SPEC Surface 2). Arg 1 is the per-session config JSON
# path. Renders a fixed 440x240 always-on-top dialog naming the requesting
# admin and tenant, with Decline/Accept buttons and a `timeout_secs` countdown.
# Writes exactly one decision word (`accept`/`decline`/`timeout`) to
# `consent_{session}.decision` on every exit path before the process exits.
CONSENT_UI_PS = r"""
param([Parameter(Mandatory=$true)][string]$ConfigPath)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$cfg  = Get-Content -Raw -Path $ConfigPath | ConvertFrom-Json
$Session  = $cfg.session_id
$Dir      = [System.IO.Path]::GetDirectoryName($ConfigPath)
$DecFile  = [System.IO.Path]::Combine($Dir, "consent_$Session.decision")

function Write-Decision([string]$word) {
    [System.IO.File]::WriteAllText($DecFile, $word)
}

$form               = New-Object System.Windows.Forms.Form
$form.Text          = "Remote Support Request"
$form.Size          = New-Object System.Drawing.Size(440, 240)
$form.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::FixedDialog
$form.MaximizeBox   = $false
$form.MinimizeBox   = $false
$form.StartPosition = 'Manual'
$form.TopMost       = $true
$form.BackColor     = [System.Drawing.ColorTranslator]::FromHtml('#0b1220')
$screen = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$form.Location = New-Object System.Drawing.Point(
    [int]($screen.X + ($screen.Width  - $form.Width)  / 2),
    [int]($screen.Y + ($screen.Height - $form.Height) / 2))

$title               = New-Object System.Windows.Forms.Label
$title.Text          = "Remote Support Request"
$title.Location      = New-Object System.Drawing.Point(24, 22)
$title.Size          = New-Object System.Drawing.Size(390, 26)
$title.Font          = New-Object System.Drawing.Font("Segoe UI", 12, [System.Drawing.FontStyle]::Bold)
$title.ForeColor     = [System.Drawing.ColorTranslator]::FromHtml('#F8FAFC')
$form.Controls.Add($title)

$body                = New-Object System.Windows.Forms.Label
$body.Text           = "$($cfg.requester_name) ($($cfg.requester_email)) from $($cfg.tenant_name) is requesting to remotely control this computer."
# Identity labels wrap rather than truncate (D-03 backstop): fixed width, zero
# height + AutoSize lets a long name/tenant grow the label downward.
$body.AutoSize       = $true
$body.MaximumSize    = New-Object System.Drawing.Size(394, 0)
$body.Location       = New-Object System.Drawing.Point(24, 58)
$body.Font           = New-Object System.Drawing.Font("Segoe UI", 10)
$body.ForeColor      = [System.Drawing.ColorTranslator]::FromHtml('#F8FAFC')
$form.Controls.Add($body)

$sub                  = New-Object System.Windows.Forms.Label
$sub.Text             = "They will be able to see your screen and control your mouse and keyboard until you stop it or the session ends."
$sub.AutoSize         = $true
$sub.MaximumSize      = New-Object System.Drawing.Size(394, 0)
$sub.Location         = New-Object System.Drawing.Point(24, 110)
$sub.Font             = New-Object System.Drawing.Font("Segoe UI", 10)
$sub.ForeColor        = [System.Drawing.ColorTranslator]::FromHtml('#94A3B8')
$form.Controls.Add($sub)

$decline               = New-Object System.Windows.Forms.Button
$decline.Text          = "Decline"
$decline.Size          = New-Object System.Drawing.Size(96, 34)
$decline.Location      = New-Object System.Drawing.Point(228, 168)
$decline.Font          = New-Object System.Drawing.Font("Segoe UI", 10, [System.Drawing.FontStyle]::Bold)
$decline.BackColor     = [System.Drawing.ColorTranslator]::FromHtml('#DC2626')
$decline.ForeColor     = [System.Drawing.Color]::White
$decline.FlatStyle     = [System.Windows.Forms.FlatStyle]::Flat
$form.Controls.Add($decline)

$accept                = New-Object System.Windows.Forms.Button
$accept.Text           = "Accept"
$accept.Size           = New-Object System.Drawing.Size(96, 34)
$accept.Location       = New-Object System.Drawing.Point(332, 168)
$accept.Font           = New-Object System.Drawing.Font("Segoe UI", 10, [System.Drawing.FontStyle]::Bold)
$accept.BackColor      = [System.Drawing.ColorTranslator]::FromHtml('#0369A1')
$accept.ForeColor      = [System.Drawing.Color]::White
$accept.FlatStyle      = [System.Windows.Forms.FlatStyle]::Flat
$form.Controls.Add($accept)

$accept.Add_Click({
    Write-Decision 'accept'
    $form.Close()
})
$decline.Add_Click({
    Write-Decision 'decline'
    $form.Close()
})

# Timeout countdown: auto-declines (writes the timeout word) at timeout_secs.
$timer          = New-Object System.Windows.Forms.Timer
$timer.Interval = [int]($cfg.timeout_secs * 1000)
$timer.Add_Tick({
    $timer.Stop()
    Write-Decision 'timeout'
    $form.Close()
})
$timer.Start()

# Every exit path writes exactly one decision word. Add_FormClosed is the last
# line of defence: if the user closed via the window chrome, still write a
# word so the Python poller never hangs.
$form.Add_FormClosed({
    $timer.Stop()
    if (-not (Test-Path -Path $DecFile)) {
        Write-Decision 'decline'
    }
    Remove-Item -Path $ConfigPath -ErrorAction SilentlyContinue
})
[System.Windows.Forms.Application]::Run($form)
"""

# Persistent stop-control bar (74-UI-SPEC Surface 3). Arg 1 is the per-session
# config JSON path. Renders a fixed 360x48 top-centre always-on-top, non-movable
# bar naming the controlling admin with a pulsing red dot and a Stop Control
# button. Clicking Stop Control writes `stop_{session}.stop` and closes. A
# polling timer watches for a `stop_{session}.close` sentinel (written by the
# agent when the session ends by any other route) and self-closes on it.
STOP_BAR_PS = r"""
param([Parameter(Mandatory=$true)][string]$ConfigPath)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$cfg  = Get-Content -Raw -Path $ConfigPath | ConvertFrom-Json
$Session = $cfg.session_id
$Dir     = [System.IO.Path]::GetDirectoryName($ConfigPath)
$StopSig = [System.IO.Path]::Combine($Dir, "stop_$Session.stop")
$CloseSig= [System.IO.Path]::Combine($Dir, "stop_$Session.close")

$form                 = New-Object System.Windows.Forms.Form
$form.Size            = New-Object System.Drawing.Size(360, 48)
$form.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::None
$form.StartPosition   = 'Manual'
$form.TopMost         = $true
$form.BackColor       = [System.Drawing.ColorTranslator]::FromHtml('#0b1220')
$screen = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$form.Location = New-Object System.Drawing.Point(
    [int]($screen.X + ($screen.Width - $form.Width) / 2),
    [int]($screen.Y))

# Pulsing red dot toggled by a timer below.
$dot              = New-Object System.Windows.Forms.Label
$dot.Size         = New-Object System.Drawing.Size(14, 14)
$dot.Location     = New-Object System.Drawing.Point(16, 17)
$dot.BackColor    = [System.Drawing.ColorTranslator]::FromHtml('#DC2626')
$dot.ForeColor    = [System.Drawing.Color]::White
$dot.Text         = ""
$form.Controls.Add($dot)

$name                = New-Object System.Windows.Forms.Label
$name.Text           = "$($cfg.requester_name) is controlling this computer"
$name.Location       = New-Object System.Drawing.Point(38, 15)
$name.Size           = New-Object System.Drawing.Size(200, 18)
$name.Font           = New-Object System.Windows.Forms.Font("Segoe UI", 10)
$name.ForeColor      = [System.Drawing.ColorTranslator]::FromHtml('#F8FAFC')
# Fixed-width persistent bar: admin name truncates with an ellipsis, not wraps
# (Surface 3 backstop) — a non-identity-verification moment.
$name.AutoEllipsis   = $true
$form.Controls.Add($name)

$stop                 = New-Object System.Windows.Forms.Button
$stop.Text            = "Stop Control"
$stop.Size            = New-Object System.Drawing.Size(110, 32)
$stop.Location        = New-Object System.Drawing.Point(240, 8)
$stop.Font            = New-Object System.Windows.Forms.Font("Segoe UI", 10, [System.Windows.Forms.FontStyle]::Bold)
$stop.BackColor       = [System.Drawing.ColorTranslator]::FromHtml('#DC2626')
$stop.ForeColor       = [System.Drawing.Color]::White
$stop.FlatStyle       = [System.Windows.Forms.FlatStyle]::Flat
$form.Controls.Add($stop)

# Immediate one-click revocation — no confirmation (D-09).
$stop.Add_Click({
    [System.IO.File]::WriteAllText($StopSig, 'stop')
    $form.Close()
})

$pulse = New-Object System.Windows.Forms.Timer
$pulse.Interval = 500
$pulseVisible = $true
$pulse.Add_Tick({
    $script:pulseVisible = -not $script:pulseVisible
    $dot.Visible = $script:pulseVisible
})
$pulse.Start()

# Self-close when the agent writes the .close sentinel (session ended by any
# other route: admin disconnect, platform force-kill, tunnel drop).
$watch = New-Object System.Windows.Forms.Timer
$watch.Interval = 500
$watch.Add_Tick({
    if (Test-Path -Path $CloseSig) {
        $watch.Stop(); $pulse.Stop()
        Remove-Item -Path $CloseSig -ErrorAction SilentlyContinue
        $form.Close()
    }
})
$watch.Start()

$form.Add_FormClosed({
    $pulse.Stop(); $watch.Stop()
    Remove-Item -Path $ConfigPath -ErrorAction SilentlyContinue
})
[System.Windows.Forms.Application]::Run($form)
"""