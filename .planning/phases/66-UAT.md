# Phase 66 - User Acceptance Testing (UAT)
## Full YARA-rule engine for native scan

### Test 1: Malicious file detection
- **Description:** Verify `run_yara_scan` detects a file containing the specified malicious string.
- **Status:** PASSED
- **Expected Result:** `status: "detected"`, `matches: ["evil_file"]`
- **Actual Result:** `{"status":"detected","file":"/tmp/test_malicious.txt","matches":["evil_file"]}`

### Test 2: Clean file detection
- **Description:** Verify `run_yara_scan` reports a clean file correctly.
- **Status:** PASSED
- **Expected Result:** `status: "clean"`, `matches: []`
- **Actual Result:** `{"status":"clean","file":"/tmp/test_clean.txt","matches":[]}`

