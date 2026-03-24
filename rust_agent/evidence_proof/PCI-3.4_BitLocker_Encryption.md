# System Compliance Evidence
**Date:** 2026-02-05T19:57:54.600324
**Asset:** test-agent-host
**Control:** PCI-3.4
**Check Name:** BitLocker Encryption

## 1. Check Status
**Result:** Warning
**Details:** Check requires Admin privileges

## 2. Automated Command Output
```text
Get-BitLockerVolume Output: 

manage-bde output:
BitLocker Drive Encryption: Configuration Tool version 10.0.26100
Copyright (C) 2013 Microsoft Corporation. All rights reserved.

ERROR: An attempt to access a required resource was denied.

Check that you have administrative rights on the computer.

Stderr: 
```

## 3. Evidence Integrity
*Integrity hash not provided by agent.*