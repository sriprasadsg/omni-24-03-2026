# Phase 64: rotate_key autonomous-remediation action - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-08-11
**Phase:** 64-rotate-key-autonomous-remediation-action
**Areas discussed:** Rotation target — which key/credential, Allowlist mechanism, Reversibility / undo mechanism, New-value propagation

---

## Rotation target — which key/credential

**Q: Which credential should the rotate_key action actually rotate?**

| Option | Description | Selected |
|--------|-------------|----------|
| SSH authorized_keys entry | Generate new keypair, replace matching authorized_keys line, keep old line backed up. Purely local, no cloud API. | ✓ |
| Agent's own enrollment/auth token | Directly contradicts the review's "can lock out the host" concern. | |
| TLS/service certificate | More complex — needs a CA or self-signed reissue flow. | |
| Local service secret file (generic) | Too close to the vagueness the review already flagged. | |

**User's choice:** SSH authorized_keys entry

**Q: What finding should trigger the rotate_key playbook?**

| Option | Description | Selected |
|--------|-------------|----------|
| VULN: weak/compromised key detected | finding_class: vuln. Finding names the exact key. | ✓ |
| FIM: unauthorized authorized_keys change | Different semantics — "remove," not "regenerate." | |
| Both — same playbook, different match | More complexity, covers more of AUTO-02's intent. | |

**User's choice:** VULN: weak/compromised key detected

**Q: Phase 51's vuln scanner has zero detection for weak/compromised SSH keys — how should Phase 64 handle the gap?**

| Option | Description | Selected |
|--------|-------------|----------|
| Add the VULN check in this phase too | Extend Phase 51's scanner with a real check. Makes the feature actually autonomous end-to-end. | ✓ |
| Operator-triggered only, no new detection | Narrower scope, defers real autonomy. | |

**User's choice:** Add the VULN check in this phase too

**Notes:** Mid-discussion, checked `backend/secrets_service.py` (similarly-named `SecretType.SSH_KEY` + `rotate_secret()`) to rule out a collision — confirmed unrelated (tenant-facing secrets vault, explicitly refuses to auto-rotate SSH_KEY, no connection to the agent or monitored endpoints).

---

## Allowlist mechanism

**Q: How should the agent decide a given authorized_keys entry is safe to rotate?**

| Option | Description | Selected |
|--------|-------------|----------|
| Playbook step names the exact key fingerprint | VULN finding identifies the specific key; agent only touches that one line. Same precision as kill_process's by-pid targeting. | ✓ |
| Denylist of protected principals | CRITICAL_SSH_PRINCIPALS-style backstop mirroring existing CRITICAL_PROCESS_NAMES pattern. | |
| Both | Exact-fingerprint targeting AND a denylist backstop. | |

**User's choice:** Playbook step names the exact key fingerprint

**Q: What if the matched key is the ONLY authorized_keys entry on the host?**

| Option | Description | Selected |
|--------|-------------|----------|
| Refuse if it's the last/only entry | Agent counts entries before acting; returns {status: error} instead of rotating. | ✓ |
| No special-case, rely on approval gate + rollback | Trust the human approval + rollback path. | |

**User's choice:** Refuse if it's the last/only entry

---

## Reversibility / undo mechanism

**Q: What's the concrete rollback for rotate_key — reversible with a rollback step, or irreversible/escalate-only?**

| Option | Description | Selected |
|--------|-------------|----------|
| Restore the backed-up line | Agent backs up the old authorized_keys line before replacing; rollback writes it back. Mirrors restore_file's baseline/backup approach. | ✓ |
| Irreversible — escalate-only | No rollback step; verify-failure escalates to a human alert. | |

**User's choice:** Restore the backed-up line

**Q: What should "re-run the finding's own check" mean for rotate_key verify?**

| Option | Description | Selected |
|--------|-------------|----------|
| Re-scan authorized_keys, confirm old fingerprint gone + new key passes strength check | Grounded in actual post-action state. | ✓ |
| Trust the agent's structured result only | Simpler but weaker — doesn't meet Phase 53's own D-07 bar. | |

**User's choice:** Re-scan authorized_keys, confirm old fingerprint gone + new key passes strength check

---

## New-value propagation

**Q: After rotating, does anything else need to learn about the new value, or does v1 stop at replace-on-disk?**

| Option | Description | Selected |
|--------|-------------|----------|
| No propagation — replace on disk only | Nothing else in the platform needs the new key. New private key delivery is out-of-band, out of scope. | ✓ |
| Store new key metadata in the platform for operator retrieval | Adds a delivery/audit surface beyond the immutable remediation_audit record. | |

**User's choice:** No propagation — replace on disk only

**Note (not a real AskUserQuestion — stated as a hard constraint, not offered as a choice):** Whether the new private key material may ever appear in the `remediation_audit` record or agent result payload. There is no legitimate alternative — that would be a security bug, not a design option. Locked: private key stays host-local (locked-down file permissions), agent reports only the new key's fingerprint/comment back to the backend.

---

## Claude's Discretion

- Exact key algorithm for the newly generated keypair (ed25519 vs RSA-4096, etc.)
- Exact weak-key detection thresholds and compromised-key list format
- Whether the new VULN check is standalone or extends an existing SSH-related check in Phase 51's scanner

## Deferred Ideas

None — discussion stayed within phase scope.
