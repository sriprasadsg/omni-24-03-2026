# System Compliance Audit - Evidence
**Date:** 2024-05-20
**Asset:** web-server-01 (10.0.0.15)
**Control:** NIST 800-53 AC-2 (Account Management)

## 1. User Account Status
The following user accounts are currently active on the system:

| Username | UID | GID | Groups | Status |
|----------|-----|-----|--------|--------|
| root     | 0   | 0   | root   | Active |
| admin    | 1001| 1001| sudo,wheel | Active |
| deploy   | 1002| 1002| www-data | Active |

## 2. Password Policy Configuration (`/etc/login.defs`)
```bash
PASS_MAX_DAYS   90
PASS_MIN_DAYS   7
PASS_MIN_LEN    12
PASS_WARN_AGE   14
```

## 3. Recent Auth Logs (`/var/log/auth.log`)
```log
May 20 08:00:01 web-server-01 sshd[12345]: Accepted publickey for admin from 192.168.1.50 port 54321 ssh2
May 20 08:15:22 web-server-01 sudo:    admin : TTY=pts/0 ; PWD=/home/admin ; USER=root ; COMMAND=/usr/bin/apt update
May 20 09:00:00 web-server-01 CRONG[12400]: pam_unix(cron:session): session opened for user root by (uid=0)
```

## 4. Auditor Notes
- Password aging safeguards are correctly implemented.
- Root access is restricted to console or key-based auth.
- Minimal privilege principles observed for `deploy` user.
