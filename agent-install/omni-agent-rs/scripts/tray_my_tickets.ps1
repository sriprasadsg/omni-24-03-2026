<#
    OmniAgent tray: My tickets (the requester's side of the service desk).

    Dot-sourced by tray_icon.ps1 from the same folder, so it shares that script's scope:
    Sync-TrayConfig, Test-Enrolled, Get-FailureText, Write-TrayLog and the $Base, $AgentId,
    $Headers and $Token values it sets. Nothing here runs on its own.

    Talks only to the tray routes of the service desk (see backend/service_desk/tray_contract.py, which
    is frozen once an agent that carries this window is published). Every display string the window
    shows comes from the server; only the fixed labels of the window live here. Server text is shown
    as text and is never evaluated.

    Part 1: the answer check (a timer, a balloon, the menu count).
    Part 2: the My tickets window and the article window.
#>

# ----------------------------------------------------------------------------------------------
# Part 1: the answer check
# ----------------------------------------------------------------------------------------------

# State shared by the timer, the balloon and the window. One hashtable, so the closures that capture
# it all see the same object.
$script:TicketWatch = $null

function Get-SeenPath {
    $root = if ($env:LOCALAPPDATA) { $env:LOCALAPPDATA } else { $env:TEMP }
    return (Join-Path $root 'OmniAgent\tray-seen.json')
}

# tray-seen.json keeps two lists of answer ids on this computer: the ones already announced in a
# balloon (each answer pops up once) and the ones the user has opened (they stop counting as new).
function Read-TraySeen {
    $seen = @{ popped = @(); read = @() }
    try {
        $path = Get-SeenPath
        if (Test-Path $path) {
            $j = Get-Content -Raw -Path $path | ConvertFrom-Json
            if ($j.popped) { $seen.popped = @($j.popped | ForEach-Object { [string]$_ }) }
            if ($j.read)   { $seen.read   = @($j.read   | ForEach-Object { [string]$_ }) }
        }
    } catch { Write-TrayLog "tray-seen.json could not be read: $($_.Exception.Message)" }
    return $seen
}

function Write-TraySeen($seen) {
    try {
        $path = Get-SeenPath
        $dir = Split-Path -Parent $path
        if (-not (Test-Path $dir)) { [void](New-Item -ItemType Directory -Path $dir -Force) }
        $out = @{
            popped = @($seen.popped | Select-Object -Last 200)
            read   = @($seen.read   | Select-Object -Last 200)
        } | ConvertTo-Json -Depth 3
        Set-Content -Path $path -Value $out -Encoding UTF8
    } catch { Write-TrayLog "tray-seen.json could not be written: $($_.Exception.Message)" }
}

# 'My tickets ({n} new)' only when n is at least 1, otherwise 'My tickets'.
function Update-TicketMenu {
    $w = $script:TicketWatch
    if (-not $w -or -not $w.MenuItem) { return }
    $n = @($w.UnreadIds).Count
    $w.MenuItem.Text = if ($n -ge 1) { 'My tickets ({0} new)' -f $n } else { 'My tickets' }
}

# The user opened these answers: they are no longer new.
function Set-AnswersRead($ids) {
    $w = $script:TicketWatch
    $ids = @($ids | Where-Object { $_ } | ForEach-Object { [string]$_ })
    if ($ids.Count -eq 0) { return }
    $seen = Read-TraySeen
    $seen.read = @($seen.read) + @($ids | Where-Object { $seen.read -notcontains $_ })
    Write-TraySeen $seen
    if ($w) {
        $w.UnreadIds = @($w.UnreadIds | Where-Object { $ids -notcontains $_ })
        Update-TicketMenu
    }
}

# The list of this computer's tickets for the signed-in Windows user. The user name is soft scoping
# between people who share one computer, not a security boundary.
function Get-TrayTicketList {
    $uri = "$Base/api/agents/$AgentId/tray/tickets?user=" + [uri]::EscapeDataString($env:USERNAME)
    return Invoke-RestMethod -Method Get -Uri $uri -Headers $Headers -TimeoutSec 10
}

# The user raised a ticket: check every 30 seconds for the next 3 minutes.
function Start-TicketWatch {
    $w = $script:TicketWatch
    if (-not $w) { return }
    $w.FastUntil = (Get-Date).AddSeconds($w.FastWindowSeconds)
    $w.HasOpen = $true
}

# One check. A failure is logged and never shown: nobody asked for this request.
function Invoke-TicketPoll {
    $w = $script:TicketWatch
    if (-not $w -or $w.Busy) { return }
    Sync-TrayConfig
    if (-not ($Token -and $AgentId)) { return }
    $w.Busy = $true
    try {
        $lr = Get-TrayTicketList
        $w.LastPoll = Get-Date
        $seen = Read-TraySeen
        $open = $false
        $unread = @()
        $fresh = @()
        $pop = $null
        foreach ($tk in $lr.tickets) {
            if (@('resolved', 'closed') -notcontains [string]$tk.status) { $open = $true }
            foreach ($answerId in $tk.answerIds) {
                $a = [string]$answerId
                if (-not $a -or ($seen.read -contains $a)) { continue }
                $unread += $a
                if ($seen.popped -notcontains $a) {
                    $fresh += $a
                    if (-not $pop) { $pop = $tk }   # the list is newest first
                }
            }
        }
        $w.HasOpen = $open
        $w.UnreadIds = $unread
        Update-TicketMenu
        if ($pop) {
            $seen.popped = @($seen.popped) + $fresh
            Write-TraySeen $seen
            # One balloon, whatever the number of new answers; the text is cut so it stays under the
            # 255 character balloon limit.
            $head = "$([string]$pop.number): "
            $tail = '. Click to read it.'
            $room = 255 - $head.Length - $tail.Length
            $name = [string]$pop.title
            if ($name.Length -gt $room) { $name = $name.Substring(0, [Math]::Max(0, $room - 3)) + '...' }
            $w.PendingTicketId = [string]$pop.id
            $w.Notify.BalloonTipTitle = 'Your ticket has an answer'
            $w.Notify.BalloonTipText = $head + $name + $tail
            $w.Notify.ShowBalloonTip(10000)
        }
    } catch {
        Write-TrayLog "ticket check failed: $(Get-FailureText $_) ($($_.Exception.Message))"
    } finally {
        $w.Busy = $false
    }
}

# Called once, before Application.Run, with the menu item and the notify icon. The timer ticks every
# 30 seconds on the tray's own thread; whether a tick makes a request depends on the time since the
# user raised a ticket and on whether an open ticket exists.
function Initialize-TicketWatch($menuItem, $notify) {
    $w = @{
        MenuItem = $menuItem; Notify = $notify; Timer = $null
        FastSeconds = 30; FastWindowSeconds = 180; SlowSeconds = 300
        FastUntil = [datetime]::MinValue; LastPoll = [datetime]::MinValue
        HasOpen = $true          # unknown until the first check, so the first tick looks
        UnreadIds = @(); PendingTicketId = $null; Busy = $false; WindowOpen = $false
    }
    $script:TicketWatch = $w

    $timer = New-Object System.Windows.Forms.Timer
    $timer.Interval = $w.FastSeconds * 1000
    $timer.Add_Tick({
        try {
            $now = Get-Date
            $fast = $now -lt $w.FastUntil
            $slowDue = $w.HasOpen -and (($now - $w.LastPoll).TotalSeconds -ge $w.SlowSeconds)
            if ($fast -or $slowDue) { Invoke-TicketPoll }
        } catch { Write-TrayLog "ticket check tick failed: $($_.Exception.Message)" }
    }.GetNewClosure())
    $w.Timer = $timer

    # Clicking the answer balloon opens My tickets on that ticket. Other balloons (Agent Status)
    # clear PendingTicketId first, so they open nothing.
    $notify.Add_BalloonTipClicked({
        $id = $w.PendingTicketId
        $w.PendingTicketId = $null
        if ($id) {
            try { Show-MyTickets $id } catch { Write-TrayLog "My tickets failed to open: $($_.Exception.Message)" }
        }
    }.GetNewClosure())
    $notify.Add_BalloonTipClosed({ $w.PendingTicketId = $null }.GetNewClosure())

    $timer.Start()
}

# ----------------------------------------------------------------------------------------------
# Part 2: the My tickets window (added by the next commit of this plan)
# ----------------------------------------------------------------------------------------------

function Show-MyTickets([string]$selectId) {
    [void][System.Windows.Forms.MessageBox]::Show('My tickets is not available in this build.', 'My tickets')
}
