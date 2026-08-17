use omni_agent::*;
use std::sync::{Arc, atomic::AtomicBool};
use ctrlc;
use tokio; // Add tokio for tokio::main macro

#[allow(dead_code)]
const SERVICE_NAME: &str = "OmniAgentRust";

// ── Windows Service wrapper (compiled only on Windows) ─────────────────────────

#[cfg(windows)]
mod win_svc {
    use super::SERVICE_NAME;
    use omni_agent::agent;
    use std::{ffi::OsString, sync::{Arc, OnceLock, atomic::{AtomicBool, Ordering}}, time::Duration};
    use windows_service::{
        define_windows_service, service_dispatcher,
        service::{ServiceControl, ServiceControlAccept, ServiceExitCode, ServiceState, ServiceStatus, ServiceType},
        service_control_handler::{self, ServiceControlHandlerResult},
    };

    static RUNNING: OnceLock<Arc<AtomicBool>> = OnceLock::new();

    define_windows_service!(ffi_service_main, svc_main);

    fn svc_main(_args: Vec<OsString>) {
        let running = Arc::new(AtomicBool::new(true));
        let _ = RUNNING.set(running.clone());

        let event_handler = move |control_event| -> ServiceControlHandlerResult {
            match control_event {
                ServiceControl::Stop => {
                    running.store(false, Ordering::SeqCst);
                    ServiceControlHandlerResult::NoError
                }
                _ => ServiceControlHandlerResult::NotImplemented,
            }
        };

        let status_handle = service_control_handler::register(SERVICE_NAME, event_handler).unwrap();
        status_handle.set_service_status(ServiceStatus {
            service_type: ServiceType::OWN_PROCESS,
            current_state: ServiceState::Running,
            controls_accepted: ServiceControlAccept::STOP,
            exit_code: ServiceExitCode::Win32(0),
            checkpoint: 0,
            wait_hint: Duration::default(),
            process_id: None,
        }).unwrap();

        // RUN THE AGENT in a tokio runtime for services
        let runtime = tokio::runtime::Builder::new_multi_thread()
            .enable_all()
            .build()
            .unwrap();

        runtime.block_on(async {
            agent::agent_loop(RUNNING.get().unwrap().clone()).await;
        });

        status_handle.set_service_status(ServiceStatus {
            service_type: ServiceType::OWN_PROCESS,
            current_state: ServiceState::Stopped,
            controls_accepted: ServiceControlAccept::empty(),
            exit_code: ServiceExitCode::Win32(0),
            checkpoint: 0,
            wait_hint: Duration::default(),
            process_id: None,
        }).unwrap();
    }

    pub fn start() {
        service_dispatcher::start(SERVICE_NAME, ffi_service_main).unwrap();
    }
}

#[tokio::main]
async fn main() {
    #[cfg(windows)]
    {
        // On Windows, if started with --console or in a TTY, run interactively.
        // Otherwise, assume it's the Service Control Manager.
        let interactive = std::env::args().any(|arg| arg == "--console") || atty::is(atty::Stream::Stdout);
        if interactive {
             let running = Arc::new(AtomicBool::new(true));
             let r = running.clone();
             ctrlc::set_handler(move || { r.store(false, std::sync::atomic::Ordering::SeqCst); }).expect("Error setting Ctrl-C handler");
             agent::agent_loop(running).await;
        } else {
             win_svc::start();
        }
    }

    #[cfg(not(windows))]
    {
        let running = Arc::new(AtomicBool::new(true));
        let r = running.clone();
        // Use a simple signal handler loop for Unix — no complex service wrapper needed.
        ctrlc::set_handler(move || {
            println!("Shutting down...");
            r.store(false, std::sync::atomic::Ordering::SeqCst);
        }).expect("Error setting Ctrl-C handler");

        agent::agent_loop(running).await;
    }
}