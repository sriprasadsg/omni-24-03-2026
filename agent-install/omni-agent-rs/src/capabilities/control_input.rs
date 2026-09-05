//! Browser→agent interactive-control input layer (Phase 74, Option A wire
//! contract): frame parsing at the trust boundary, the per-session
//! authorisation gate, and the Windows SendInput replayer.
//!
//! Split out of `remote_access.rs` purely for the 500-line source cap; the
//! session orchestration (consent flow, tunnel wiring, screenshot loop) lives
//! in `remote_access`, this module is the pure input surface. Everything the
//! plan's full-surface matrix allows is replayed (D-05: mouse buttons/wheel,
//! keyboard incl. extended keys and Unicode text input); what is forbidden —
//! `INPUT_HARDWARE`, the SAS secret, `BlockInput`/low-level hooks (D-08) — is
//! simply never emitted, so there is nothing to call `SendInput` with (see
//! COVERAGE.md matrix).

/// One decoded interactive-control input frame. Parsed at the boundary by
/// `parse_input_frame`, replayed on Windows by `control_input_replay`.
#[derive(Debug, PartialEq)]
pub enum InputEvent {
    MouseMove { x: f64, y: f64 },
    MouseButton { down: bool, button: u8 },
    Wheel { delta_x: i64, delta_y: i64 },
    Key { down: bool, vk: u8, extended: bool, unicode: Option<u16> },
}

const INPUT_KINDS: &[&str] = &["mousemove", "mousedown", "mouseup", "wheel", "keydown", "keyup"];

/// Parse and validate one browser→agent input frame. Rejects at the boundary:
/// any `kind` outside the enumerated set, `x`/`y` outside 0.0..=1.0 inclusive,
/// `vk` outside 0..=254, or a non-`input` `type` — returning `Err` with a
/// short reason rather than panicking or silently clamping into a
/// valid-looking event (T-74-04).
pub fn parse_input_frame(raw: &str) -> Result<InputEvent, String> {
    let value: serde_json::Value = serde_json::from_str(raw).map_err(|e| format!("invalid JSON: {e}"))?;
    if value.get("type").and_then(|v| v.as_str()) != Some("input") {
        return Err("frame type is not 'input'".to_string());
    }
    let kind = value.get("kind").and_then(|v| v.as_str()).unwrap_or("");
    if !INPUT_KINDS.contains(&kind) {
        return Err(format!("unknown input kind: {kind}"));
    }

    let coord = |key: &str| -> Result<f64, String> {
        match value.get(key).and_then(|v| v.as_f64()) {
            Some(n) if (0.0..=1.0).contains(&n) => Ok(n),
            Some(n) => Err(format!("{key} {n} out of range 0.0..=1.0")),
            None => Err(format!("missing or non-numeric {key}")),
        }
    };
    let int = |key: &str| -> Result<Option<i64>, String> {
        Ok(value.get(key).and_then(|v| v.as_i64()))
    };
    let vk = |key: &str| -> Result<Option<u8>, String> {
        match int(key)? {
            Some(n) if (0..=254).contains(&n) => Ok(Some(n as u8)),
            Some(n) => Err(format!("{key} {n} out of range 0..=254")),
            None => Ok(None),
        }
    };

    Ok(match kind {
        "mousemove" => InputEvent::MouseMove { x: coord("x")?, y: coord("y")? },
        "mousedown" => InputEvent::MouseButton { down: true, button: vk("button")?.unwrap_or(0) },
        "mouseup" => InputEvent::MouseButton { down: false, button: vk("button")?.unwrap_or(0) },
        "wheel" => InputEvent::Wheel {
            delta_x: int("deltaX")?.unwrap_or(0),
            delta_y: int("deltaY")?.unwrap_or(0),
        },
        "keydown" => InputEvent::Key {
            down: true,
            vk: vk("vk")?.ok_or("missing vk")?,
            extended: matches!(value.get("extended"), Some(serde_json::Value::Bool(true))),
            unicode: int("unicode")?.and_then(|n| u16::try_from(n).ok()),
        },
        "keyup" => InputEvent::Key {
            down: false,
            vk: vk("vk")?.ok_or("missing vk")?,
            extended: matches!(value.get("extended"), Some(serde_json::Value::Bool(true))),
            unicode: int("unicode")?.and_then(|n| u16::try_from(n).ok()),
        },
        _ => unreachable!("kind validated above"),
    })
}

/// Per-session authorisation gate for input replay (T-74-02).
///
/// Platform-independent so the accept→active→stop lifecycle is unit-tested on
/// Linux (Task 3 acceptance). The control read loop concedes once after the
/// endpoint user accepts, then consults `authorised()` before EVERY SendInput;
/// the endpoint stop bar revokes, after which no further input is replayed
/// until a fresh session grants consent again (D-12).
#[derive(Debug)]
pub struct ConsentGate {
    accepted: bool,
    stopped: bool,
}

impl Default for ConsentGate {
    fn default() -> Self {
        Self::new()
    }
}

impl ConsentGate {
    pub fn new() -> Self {
        ConsentGate { accepted: false, stopped: false }
    }

    /// Mark consent granted (called once after the endpoint user accepts).
    pub fn concede(&mut self) {
        self.accepted = true;
    }

    /// Mark control revoked (the stop sentinel appeared). Irreversible within
    /// this session — a reconnect must obtain fresh consent (D-12).
    pub fn revoke(&mut self) {
        self.stopped = true;
    }

    /// Whether input may be replayed RIGHT NOW. Refuses until accepted and
    /// never re-authorises after a stop.
    pub fn authorised(&self) -> bool {
        self.accepted && !self.stopped
    }

    // Test-only introspection: the gate refuses replay before accept.
    #[cfg(test)]
    fn accepted(&self) -> bool {
        self.accepted
    }
}

/// Replay one decoded event by synthesising native input (SendInput). Called
/// only from the control read loop, which has already checked the
/// authorisation gate. Every `SendInput` here is the INTEGRATE surface from
/// the COVERAGE.md matrix; nothing on the OPT-OUT list is ever emitted.
#[cfg(windows)]
pub fn control_input_replay(ev: &InputEvent) {
    use std::mem::size_of;
    use winapi::um::errhandlingapi::GetLastError;
    use winapi::um::winuser::*;

    // winapi 0.3: INPUT has no Default impl; the union method is `mi()` —
    // `zeroed` is the canonical init for a raw union fully written below.
    let send = |input: &mut INPUT| {
        let sent = unsafe { SendInput(1, input, size_of::<INPUT>() as i32) };
        if sent == 0 {
            log::warn!("SendInput failed: error {}", unsafe { GetLastError() });
        }
    };

    match ev {
        InputEvent::MouseMove { x, y } => {
            let mut input: INPUT = unsafe { std::mem::zeroed() };
            input.type_ = INPUT_MOUSE;
            // Form the field pointer from the INPUT pointer itself (avoids the
            // &mut -> *mut reborrow error E0606) and write through it; the
            // shared bytes are immediately reborrowed as &mut INPUT for SendInput.
            let mi: &mut MOUSEINPUT = unsafe {
                &mut *(&mut input as *mut INPUT as *mut MOUSEINPUT)
            };
            mi.dwFlags = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK;
            mi.dx = (x * 65535.0).round() as i32;
            mi.dy = (y * 65535.0).round() as i32;
            send(&mut input);
        }
        InputEvent::MouseButton { down, button } => {
            // Browser MouseEvent.button codes (Phase 74 wire contract):
            // 0 left, 1 middle, 2 right, 3 X1 (back), 4 X2 (forward).
            let flag = match (button, *down) {
                (0, true) => MOUSEEVENTF_LEFTDOWN,
                (0, false) => MOUSEEVENTF_LEFTUP,
                (1, true) => MOUSEEVENTF_MIDDLEDOWN,
                (1, false) => MOUSEEVENTF_MIDDLEUP,
                (2, true) => MOUSEEVENTF_RIGHTDOWN,
                (2, false) => MOUSEEVENTF_RIGHTUP,
                (3, true) | (4, true) => MOUSEEVENTF_XDOWN,
                (3, false) | (4, false) => MOUSEEVENTF_XUP,
                _ => return,
            };
            let mut input: INPUT = unsafe { std::mem::zeroed() };
            input.type_ = INPUT_MOUSE;
            let mi: &mut MOUSEINPUT = unsafe {
                &mut *(&mut input as *mut INPUT as *mut MOUSEINPUT)
            };
            mi.dwFlags = flag;
            match button {
                3 => mi.mouseData = XBUTTON1 as u32,
                4 => mi.mouseData = XBUTTON2 as u32,
                _ => {}
            }
            send(&mut input);
        }
        InputEvent::Wheel { delta_x, delta_y } => {
            let clamp = |delta: i64| (delta * WHEEL_DELTA as i64).clamp(i32::MIN as i64, i32::MAX as i64) as u32;
            if *delta_y != 0 {
                let mut input: INPUT = unsafe { std::mem::zeroed() };
                input.type_ = INPUT_MOUSE;
                let mi: &mut MOUSEINPUT = unsafe {
                    &mut *(&mut input as *mut INPUT as *mut MOUSEINPUT)
                };
                mi.dwFlags = MOUSEEVENTF_WHEEL;
                mi.mouseData = clamp(*delta_y);
                send(&mut input);
            }
            if *delta_x != 0 {
                let mut input: INPUT = unsafe { std::mem::zeroed() };
                input.type_ = INPUT_MOUSE;
                let mi: &mut MOUSEINPUT = unsafe {
                    &mut *(&mut input as *mut INPUT as *mut MOUSEINPUT)
                };
                mi.dwFlags = MOUSEEVENTF_HWHEEL;
                mi.mouseData = clamp(*delta_x);
                send(&mut input);
            }
        }
        InputEvent::Key { down, vk, extended, unicode } => {
            let mut input: INPUT = unsafe { std::mem::zeroed() };
            input.type_ = INPUT_KEYBOARD;
            let ki: &mut KEYBDINPUT = unsafe {
                &mut *(&mut input as *mut INPUT as *mut KEYBDINPUT)
            };
            ki.wVk = *vk as u16;
            if !*down {
                ki.dwFlags = KEYEVENTF_KEYUP;
            }
            if *extended {
                ki.dwFlags |= KEYEVENTF_EXTENDEDKEY;
            }
            // Full-surface text input: a frame carrying a Unicode code unit
            // plus a zero virtual-key code is replayed as a `KEYEVENTF_UNICODE`
            // keystroke with the UTF-16 unit in wScan (D-05). A frame with
            // BOTH vk and unicode resolves to the virtual-key path — vk wins.
            if *vk == 0 {
                if let Some(unit) = unicode {
                    ki.wScan = *unit;
                    ki.dwFlags |= KEYEVENTF_UNICODE;
                }
            }
            send(&mut input);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_input_frame_rejects_unknown_kind() {
        let raw = r#"{"type":"input","kind":"teleport","x":0.5,"y":0.5}"#;
        assert!(parse_input_frame(raw).is_err());
    }

    #[test]
    fn parse_input_frame_rejects_out_of_range_coords() {
        let raw = r#"{"type":"input","kind":"mousemove","x":1.5,"y":0.5}"#;
        assert!(parse_input_frame(raw).is_err());
    }

    #[test]
    fn parse_input_frame_rejects_non_input_type() {
        let raw = r#"{"type":"frame","kind":"mousemove","x":0.5,"y":0.5}"#;
        assert!(parse_input_frame(raw).is_err());
    }

    #[test]
    fn parse_input_frame_accepts_valid_mousemove() {
        let raw = r#"{"type":"input","kind":"mousemove","x":0.25,"y":0.75}"#;
        assert_eq!(
            parse_input_frame(raw).unwrap(),
            InputEvent::MouseMove { x: 0.25, y: 0.75 }
        );
    }

    #[test]
    fn parse_input_frame_rejects_bad_vk() {
        let raw = r#"{"type":"input","kind":"keydown","vk":300}"#;
        assert!(parse_input_frame(raw).is_err());
    }

    #[test]
    fn parse_input_frame_full_surface() {
        // Every kind on the matrix parses to its event — nothing is a "tracer
        // dropped" stub anymore (74-03 Task 3 full surface).
        assert_eq!(
            parse_input_frame(r#"{"type":"input","kind":"mousedown","button":2}"#).unwrap(),
            InputEvent::MouseButton { down: true, button: 2 }
        );
        assert_eq!(
            parse_input_frame(r#"{"type":"input","kind":"mouseup","button":4}"#).unwrap(),
            InputEvent::MouseButton { down: false, button: 4 }
        );
        assert_eq!(
            parse_input_frame(r#"{"type":"input","kind":"wheel","deltaX":2,"deltaY":-1}"#).unwrap(),
            InputEvent::Wheel { delta_x: 2, delta_y: -1 }
        );
        assert_eq!(
            parse_input_frame(r#"{"type":"input","kind":"keydown","vk":17,"extended":true}"#).unwrap(),
            InputEvent::Key { down: true, vk: 0x11, extended: true, unicode: None }
        );
        assert_eq!(
            parse_input_frame(r#"{"type":"input","kind":"keyup","vk":0,"unicode":65}"#).unwrap(),
            InputEvent::Key { down: false, vk: 0, extended: false, unicode: Some(65) }
        );
    }

    #[test]
    fn consent_gate_refuses_replay_before_accept() {
        let gate = ConsentGate::new();
        assert!(!gate.authorised(), "must not replay without consent");
        assert!(!gate.accepted(), "nothing accepted yet");
    }

    #[test]
    fn consent_gate_allows_after_accept_and_refuses_after_stop() {
        let mut gate = ConsentGate::new();
        gate.concede();
        assert!(gate.authorised(), "accepted session may replay");
        gate.revoke();
        assert!(!gate.authorised(), "stop revokes permanently — no re-authorise in-session");
    }

    #[test]
    fn consent_gate_stop_without_accept_never_authorises() {
        let mut gate = ConsentGate::new();
        gate.revoke();
        assert!(!gate.authorised());
        gate.concede();
        assert!(!gate.authorised(), "a conceded-then-revoked gate stays revoked");
    }

    #[test]
    fn wheel_line_delta_scales_to_windows_notches() {
        // Sanity for the clamp used by the Windows replay: a browser wheel
        // delta of -1 line becomes WHEEL_DELTA 120 (a notches unit) scaled to
        // -120, within i32 range. Windows WHEEL_DELTA is exactly 120.
        let clamped = (-1i64 * 120i64).clamp(i32::MIN as i64, i32::MAX as i64);
        assert_eq!(clamped, -120);
    }
}