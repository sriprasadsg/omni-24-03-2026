# Windows Security Compliance Audit - Evidence
**Date:** 2025-12-11 18:55:52
**Asset:** EILT0197 (169.254.237.112)
**Control:** Windows Baseline Audit

## 1. Local Account Status

| Name | Enabled | PasswordRequired |
|------|---------|------------------|
| admin | True | False |
| Administrator | False | True |
| DefaultAccount | False | False |
| Guest | False | False |
| WDAGUtilityAccount | False | True |

## 2. Password Policy
```cmd
Force user logoff how long after time expires?:       Never
Minimum password age (days):                          1
Maximum password age (days):                          45
Minimum password length:                              14
Length of password history maintained:                24
Lockout threshold:                                    5
Lockout duration (minutes):                           Never
Lockout observation window (minutes):                 5
Computer role:                                        WORKSTATION
The command completed successfully.


```

## 3. Remote Desktop Configuration (NLA)
**Registry Key:** HKLM...RDP-Tcp
**NLA Enabled:** Yes (Compliant)

## 4. Recent Security Events
```
```
