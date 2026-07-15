' OmniAgent tray launcher — starts the tray helper with NO window at all.
'
' The tray must live only as a notification-area icon. Launching powershell.exe
' from the logon task (even with -WindowStyle Hidden) creates a console window
' the user can close, which kills the NotifyIcon. wscript is a GUI-subsystem
' host, so Run(cmd, 0, False) starts powershell with a hidden window and no
' console flash. The background telemetry runs in the separate session-0
' service and is unaffected by this UI process.
Option Explicit
Dim sh, script, cmd
Set sh = CreateObject("WScript.Shell")
script = sh.ExpandEnvironmentStrings("%ProgramData%") & "\OmniAgent\tray_icon.ps1"
cmd = "powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & script & """"
' 0 = hidden window, False = don't wait (launcher exits immediately)
sh.Run cmd, 0, False
