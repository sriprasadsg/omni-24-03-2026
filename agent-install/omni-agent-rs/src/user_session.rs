//! Run a helper process inside the logged-on user's session and read its output.
//!
//! The agent is a Windows service in session 0, which cannot see the user's
//! desktop: a screen grab started there captures nothing, so the desktop stream
//! died right after the user granted consent. The consent prompt and the chat
//! window already launch into the active console session (consent_ui, chat_ui);
//! this does the same for a helper whose stdout the agent needs, through a pipe.
//!
//! The child inherits exactly one handle — the pipe's write end — via an
//! explicit handle list, so no other service handle leaks into a process that
//! runs as the (less privileged) user.

/// `powershell.exe -EncodedCommand` takes the script as base64 UTF-16LE, which
/// avoids quoting a multi-line script on a CreateProcess command line.
pub fn powershell_encoded(script: &str) -> String {
    let bytes: Vec<u8> = script.encode_utf16().flat_map(|u| u.to_le_bytes()).collect();
    format!(
        "powershell.exe -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -EncodedCommand {}",
        base64(&bytes)
    )
}

fn base64(data: &[u8]) -> String {
    const ALPHABET: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut out = String::with_capacity((data.len() + 2) / 3 * 4);
    for chunk in data.chunks(3) {
        let b = [chunk[0], *chunk.get(1).unwrap_or(&0), *chunk.get(2).unwrap_or(&0)];
        let n = (u32::from(b[0]) << 16) | (u32::from(b[1]) << 8) | u32::from(b[2]);
        for i in 0..4 {
            if i <= chunk.len() {
                out.push(ALPHABET[(n >> (18 - 6 * i) & 63) as usize] as char);
            } else {
                out.push('=');
            }
        }
    }
    out
}

#[cfg(windows)]
pub use win::{spawn_piped, UserProcess};

#[cfg(windows)]
mod win {
    use std::os::windows::ffi::OsStrExt;
    use std::os::windows::io::FromRawHandle;
    use winapi::shared::basetsd::SIZE_T;
    use winapi::shared::minwindef::{DWORD, FALSE, LPVOID, TRUE};
    use winapi::um::errhandlingapi::GetLastError;
    use winapi::um::handleapi::{CloseHandle, SetHandleInformation};
    use winapi::um::minwinbase::SECURITY_ATTRIBUTES;
    use winapi::um::namedpipeapi::CreatePipe;
    use winapi::um::processthreadsapi::{
        CreateProcessAsUserW, DeleteProcThreadAttributeList, InitializeProcThreadAttributeList,
        TerminateProcess, UpdateProcThreadAttribute, PROCESS_INFORMATION, PROC_THREAD_ATTRIBUTE_LIST,
    };
    use winapi::um::securitybaseapi::DuplicateTokenEx;
    use winapi::um::userenv::{CreateEnvironmentBlock, DestroyEnvironmentBlock};
    use winapi::um::winbase::{
        WTSGetActiveConsoleSessionId, CREATE_NO_WINDOW, CREATE_UNICODE_ENVIRONMENT,
        EXTENDED_STARTUPINFO_PRESENT, HANDLE_FLAG_INHERIT, STARTF_USESTDHANDLES, STARTUPINFOEXW,
    };
    use winapi::um::winnt::{SecurityImpersonation, TokenPrimary, HANDLE, MAXIMUM_ALLOWED};
    use winapi::um::wtsapi32::WTSQueryUserToken;

    /// Not exported by winapi 0.3: ProcThreadAttributeHandleList (2) | PROC_THREAD_ATTRIBUTE_INPUT.
    const PROC_THREAD_ATTRIBUTE_HANDLE_LIST: usize = 0x0002_0002;

    /// A helper running in the user's session. Dropping it ends the process.
    pub struct UserProcess {
        process: HANDLE,
        pub stdout: Option<std::fs::File>,
    }

    // The process handle is only used for TerminateProcess/CloseHandle, which
    // are safe from any thread.
    unsafe impl Send for UserProcess {}

    impl UserProcess {
        pub fn kill(&self) {
            unsafe { TerminateProcess(self.process, 1) };
        }
    }

    impl Drop for UserProcess {
        fn drop(&mut self) {
            unsafe {
                TerminateProcess(self.process, 1);
                CloseHandle(self.process);
            }
        }
    }

    fn wide(s: &str) -> Vec<u16> {
        std::ffi::OsStr::new(s).encode_wide().chain(std::iter::once(0)).collect()
    }

    /// Start `cmdline` as the active console user on winsta0\default with its
    /// stdout and stderr connected to a pipe the caller reads.
    pub fn spawn_piped(cmdline: &str) -> Result<UserProcess, String> {
        unsafe {
            let session = WTSGetActiveConsoleSessionId();
            if session == 0xFFFF_FFFF {
                return Err("no active console session (no user logged on)".to_string());
            }
            let mut user_token: HANDLE = std::ptr::null_mut();
            if WTSQueryUserToken(session, &mut user_token) == 0 {
                return Err(format!("WTSQueryUserToken failed ({})", GetLastError()));
            }
            let mut primary: HANDLE = std::ptr::null_mut();
            let dup = DuplicateTokenEx(
                user_token, MAXIMUM_ALLOWED, std::ptr::null_mut(), SecurityImpersonation, TokenPrimary, &mut primary,
            );
            CloseHandle(user_token);
            if dup == 0 {
                return Err(format!("DuplicateTokenEx failed ({})", GetLastError()));
            }

            // Pipe: the write end is handed to the child, the read end stays here.
            let mut sa: SECURITY_ATTRIBUTES = std::mem::zeroed();
            sa.nLength = std::mem::size_of::<SECURITY_ATTRIBUTES>() as DWORD;
            sa.bInheritHandle = TRUE;
            let (mut read, mut write): (HANDLE, HANDLE) = (std::ptr::null_mut(), std::ptr::null_mut());
            if CreatePipe(&mut read, &mut write, &mut sa, 0) == 0 {
                let err = GetLastError();
                CloseHandle(primary);
                return Err(format!("CreatePipe failed ({err})"));
            }
            SetHandleInformation(read, HANDLE_FLAG_INHERIT, 0);

            // Inherit only the write end.
            let mut list_size: SIZE_T = 0;
            InitializeProcThreadAttributeList(std::ptr::null_mut(), 1, 0, &mut list_size);
            let mut list_buf = vec![0u8; list_size];
            let list = list_buf.as_mut_ptr() as *mut PROC_THREAD_ATTRIBUTE_LIST;
            let mut inherit = [write];
            let list_ok = InitializeProcThreadAttributeList(list, 1, 0, &mut list_size) != 0
                && UpdateProcThreadAttribute(
                    list, 0, PROC_THREAD_ATTRIBUTE_HANDLE_LIST,
                    inherit.as_mut_ptr() as LPVOID, std::mem::size_of::<HANDLE>(),
                    std::ptr::null_mut(), std::ptr::null_mut(),
                ) != 0;
            if !list_ok {
                let err = GetLastError();
                CloseHandle(read);
                CloseHandle(write);
                CloseHandle(primary);
                return Err(format!("handle list setup failed ({err})"));
            }

            let mut env: LPVOID = std::ptr::null_mut();
            let have_env = CreateEnvironmentBlock(&mut env, primary, FALSE) != 0;

            let mut si: STARTUPINFOEXW = std::mem::zeroed();
            si.StartupInfo.cb = std::mem::size_of::<STARTUPINFOEXW>() as DWORD;
            let mut desktop = wide(r"winsta0\default");
            si.StartupInfo.lpDesktop = desktop.as_mut_ptr();
            si.StartupInfo.dwFlags = STARTF_USESTDHANDLES;
            si.StartupInfo.hStdInput = std::ptr::null_mut();
            si.StartupInfo.hStdOutput = write;
            si.StartupInfo.hStdError = write;
            si.lpAttributeList = list;

            let mut pi: PROCESS_INFORMATION = std::mem::zeroed();
            let mut cmd = wide(cmdline);
            let ok = CreateProcessAsUserW(
                primary,
                std::ptr::null(),
                cmd.as_mut_ptr(),
                std::ptr::null_mut(),
                std::ptr::null_mut(),
                TRUE,
                CREATE_UNICODE_ENVIRONMENT | CREATE_NO_WINDOW | EXTENDED_STARTUPINFO_PRESENT,
                if have_env { env } else { std::ptr::null_mut() },
                std::ptr::null(),
                &mut si.StartupInfo,
                &mut pi,
            );
            let err = GetLastError();

            DeleteProcThreadAttributeList(list);
            if have_env {
                DestroyEnvironmentBlock(env);
            }
            CloseHandle(primary);
            // The child holds its own copy; ours must go so EOF arrives when it exits.
            CloseHandle(write);

            if ok == 0 {
                CloseHandle(read);
                return Err(format!("CreateProcessAsUserW failed ({err})"));
            }
            CloseHandle(pi.hThread);
            Ok(UserProcess {
                process: pi.hProcess,
                stdout: Some(std::fs::File::from_raw_handle(read as _)),
            })
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn base64_matches_rfc4648_vectors() {
        for (input, expected) in [("", ""), ("f", "Zg=="), ("fo", "Zm8="), ("foo", "Zm9v"), ("foob", "Zm9vYg=="), ("fooba", "Zm9vYmE="), ("foobar", "Zm9vYmFy")] {
            assert_eq!(base64(input.as_bytes()), expected);
        }
    }

    #[test]
    fn encoded_command_is_utf16le_base64() {
        // "dir" as UTF-16LE is 64 00 69 00 72 00.
        assert!(powershell_encoded("dir").ends_with(" -EncodedCommand ZABpAHIA"));
    }
}
