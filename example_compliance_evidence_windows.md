# Windows Security Compliance Audit - Evidence
**Date:** 2024-05-21
**Asset:** WIN-PROD-SQL-01 (10.0.0.25)
**Control:** NIST 800-53 IA-5 (Authenticator Management)

## 1. Local Account Status (PowerShell)
`Get-LocalUser | Select-Object Name,Enabled,PasswordRequired`

| Name | Enabled | PasswordRequired |
|------|---------|------------------|
| Administrator | False | True |
| Guest | False | False |
| SQLService | True | True |
| OmniAgent | True | True |

## 2. Password Policy (Security Policy)
`net accounts`

```cmd
Force user logoff how long after time expires?:       Never
Minimum password age (days):                          1
Maximum password age (days):                          42
Minimum password length:                              14
Length of password history maintained:                24
Lockout threshold:                                    5
Lockout duration (minutes):                           30
Lockout observation window (minutes):                 30
Computer role:                                        SERVER
```

## 3. Remote Desktop Configuration (Registry)
**Key:** `HKLM\System\CurrentControlSet\Control\Terminal Server\WinStations\RDP-Tcp`
**Value:** `UserAuthentication`
**Data:** `1` (NLA Enabled)

## 4. Recent Security Events (Get-WinEvent)
**Event ID 4624 (Logon Success)**
```
Logon Type: 3 (Network)
Account Name: OmniAgent
Workstation Name: WIN-PROD-SQL-01
Source Network Address: 10.0.0.5 (Management Server)
Time: 2024-05-21T09:15:00.000Z
```

## 5. Auditor Notes
- Built-in Administrator account is disabled (Compliant).
- Password complexity exceeds baseline requirements (14 chars vs 12).
- Network Level Authentication (NLA) is enforced for RDP.
