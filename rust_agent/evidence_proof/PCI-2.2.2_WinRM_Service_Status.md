# System Compliance Evidence
**Date:** 2026-02-05T19:57:54.600324
**Asset:** test-agent-host
**Control:** PCI-2.2.2
**Check Name:** WinRM Service Status

## 1. Check Status
**Result:** Pass
**Details:** WinRM Service Stopped

## 2. Automated Command Output
```text

SERVICE_NAME: WinRM 
        TYPE               : 20  WIN32_SHARE_PROCESS  
        STATE              : 1  STOPPED 
        WIN32_EXIT_CODE    : 1077  (0x435)
        SERVICE_EXIT_CODE  : 0  (0x0)
        CHECKPOINT         : 0x0
        WAIT_HINT          : 0x0

```

## 3. Evidence Integrity
*Integrity hash not provided by agent.*