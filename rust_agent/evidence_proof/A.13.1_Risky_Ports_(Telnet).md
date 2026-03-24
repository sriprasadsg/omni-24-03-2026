# System Compliance Evidence
**Date:** 2026-02-05T19:57:54.600324
**Asset:** test-agent-host
**Control:** A.13.1
**Check Name:** Risky Ports (Telnet)

## 1. Check Status
**Result:** Pass
**Details:** Port 23 closed

## 2. Automated Command Output
```text

Active Connections

  Proto  Local Address          Foreign Address        State
  TCP    0.0.0.0:135            0.0.0.0:0              LISTENING
  TCP    0.0.0.0:445            0.0.0.0:0              LISTENING
  TCP    0.0.0.0:2179           0.0.0.0:0              LISTENING
  TCP    0.0.0.0:3000           0.0.0.0:0              LISTENING
  TCP    0.0.0.0:5000           0.0.0.0:0              LISTENING
  TCP    0.0.0.0:5040           0.0.0.0:0              LISTENING
  TCP    0.0.0.0:6
```

## 3. Evidence Integrity
*Integrity hash not provided by agent.*