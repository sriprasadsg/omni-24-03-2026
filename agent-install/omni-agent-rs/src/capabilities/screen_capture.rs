//! Native desktop frame capture for remote sessions.
//!
//! The agent used to screen-grab by spawning a hidden `powershell.exe
//! -EncodedCommand` that ran `Add-Type` + `System.Drawing.CopyFromScreen`. A
//! hidden, encoded PowerShell process taking screenshots is a textbook
//! potentially-unwanted-application behaviour, so Microsoft Defender quarantined
//! it on real endpoints (EILT0197, 2026-10-12) before a single frame was
//! produced — the stream died at line 1 every time. This captures the screen
//! with the Win32 GDI APIs inside the agent binary instead, which is how
//! production remote-desktop agents do it and carries no script for an AV to
//! scan.
//!
//! The stdout frame protocol is unchanged, so `remote_access`'s relay loop is
//! untouched: one base64 JPEG per line, `ERR:<message>` on a fatal error.

use std::io::Write;

/// JPEG quality for streamed frames (matches the prior PowerShell grabber).
#[cfg_attr(not(windows), allow(dead_code))]
const FRAME_QUALITY: u8 = 40;
/// Delay between frames (~6-7 fps), matching the prior grabber's cadence.
#[cfg_attr(not(windows), allow(dead_code))]
const FRAME_INTERVAL_MS: u64 = 150;

/// Encode a captured BGRA framebuffer as a base64 JPEG line (no trailing
/// newline). Pure and platform-independent, so it is unit-tested off Windows;
/// only the GDI capture that produces `bgra` is Windows-only. The base64 output
/// begins `/9j/` (the JPEG magic FF D8 FF), which is exactly what
/// `remote_access::classify_capture_line` recognises as a frame.
#[cfg_attr(not(windows), allow(dead_code))]
pub(crate) fn encode_frame(bgra: &[u8], width: u32, height: u32, quality: u8) -> Result<String, String> {
    if width == 0 || height == 0 {
        return Err("empty frame (0x0 screen)".into());
    }
    if width > u16::MAX as u32 || height > u16::MAX as u32 {
        return Err(format!("frame too large to encode: {width}x{height}"));
    }
    let expected = (width as usize) * (height as usize) * 4;
    if bgra.len() < expected {
        return Err(format!("short framebuffer: {} bytes for {width}x{height}", bgra.len()));
    }
    let mut jpeg = Vec::new();
    jpeg_encoder::Encoder::new(&mut jpeg, quality)
        .encode(&bgra[..expected], width as u16, height as u16, jpeg_encoder::ColorType::Bgra)
        .map_err(|e| format!("jpeg encode failed: {e}"))?;
    Ok(crate::user_session::base64(&jpeg))
}

/// Entry point for the `--desktop-capture` child process. Streams frames to
/// stdout until the parent closes the pipe (session ended), then exits 0; on a
/// fatal capture error it writes one `ERR:` line and exits 1. Never returns.
pub fn run_capture_loop() -> ! {
    let mut out = std::io::stdout();
    match capture_forever(&mut out) {
        Ok(()) => std::process::exit(0),
        Err(e) => {
            let _ = writeln!(out, "ERR:{e}");
            let _ = out.flush();
            std::process::exit(1);
        }
    }
}

/// Grab and emit frames until the output pipe breaks. Returns Ok when the
/// parent has gone away (an expected end), Err on a capture failure.
#[cfg(windows)]
fn capture_forever(out: &mut impl Write) -> Result<(), String> {
    unsafe { winapi::um::winuser::SetProcessDPIAware() };
    loop {
        let (bgra, w, h) = win::grab_primary_screen()?;
        let line = encode_frame(&bgra, w, h, FRAME_QUALITY)?;
        if out.write_all(line.as_bytes()).is_err()
            || out.write_all(b"\n").is_err()
            || out.flush().is_err()
        {
            // The parent closed the read end (session ended / was stopped).
            return Ok(());
        }
        std::thread::sleep(std::time::Duration::from_millis(FRAME_INTERVAL_MS));
    }
}

#[cfg(not(windows))]
fn capture_forever(_out: &mut impl Write) -> Result<(), String> {
    Err("desktop capture is only supported on Windows".into())
}

#[cfg(windows)]
mod win {
    use std::ptr;
    use winapi::shared::minwindef::DWORD;
    use winapi::um::errhandlingapi::GetLastError;
    use winapi::um::wingdi::{
        BitBlt, CreateCompatibleDC, CreateDIBSection, DeleteDC, DeleteObject, SelectObject,
        BITMAPINFO, BITMAPINFOHEADER, BI_RGB, CAPTUREBLT, DIB_RGB_COLORS, SRCCOPY,
    };
    use winapi::um::winuser::{GetDC, GetSystemMetrics, ReleaseDC, SM_CXSCREEN, SM_CYSCREEN};

    /// Capture the primary screen into a top-down 32-bit BGRA buffer.
    ///
    /// Matches the prior grabber's choice of the primary monitor (not the whole
    /// virtual desktop). Every GDI object created here is released on every
    /// path, including the error paths, so a failing or long-running session
    /// cannot leak device contexts or bitmaps.
    pub(super) fn grab_primary_screen() -> Result<(Vec<u8>, u32, u32), String> {
        unsafe {
            let width = GetSystemMetrics(SM_CXSCREEN);
            let height = GetSystemMetrics(SM_CYSCREEN);
            if width <= 0 || height <= 0 {
                return Err(
                    "No interactive desktop available (0x0 screen) - the agent has no active \
                     user session to capture (Session 0 isolation)"
                        .into(),
                );
            }

            let screen_dc = GetDC(ptr::null_mut());
            if screen_dc.is_null() {
                return Err(format!("GetDC(screen) failed ({})", GetLastError()));
            }
            let mem_dc = CreateCompatibleDC(screen_dc);
            if mem_dc.is_null() {
                ReleaseDC(ptr::null_mut(), screen_dc);
                return Err(format!("CreateCompatibleDC failed ({})", GetLastError()));
            }

            let mut info: BITMAPINFO = std::mem::zeroed();
            info.bmiHeader.biSize = std::mem::size_of::<BITMAPINFOHEADER>() as DWORD;
            info.bmiHeader.biWidth = width;
            info.bmiHeader.biHeight = -height; // negative: top-down, first row is the top of the screen
            info.bmiHeader.biPlanes = 1;
            info.bmiHeader.biBitCount = 32;
            info.bmiHeader.biCompression = BI_RGB;

            let mut bits: *mut winapi::ctypes::c_void = ptr::null_mut();
            let dib = CreateDIBSection(mem_dc, &info, DIB_RGB_COLORS, &mut bits, ptr::null_mut(), 0);
            if dib.is_null() || bits.is_null() {
                DeleteDC(mem_dc);
                ReleaseDC(ptr::null_mut(), screen_dc);
                return Err(format!("CreateDIBSection failed ({})", GetLastError()));
            }

            let prev = SelectObject(mem_dc, dib as _);
            // CAPTUREBLT also grabs layered windows (tooltips, some overlays).
            let ok = BitBlt(mem_dc, 0, 0, width, height, screen_dc, 0, 0, SRCCOPY | CAPTUREBLT);
            let result = if ok == 0 {
                Err(format!("BitBlt failed ({})", GetLastError()))
            } else {
                let len = (width as usize) * (height as usize) * 4;
                let mut buf = vec![0u8; len];
                ptr::copy_nonoverlapping(bits as *const u8, buf.as_mut_ptr(), len);
                Ok((buf, width as u32, height as u32))
            };

            SelectObject(mem_dc, prev);
            DeleteObject(dib as _);
            DeleteDC(mem_dc);
            ReleaseDC(ptr::null_mut(), screen_dc);
            result
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::capabilities::remote_access::line_is_frame;

    #[test]
    fn encoded_frame_is_recognised_as_a_frame_by_the_relay() {
        // 2x2 BGRA. The encoder output must start "/9j/" so the relay sends it
        // as a frame rather than treating it as stray output.
        let bgra = vec![0u8; 2 * 2 * 4];
        let line = encode_frame(&bgra, 2, 2, FRAME_QUALITY).unwrap();
        assert!(line.starts_with("/9j/"), "not a JPEG base64 line: {}", &line[..line.len().min(8)]);
        assert!(line_is_frame(&line));
    }

    #[test]
    fn encode_frame_rejects_a_zero_sized_or_short_buffer() {
        assert!(encode_frame(&[], 0, 0, FRAME_QUALITY).is_err());
        // 10x10 needs 400 bytes; give it 4.
        assert!(encode_frame(&[0u8; 4], 10, 10, FRAME_QUALITY).is_err());
    }
}

