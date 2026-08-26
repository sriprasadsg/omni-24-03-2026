# Phase 74 — API Coverage Matrix

**Detector:** `api-coverage.cjs` returned `detected: true` on a single signal — the noun `api`
inside D-14's phrase "Windows Graphics Capture API", which is an explicitly-deferred stretch goal.

**No external network API, SDK, or third-party service is integrated by this phase.** No new
package is added to either ecosystem (see `74-RESEARCH.md` § Package Legitimacy Audit — the only
manifest change is adding the `winuser` feature flag to the already-vetted `winapi` 0.3 crate).

The API surface this phase *does* integrate is an **operating-system API**: `user32!SendInput` plus
the Windows Terminal Services / token APIs already used by `chat_ui.rs`. Because D-05 locks
"full, unrestricted keyboard and mouse passthrough", enumerating that surface is load-bearing —
a silently un-built input kind is exactly the invisible hole this checkpoint exists to prevent.
The matrix below is therefore the subtraction record for the OS API surface.

## `user32!SendInput` — input capability surface

| capability | decision | reason |
|---|---|---|
| `INPUT_MOUSE` / `MOUSEEVENTF_MOVE` (absolute, normalized) | INTEGRATE | |
| `INPUT_MOUSE` / `MOUSEEVENTF_LEFTDOWN` + `LEFTUP` | INTEGRATE | |
| `INPUT_MOUSE` / `MOUSEEVENTF_RIGHTDOWN` + `RIGHTUP` | INTEGRATE | |
| `INPUT_MOUSE` / `MOUSEEVENTF_MIDDLEDOWN` + `MIDDLEUP` | INTEGRATE | |
| `INPUT_MOUSE` / `MOUSEEVENTF_WHEEL` (vertical) | INTEGRATE | |
| `INPUT_MOUSE` / `MOUSEEVENTF_HWHEEL` (horizontal) | INTEGRATE | Browser `WheelEvent.deltaX` exists; no reason to drop it once the wheel path is built |
| `INPUT_MOUSE` / `MOUSEEVENTF_XDOWN` + `XUP` (browser back/forward buttons 3-4) | INTEGRATE | `MouseEvent.button` 3/4 are capturable; D-05 says unrestricted |
| `INPUT_KEYBOARD` / key down (`wVk` virtual-key) | INTEGRATE | |
| `INPUT_KEYBOARD` / key up (`KEYEVENTF_KEYUP`) | INTEGRATE | |
| `INPUT_KEYBOARD` / `KEYEVENTF_EXTENDEDKEY` (arrows, Ins/Del/Home/End/PgUp/PgDn, right-Alt/Ctrl, numpad Enter) | INTEGRATE | Omitting the extended-key flag silently breaks arrow keys and Del — a classic half-integration |
| `INPUT_KEYBOARD` / `KEYEVENTF_UNICODE` (`wScan` as UTF-16 code unit) | INTEGRATE | Required for non-US keyboard layouts; VK-only injection types the wrong character on any layout the agent host does not share with the admin |
| `INPUT_HARDWARE` | OPT-OUT | Documented by Microsoft as not supported for synthesized input via `SendInput`; there is no remote-desktop use for it |
| Secure Attention Sequence (Ctrl+Alt+Del) | OPT-OUT | Blocked by Windows itself — `SendInput` cannot inject the SAS. D-05 explicitly acknowledges this and forbids building a blocklist for it |
| Clipboard transfer (`OpenClipboard`/`SetClipboardData`) | OPT-OUT | Deferred by D-07 to a follow-up phase — data-exfiltration threat model not yet done |
| Local-input suppression (`BlockInput`, low-level hooks) | OPT-OUT | Forbidden by D-08 — the local physical user keeps working during a control session |

## Windows session / token API surface (consent + stop-control UI)

| capability | decision | reason |
|---|---|---|
| `WTSGetActiveConsoleSessionId` | INTEGRATE | |
| `WTSQueryUserToken` | INTEGRATE | |
| `DuplicateTokenEx` → `CreateProcessAsUserW` (`winsta0\default`) | INTEGRATE | |
| `CreateEnvironmentBlock` / `DestroyEnvironmentBlock` | INTEGRATE | |
| `WTSSendMessage` / `msg.exe` | OPT-OUT | One-way text only — cannot capture Accept/Decline, so it cannot satisfy D-01/D-03. `chat_display.rs`'s own doc comment confirms this |
| `WTSEnumerateSessions` (multi-session / RDP-and-console simultaneously) | OPT-OUT | `heartbeat.rs` already scopes the agent to the single active console session; multi-session is out of scope repo-wide, not just this phase |

## Screen capture surface

| capability | decision | reason |
|---|---|---|
| PowerShell `CopyFromScreen` periodic capture (existing) | INTEGRATE | Unchanged from today — this phase adds input, not capture |
| Windows Graphics Capture API / DXGI Desktop Duplication | OPT-OUT | Deferred by D-14 as an explicit stretch goal, not required for phase completion |
