use simplelog::{
    ColorChoice, CombinedLogger, Config as LogConfig, LevelFilter,
    TermLogger, TerminalMode, WriteLogger,
};
use std::fs::File;

fn init_logging() {
    let log_file = std::env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(|d| d.join("omni-agent.log")))
        .unwrap_or_else(|| "omni-agent.log".into());

    let _ = CombinedLogger::init(vec![
        TermLogger::new(
            LevelFilter::Info,
            LogConfig::default(),
            TerminalMode::Mixed,
            ColorChoice::Auto,
        ),
        WriteLogger::new(
            LevelFilter::Info,
            LogConfig::default(),
            File::options()
                .create(true)
                .append(true)
                .open(&log_file)
                .unwrap_or_else(|_| File::create("omni-agent.log").expect("log file")),
        ),
    ]);
}

#[tokio::main]
async fn main() {
    let args: Vec<String> = std::env::args().collect();

    // Desktop capture helper: the remote-access code re-launches this binary
    // with --desktop-capture inside the logged-on user's session. It must run
    // BEFORE init_logging — its stdout is the frame pipe the parent reads, and
    // a logger writing there would corrupt the stream. Never returns.
    if args.iter().any(|a| a == "--desktop-capture") {
        omni_agent::capabilities::screen_capture::run_capture_loop();
    }

    init_logging();

    // Uninstaller modes (uninstall protection) — answer and exit.
    if let Some(code) = omni_agent::uninstall::cli(&args).await {
        std::process::exit(code);
    }

    #[cfg(windows)]
    {
        if args.len() == 1 {
            match omni_agent::service::run() {
                Ok(()) => return,
                Err(windows_service::Error::Winapi(e))
                    if e.raw_os_error() == Some(1063) => {}
                Err(e) => log::warn!("Service dispatcher: {e}"),
            }
        }
    }

    log::info!("Standalone mode (args: {args:?})");
    omni_agent::agent_loop(None).await;
}
