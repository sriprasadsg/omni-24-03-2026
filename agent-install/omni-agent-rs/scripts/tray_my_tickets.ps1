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

# ---- Part 1: the answer check ----------------------------------------------------------------

# State shared by the timer, the balloon and the window: one hashtable, so every closure sees it.
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

# ---- Part 2: the My tickets window and the article window ------------------------------------

# Multiline text boxes need CR LF line ends.
function ConvertTo-Crlf([string]$text) {
    return ($text -replace "`r?`n", "`r`n")
}

# 'Nov 8, 14:05' in the user's own time zone; the server's text when it is not a date.
function Format-TrayTime([string]$iso) {
    try {
        $inv = [System.Globalization.CultureInfo]::InvariantCulture
        $d = [datetime]::Parse($iso, $inv, [System.Globalization.DateTimeStyles]::RoundtripKind)
        return $d.ToLocalTime().ToString('MMM d, HH:mm', $inv)
    } catch { return $iso }
}

# The conversation as plain text, oldest first, a blank line between entries. Only entries the server
# marked visible to the requester arrive here. A withdrawn answer shows only the server's notice.
function Get-ConversationText($tk) {
    $mark = 'AI-assisted answer from your IT knowledge base'
    $blocks = @()
    foreach ($en in $tk.entries) {
        $text = [string]$en.text
        if ([string]$en.kind -eq 'withdrawn') { $blocks += $text; continue }
        $lines = @(("{0}  {1}" -f (Format-TrayTime ([string]$en.at)), [string]$en.heading).TrimEnd())
        if ([string]$en.kind -eq 'answer' -and -not $text.StartsWith($mark)) { $lines += $mark }
        $lines += $text
        if ([string]$en.kind -eq 'answer') {
            $names = @()
            foreach ($ci in $en.citations) { if ($ci.title) { $names += [string]$ci.title } }
            if ($names.Count -gt 0) { $lines += 'Based on: ' + ($names -join '; ') }
        }
        $blocks += ($lines -join "`n")
    }
    return (ConvertTo-Crlf ($blocks -join "`n`n"))
}

# A cited article, read only: one text box, plain text, no links.
function Show-TrayArticle([string]$ticketId, [string]$articleId, [string]$title) {
    Sync-TrayConfig
    $f = New-Object System.Windows.Forms.Form
    $f.Text = "Article - $title"
    $f.ClientSize = New-Object System.Drawing.Size(520, 432)
    $f.StartPosition = 'CenterScreen'; $f.TopMost = $true
    $f.FormBorderStyle = 'FixedDialog'; $f.MaximizeBox = $false; $f.MinimizeBox = $false

    $box = New-Object System.Windows.Forms.TextBox
    $box.Location = '12,12'; $box.Size = '480,340'; $box.Multiline = $true; $box.ReadOnly = $true
    $box.ScrollBars = 'Vertical'; $box.BackColor = [System.Drawing.Color]::White
    $box.Text = 'Loading...'; $box.AccessibleName = 'Article'
    $f.Controls.Add($box)

    $btnClose = New-Object System.Windows.Forms.Button
    $btnClose.Text = 'Close'; $btnClose.Location = '412,364'; $btnClose.Size = '80,28'
    $btnClose.AccessibleName = 'Close'
    $btnClose.Add_Click({ $f.Close() }.GetNewClosure())
    $f.Controls.Add($btnClose)
    $f.CancelButton = $btnClose

    $f.Add_Shown({
        if (-not (Test-Enrolled $box)) { return }
        $uri = "$Base/api/agents/$AgentId/tray/tickets/$ticketId/articles/$articleId?user=" + [uri]::EscapeDataString($env:USERNAME)
        try {
            $ar = Invoke-RestMethod -Method Get -Uri $uri -Headers $Headers -TimeoutSec 10
            if ($ar.available -eq $false -or -not $ar.content) {
                $box.Text = 'This article is no longer available.'
            } else {
                if ($ar.title) { $f.Text = "Article - $([string]$ar.title)" }
                $box.Text = ConvertTo-Crlf ([string]$ar.content)
                $box.SelectionStart = 0; $box.SelectionLength = 0
            }
        } catch {
            $why = Get-FailureText $_
            Write-TrayLog "article failed: GET $uri -> $why ($($_.Exception.Message))"
            # The server answered (the article is gone or not cited on this ticket), or it did not.
            if (Get-ErrorStatusCode $_) { $box.Text = 'This article is no longer available.' }
            else { $box.ForeColor = 'Firebrick'; $box.Text = "Couldn't load this article. $why" }
        }
    }.GetNewClosure())
    [void]$f.ShowDialog()
}

# The My tickets window. $selectId (from the balloon) picks the ticket to show first.
function Show-MyTickets([string]$selectId) {
    $watch = $script:TicketWatch
    if ($watch -and $watch.WindowOpen) { return }   # one window at a time
    Sync-TrayConfig

    $f = New-Object System.Windows.Forms.Form
    $f.Text = 'My tickets'
    $f.ClientSize = New-Object System.Drawing.Size(800, 560)   # 800x560, every control sits on a 4 px grid
    $f.StartPosition = 'CenterScreen'; $f.TopMost = $true
    $f.FormBorderStyle = 'FixedDialog'; $f.MaximizeBox = $false; $f.MinimizeBox = $false
    $f.AutoScaleMode = 'None'; $f.AcceptButton = $null

    $lblList = New-Object System.Windows.Forms.Label
    $lblList.Text = 'Your tickets'; $lblList.Location = '12,12'; $lblList.AutoSize = $true; $f.Controls.Add($lblList)

    $list = New-Object System.Windows.Forms.ListView
    $list.Location = '12,32'; $list.Size = '292,400'; $list.View = 'Details'; $list.FullRowSelect = $true
    $list.MultiSelect = $false; $list.HideSelection = $false
    [void]$list.Columns.Add('Ticket', 64); [void]$list.Columns.Add('Title', 140); [void]$list.Columns.Add('Status', 80)
    $list.AccessibleName = 'Your tickets'; $list.TabIndex = 0
    $f.Controls.Add($list)

    $lblFootnote = New-Object System.Windows.Forms.Label
    $lblFootnote.Location = '12,436'; $lblFootnote.Size = '292,32'; $lblFootnote.ForeColor = 'DimGray'
    $lblFootnote.UseMnemonic = $false; $f.Controls.Add($lblFootnote)

    $lblTitle = New-Object System.Windows.Forms.Label
    $lblTitle.Location = '320,12'; $lblTitle.Size = '456,20'; $lblTitle.AutoEllipsis = $true; $lblTitle.UseMnemonic = $false
    $lblTitle.Font = New-Object System.Drawing.Font($f.Font, [System.Drawing.FontStyle]::Bold)
    $f.Controls.Add($lblTitle)

    $lblStatus = New-Object System.Windows.Forms.Label
    $lblStatus.Location = '320,36'; $lblStatus.Size = '456,20'; $lblStatus.ForeColor = 'DimGray'
    $lblStatus.AutoEllipsis = $true; $lblStatus.UseMnemonic = $false
    $f.Controls.Add($lblStatus)

    $convo = New-Object System.Windows.Forms.TextBox
    $convo.Location = '320,56'; $convo.Size = '456,252'; $convo.Multiline = $true; $convo.ReadOnly = $true
    $convo.ScrollBars = 'Vertical'; $convo.BackColor = [System.Drawing.Color]::White
    $convo.AccessibleName = 'Conversation'; $convo.TabIndex = 1
    $f.Controls.Add($convo)

    $lblBased = New-Object System.Windows.Forms.Label
    $lblBased.Text = 'Based on these articles (click one to read it):'
    $lblBased.Location = '320,312'; $lblBased.Size = '456,16'; $f.Controls.Add($lblBased)

    $links = New-Object System.Windows.Forms.FlowLayoutPanel
    $links.Location = '320,332'; $links.Size = '456,44'; $links.AutoScroll = $true
    $links.FlowDirection = 'TopDown'; $links.WrapContents = $false
    $links.AccessibleName = 'Based on these articles'; $links.TabIndex = 2
    $f.Controls.Add($links)

    $lblFooter = New-Object System.Windows.Forms.Label
    $lblFooter.Location = '320,380'; $lblFooter.Size = '456,32'; $lblFooter.ForeColor = 'DimGray'; $lblFooter.Visible = $false
    $f.Controls.Add($lblFooter)

    $lblNote = New-Object System.Windows.Forms.Label
    $lblNote.Text = 'Tell IT what is still wrong (optional)'
    $lblNote.Location = '320,416'; $lblNote.Size = '456,16'; $lblNote.Visible = $false; $f.Controls.Add($lblNote)

    $note = New-Object System.Windows.Forms.TextBox
    $note.Location = '320,432'; $note.Size = '456,24'; $note.MaxLength = 500; $note.Visible = $false
    $note.AccessibleName = 'Tell IT what is still wrong (optional)'; $note.TabIndex = 3
    $f.Controls.Add($note)

    $btnFixed = New-Object System.Windows.Forms.Button
    $btnFixed.Text = 'This fixed it'; $btnFixed.Location = '320,464'; $btnFixed.Size = '112,28'
    $btnFixed.Enabled = $false; $btnFixed.AccessibleName = 'This fixed it'; $btnFixed.TabIndex = 4
    $f.Controls.Add($btnFixed)

    $btnHelp = New-Object System.Windows.Forms.Button
    $btnHelp.Text = 'I still need help'; $btnHelp.Location = '440,464'; $btnHelp.Size = '132,28'
    $btnHelp.Enabled = $false; $btnHelp.AccessibleName = 'I still need help'; $btnHelp.TabIndex = 5
    $f.Controls.Add($btnHelp)

    $btnRefresh = New-Object System.Windows.Forms.Button
    $btnRefresh.Text = 'Refresh tickets'; $btnRefresh.Location = '580,464'; $btnRefresh.Size = '100,28'
    $btnRefresh.AccessibleName = 'Refresh tickets'; $btnRefresh.TabIndex = 6
    $f.Controls.Add($btnRefresh)

    $btnClose = New-Object System.Windows.Forms.Button
    $btnClose.Text = 'Close'; $btnClose.Location = '688,464'; $btnClose.Size = '88,28'
    $btnClose.AccessibleName = 'Close'; $btnClose.TabIndex = 7
    $btnClose.Add_Click({ $f.Close() }.GetNewClosure())
    $f.Controls.Add($btnClose)
    $f.CancelButton = $btnClose

    $lblFeedback = New-Object System.Windows.Forms.Label
    $lblFeedback.Location = '12,500'; $lblFeedback.Size = '764,40'; $lblFeedback.ForeColor = 'DimGray'
    $lblFeedback.Text = 'Loading your tickets...'; $lblFeedback.UseMnemonic = $false
    $f.Controls.Add($lblFeedback)

    # One object holds what the handlers share; every handler below is a closure over it.
    $ui = @{ Tickets = @(); Current = $null; Filling = $false; Empty = ''; Footer = '' }
    $say = { param([string]$text, [string]$color) $lblFeedback.ForeColor = $color; $lblFeedback.Text = $text; $lblFeedback.Refresh() }.GetNewClosure()

    # Show one ticket: title, status or reason, conversation, cited articles, and which buttons work.
    $ui.Show = {
        param($tk)
        $ui.Current = $tk
        $links.Controls.Clear()
        $lblFooter.Visible = $false; $lblNote.Visible = $false; $note.Visible = $false
        $btnFixed.Enabled = $false; $btnHelp.Enabled = $false
        if (-not $tk) {
            $lblTitle.Text = ''; $lblStatus.Text = ''; $convo.Text = ''
            if ($ui.Tickets.Count -eq 0) { $convo.Text = $ui.Empty }
            return
        }
        $ticketId = [string]$tk.id
        $lblTitle.Text = "$([string]$tk.number)  $([string]$tk.title)"
        $reason = [string]$tk.reasonLine
        $lblStatus.Text = if ($reason) { $reason } else { [string]$tk.statusText }
        $convo.Text = Get-ConversationText $tk
        $convo.SelectionStart = $convo.TextLength; $convo.ScrollToCaret()
        $shown = @{}
        foreach ($en in $tk.entries) {
            foreach ($ci in $en.citations) {
                $articleId = [string]$ci.articleId
                if (-not $articleId -or $shown.ContainsKey($articleId)) { continue }
                $shown[$articleId] = $true
                $articleTitle = [string]$ci.title
                $ll = New-Object System.Windows.Forms.LinkLabel
                $ll.Text = $articleTitle; $ll.AutoSize = $false; $ll.Size = '436,16'; $ll.AutoEllipsis = $true
                $ll.UseMnemonic = $false; $ll.AccessibleName = $articleTitle
                $ll.Add_LinkClicked({ Show-TrayArticle $ticketId $articleId $articleTitle }.GetNewClosure())
                $links.Controls.Add($ll)
            }
        }
        $btnFixed.Enabled = [bool]$tk.canConfirm
        $btnHelp.Enabled = [bool]$tk.canHelp
        $lblFooter.Text = $ui.Footer
        $lblFooter.Visible = [bool]$tk.canConfirm -and [bool]$ui.Footer
        $lblNote.Visible = [bool]$tk.canHelp; $note.Visible = [bool]$tk.canHelp
        Set-AnswersRead $tk.answerIds
    }.GetNewClosure()

    # Load the list. A failure keeps the last list on screen; Refresh tickets tries again.
    $ui.Load = {
        param([string]$keepId, [bool]$keepMessage)
        Sync-TrayConfig
        if (-not (Test-Enrolled $lblFeedback)) { return }
        if (-not $keepMessage) { & $say 'Loading your tickets...' 'DimGray' }
        $btnRefresh.Enabled = $false
        try {
            $lr = Get-TrayTicketList
        } catch {
            $why = Get-FailureText $_
            Write-TrayLog "my tickets failed: GET list -> $why ($($_.Exception.Message))"
            & $say "Couldn't load your tickets. $why" 'Firebrick'
            return
        } finally { $btnRefresh.Enabled = $true }
        $dp = $lr.display
        $user = if ($lr.user) { [string]$lr.user } else { [string]$env:USERNAME }
        $lblFootnote.Text = if ($dp.footnote) { [string]$dp.footnote } else { "Showing tickets you raised from this computer as $user." }
        $ui.Footer = [string]$dp.footer
        $ui.Empty = if ($dp.empty) { [string]$dp.empty } else { "You haven't raised any tickets from this computer yet. Choose Raise a Ticket in the tray menu." }
        $ui.Tickets = @($lr.tickets | Where-Object { $null -ne $_ })
        $ui.Filling = $true
        $list.BeginUpdate(); $list.Items.Clear()
        $pick = $null
        foreach ($tk in $ui.Tickets) {
            $item = New-Object System.Windows.Forms.ListViewItem ([string]$tk.number)
            [void]$item.SubItems.Add([string]$tk.title)
            [void]$item.SubItems.Add([string]$tk.statusText)
            $item.Name = [string]$tk.id
            [void]$list.Items.Add($item)
            if (-not $pick) { $pick = $item }                                  # newest first
            if ($keepId -and [string]$tk.id -eq $keepId) { $pick = $item }    # or the one that was open
        }
        $list.EndUpdate()
        $ui.Filling = $false
        if (-not $keepMessage) { & $say '' 'DimGray' }
        if ($pick) { $pick.Selected = $true; $pick.EnsureVisible() }
        else { & $ui.Show $null }
    }.GetNewClosure()

    $list.Add_SelectedIndexChanged({
        if ($ui.Filling) { return }
        if ($list.SelectedItems.Count -eq 0) { return }
        $id = $list.SelectedItems[0].Name
        foreach ($tk in $ui.Tickets) { if ([string]$tk.id -eq $id) { & $ui.Show $tk; break } }
    }.GetNewClosure())

    # This fixed it / I still need help: one request, the clicked button off while it runs.
    $act = {
        param([string]$which)
        $tk = $ui.Current
        if (-not $tk) { return }
        Sync-TrayConfig
        if (-not (Test-Enrolled $lblFeedback)) { return }
        $ticketId = [string]$tk.id
        $btn = if ($which -eq 'confirm') { $btnFixed } else { $btnHelp }
        $btn.Enabled = $false
        & $say 'Saving...' 'DimGray'
        $user = [string]$env:USERNAME
        if ($which -eq 'confirm') {
            $uri = "$Base/api/agents/$AgentId/tray/tickets/$ticketId/confirm"
            $payload = @{ user = $user } | ConvertTo-Json
            $done = 'Thanks. Your ticket is marked resolved.'
        } else {
            $uri = "$Base/api/agents/$AgentId/tray/tickets/$ticketId/help"
            $text = $note.Text.Trim()
            if ($text.Length -gt 500) { $text = $text.Substring(0, 500) }
            $payload = @{ user = $user; text = $text } | ConvertTo-Json
            $done = 'Sent to IT. A person will take over.'
        }
        try {
            [void](Invoke-RestMethod -Method Post -Uri $uri -Headers $Headers -ContentType 'application/json; charset=utf-8' -Body ([System.Text.Encoding]::UTF8.GetBytes($payload)) -TimeoutSec 10)
        } catch {
            $why = Get-FailureText $_
            Write-TrayLog "my tickets failed: POST $uri -> $why ($($_.Exception.Message))"
            & $say "Couldn't send that. $why" 'Firebrick'
            $btn.Enabled = $true
            return
        }
        if ($which -eq 'help') { $note.Text = '' }
        & $say $done 'ForestGreen'
        & $ui.Load $ticketId $true
    }.GetNewClosure()

    $btnFixed.Add_Click({ & $act 'confirm' }.GetNewClosure())
    $btnHelp.Add_Click({ & $act 'help' }.GetNewClosure())
    $btnRefresh.Add_Click({ & $ui.Load ([string]$ui.Current.id) $false }.GetNewClosure())
    $f.Add_Shown({ & $ui.Load $selectId $false }.GetNewClosure())

    if ($watch) { $watch.WindowOpen = $true }
    try { [void]$f.ShowDialog() }
    finally { if ($watch) { $watch.WindowOpen = $false } }
}
