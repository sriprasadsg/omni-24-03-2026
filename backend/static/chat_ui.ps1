param([Parameter(Mandatory=$true)][string]$ConfigPath)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$cfg      = Get-Content -Raw -Path $ConfigPath | ConvertFrom-Json
$Session  = $cfg.session_id
$Base     = $cfg.backend_url
$Token    = $cfg.token
$Headers  = @{ Authorization = "Bearer $Token" }
$MsgUrl   = "$Base/api/agent-chat/sessions/$Session/user-message"
$PollUrl  = "$Base/api/agent-chat/sessions/$Session/messages"
# The agent drops this file when the admin closes the session, for prompt teardown.
$CloseSig = [System.IO.Path]::Combine([System.IO.Path]::GetDirectoryName($ConfigPath), "chat_$Session.close")

# Only admin messages strictly newer than $script:Since are appended, so the
# window does not re-print history each poll. Start at "now" and show the opener
# below. Must be script-scoped: the timer handler updates it, and a bare $Since
# assignment inside the handler would shadow it in the child scope and re-fetch
# every admin message on every tick.
$script:Since = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()

$form               = New-Object System.Windows.Forms.Form
$form.Text          = "IT Support Chat" + $(if ($cfg.subject) { " - " + $cfg.subject } else { "" })
$form.Size          = New-Object System.Drawing.Size(460, 560)
$form.StartPosition = 'CenterScreen'
$form.TopMost       = $true

$log                = New-Object System.Windows.Forms.RichTextBox
$log.Location       = New-Object System.Drawing.Point(10, 10)
$log.Size           = New-Object System.Drawing.Size(425, 430)
$log.ReadOnly       = $true
$log.BackColor      = [System.Drawing.Color]::White
$form.Controls.Add($log)

$inputBox              = New-Object System.Windows.Forms.TextBox
$inputBox.Location     = New-Object System.Drawing.Point(10, 450)
$inputBox.Size         = New-Object System.Drawing.Size(330, 50)
$inputBox.Multiline    = $true
$form.Controls.Add($inputBox)

$send               = New-Object System.Windows.Forms.Button
$send.Location      = New-Object System.Drawing.Point(348, 450)
$send.Size          = New-Object System.Drawing.Size(87, 50)
$send.Text          = "Send"
$form.Controls.Add($send)

function Append([string]$who, [string]$text, $color) {
    $log.SelectionColor = $color
    $log.AppendText("$who`: ")
    $log.SelectionColor = [System.Drawing.Color]::Black
    $log.AppendText("$text`r`n")
    $log.ScrollToCaret()
}

if ($cfg.initial) {
    $who = if ($cfg.sender) { $cfg.sender } else { "Administrator" }
    Append $who $cfg.initial ([System.Drawing.Color]::Blue)
}

$sendAction = {
    $text = $inputBox.Text.Trim()
    if ($text.Length -eq 0) { return }
    try {
        $body = @{ content = $text } | ConvertTo-Json
        Invoke-RestMethod -Method Post -Uri $MsgUrl -Headers $Headers -ContentType 'application/json' -Body $body | Out-Null
        Append "You" $text ([System.Drawing.Color]::DarkGreen)
        $inputBox.Clear()
    } catch {
        Append "System" "Failed to send - check connection." ([System.Drawing.Color]::Red)
    }
}
$send.Add_Click($sendAction)
$inputBox.Add_KeyDown({
    if ($_.KeyCode -eq 'Return' -and -not $_.Shift) { $_.SuppressKeyPress = $true; & $sendAction }
})

$timer          = New-Object System.Windows.Forms.Timer
$timer.Interval = 3000
$timer.Add_Tick({
    if (Test-Path -Path $CloseSig) {
        Remove-Item -Path $CloseSig -ErrorAction SilentlyContinue
        Append "System" "This chat has been closed by the administrator." ([System.Drawing.Color]::Gray)
        $inputBox.Enabled = $false; $send.Enabled = $false; $timer.Stop()
        return
    }
    try {
        $resp = Invoke-RestMethod -Method Get -Uri "$PollUrl`?since=$script:Since" -Headers $Headers
        if ($resp.messages) {
            foreach ($m in $resp.messages) {
                $who = if ($m.sender_name) { $m.sender_name } else { "Administrator" }
                Append $who $m.content ([System.Drawing.Color]::Blue)
            }
            $script:Since = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
        }
        if ($resp.status -and $resp.status -ne 'active') {
            Append "System" "This chat has been closed by the administrator." ([System.Drawing.Color]::Gray)
            $inputBox.Enabled = $false; $send.Enabled = $false; $timer.Stop()
        }
    } catch { }
})
$timer.Start()

$form.Add_FormClosed({
    $timer.Stop()
    Remove-Item -Path $ConfigPath -ErrorAction SilentlyContinue
    Remove-Item -Path $CloseSig -ErrorAction SilentlyContinue
})
[System.Windows.Forms.Application]::Run($form)
