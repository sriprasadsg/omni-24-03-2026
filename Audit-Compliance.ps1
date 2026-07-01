# Audit-Compliance.ps1
# Generates a Markdown-formatted compliance evidence report for Windows systems.

$Hostname = $env:COMPUTERNAME
$IpAddr = (Get-NetIPAddress -AddressFamily IPv4 -InterfaceAlias *Ethernet* | Select-Object -First 1).IPAddress
$Date = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$OutputFile = "compliance_evidence_NO_$Hostname.md"

"Generating compliance report for $Hostname..."

"# Windows Security Compliance Audit - Evidence" | Out-File $OutputFile -Encoding utf8
"**Date:** $Date" | Out-File $OutputFile -Append -Encoding utf8
"**Asset:** $Hostname ($IpAddr)" | Out-File $OutputFile -Append -Encoding utf8
"**Control:** Windows Baseline Audit" | Out-File $OutputFile -Append -Encoding utf8
"" | Out-File $OutputFile -Append -Encoding utf8

"## 1. Local Account Status" | Out-File $OutputFile -Append -Encoding utf8
"Running \`Get-LocalUser\`..."
"" | Out-File $OutputFile -Append -Encoding utf8
"| Name | Enabled | PasswordRequired |" | Out-File $OutputFile -Append -Encoding utf8
"|------|---------|------------------|" | Out-File $OutputFile -Append -Encoding utf8
Get-LocalUser | ForEach-Object { "| $($_.Name) | $($_.Enabled) | $($_.PasswordRequired) |" } | Out-File $OutputFile -Append -Encoding utf8
"" | Out-File $OutputFile -Append -Encoding utf8

"## 2. Password Policy" | Out-File $OutputFile -Append -Encoding utf8
'```cmd' | Out-File $OutputFile -Append -Encoding utf8
net accounts | Out-String | Select-Object -First 10 | Out-File $OutputFile -Append -Encoding utf8
'```' | Out-File $OutputFile -Append -Encoding utf8
"" | Out-File $OutputFile -Append -Encoding utf8

"## 3. Remote Desktop Configuration (NLA)" | Out-File $OutputFile -Append -Encoding utf8
try {
    $RDP = Get-ItemProperty "HKLM:\System\CurrentControlSet\Control\Terminal Server\WinStations\RDP-Tcp" -Name "UserAuthentication" -ErrorAction Stop
    "**Registry Key:** HKLM...RDP-Tcp" | Out-File $OutputFile -Append -Encoding utf8
    "**NLA Enabled:** $(if ($RDP.UserAuthentication -eq 1) { 'Yes (Compliant)' } else { 'No (High Risk)' })" | Out-File $OutputFile -Append -Encoding utf8
}
catch {
    "Could not read RDP Registry key." | Out-File $OutputFile -Append -Encoding utf8
}
"" | Out-File $OutputFile -Append -Encoding utf8

"## 4. Recent Security Events" | Out-File $OutputFile -Append -Encoding utf8
'```' | Out-File $OutputFile -Append -Encoding utf8
Get-WinEvent -LogName Security -MaxEvents 5 | Select-Object TimeCreated, Id, Message | Format-Table -AutoSize | Out-String -Width 200 | Out-File $OutputFile -Append -Encoding utf8
'```' | Out-File $OutputFile -Append -Encoding utf8

"Report generated: $OutputFile"
