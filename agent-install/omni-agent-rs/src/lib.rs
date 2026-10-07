pub mod buffer;
pub mod capabilities;
pub mod chat_display;
pub mod chat_ui;
pub mod consent_scripts;
pub mod consent_ui;
pub mod config;
pub mod heartbeat;
pub mod instructions;
pub mod registration;
pub mod tls;
pub mod tray;
pub mod uninstall;
pub mod user_session;

#[cfg(windows)]
pub mod service;

use buffer::MessageBuffer;
use capabilities::CapabilityManager;
use sysinfo::System;

/// How often an agent without a token asks the platform to enroll it again.
/// The register route allows 10 calls a minute per address.
const REGISTRATION_RETRY: std::time::Duration = std::time::Duration::from_secs(120);

pub async fn agent_loop(stop_rx: Option<tokio::sync::watch::Receiver<bool>>) {
    let mut cfg = match config::load() {
        Ok(c) => c,
        Err(e) => {
            log::error!("Failed to load config.yaml: {e}");
            return;
        }
    };

    if config::adopt_previous_identity(&mut cfg) {
        match config::save(&cfg) {
            Ok(()) => log::info!("Kept this machine's enrollment from the previous install"),
            Err(e) => log::warn!("Could not save the carried-over enrollment: {e}"),
        }
    }
    let interval = std::time::Duration::from_secs(cfg.interval_seconds);
    log::info!(
        "Omni Agent v2.0 starting — interval {}s, host {}",
        cfg.interval_seconds,
        heartbeat::hostname_str()
    );

    let exe_dir = std::env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(|d| d.to_path_buf()))
        .unwrap_or_default();
    let buf = MessageBuffer::new(exe_dir.join("buffer.db"));

    tls::init(&cfg);
    // Platform requests trust only the pinned certificate (when shipped); the
    // public-IP echo services are third parties and use the OS store.
    let client = tls::platform_client()
        .timeout(std::time::Duration::from_secs(30))
        .build()
        .expect("HTTP client build");
    let public_client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(30))
        .build()
        .expect("HTTP client build");

    let cap_mgr = CapabilityManager::new();

    // Write the tray launcher before any network call: the installer starts
    // the OmniAgentTray task once it sees tray_launch.vbs, and only waits a
    // short while. Registration (and the public-IP lookup) can take far longer
    // when the platform is slow or unreachable, which left no tray icon.
    #[cfg(windows)]
    {
        if let Err(e) = chat_ui::ensure_script_installed() {
            log::warn!("chat UI script install failed: {e}");
        }
        if let Err(e) = tray::ensure_script_installed() {
            log::warn!("tray script install failed: {e}");
        }
        if let Err(e) = config::write_tray_config(&cfg) {
            log::warn!("tray-config write failed: {e}");
        }
    }

    // Resolve the WAN/ISP public IP before registering so the first payload
    // carries it. Best-effort — registration proceeds regardless.
    heartbeat::refresh_public_ip(&public_client).await;
    registration::ensure_registered(&mut cfg, &client, &cap_mgr).await;
    if cfg.agent_token.is_empty() {
        log::warn!("No agent_token — heartbeats will be unauthenticated until registered");
    }
    log::info!("Capabilities loaded: {}", cap_mgr.ids().join(", "));

    // FIM setup
    crate::capabilities::fim_baseline::check_drift_on_start(&cfg.fim_paths, &crate::capabilities::fim_baseline::baseline_dir());

    // FIM watcher + drift check + background drain
    if let Some(ref stop_rx_clone) = stop_rx {
        let watcher_stop = stop_rx_clone.clone();
        if let Err(e) = crate::capabilities::fim::start_watcher(cfg.fim_paths.clone(), watcher_stop) {
            log::warn!("FIM watcher start failed: {e}");
        }

        let drain_stop = stop_rx_clone.clone();
        let cfg_drain = cfg.clone();
        let client_drain = client.clone();
        tokio::spawn(crate::capabilities::fim::drain_queue(cfg_drain, client_drain, drain_stop));
    }

    // Refresh the user-readable tray-config now that registration has (or has
    // not) produced a token. Non-fatal — telemetry continues regardless.
    #[cfg(windows)]
    {
        if let Err(e) = config::write_tray_config(&cfg) {
            log::warn!("tray-config write failed: {e}");
        }
    }

    let mut sys = System::new_all();
    let mut tick = 0u32;
    // Public IP rarely changes; re-resolve periodically rather than every beat.
    let mut last_public_ip_refresh = std::time::Instant::now();
    // Registration used to run once per service start: a host whose enrollment
    // was refused (e.g. 409 after a reinstall lost its secret) or that started
    // while the platform was down stayed tokenless until someone restarted the
    // service — no heartbeats, no instructions, and a tray that cannot raise
    // tickets or open chats. Keep trying while there is no token.
    let mut last_registration_attempt = std::time::Instant::now();

    loop {
        if let Some(ref rx) = stop_rx {
            if *rx.borrow() {
                log::info!("Stop signal received, shutting down.");
                break;
            }
        }

        if last_public_ip_refresh.elapsed() >= std::time::Duration::from_secs(1800) {
            heartbeat::refresh_public_ip(&public_client).await;
            last_public_ip_refresh = std::time::Instant::now();
        }

        if cfg.agent_token.is_empty() && last_registration_attempt.elapsed() >= REGISTRATION_RETRY {
            last_registration_attempt = std::time::Instant::now();
            if registration::ensure_registered(&mut cfg, &client, &cap_mgr).await {
                log::info!("Enrolled with the platform after retrying");
            }
            #[cfg(windows)]
            {
                if let Err(e) = config::write_tray_config(&cfg) {
                    log::warn!("tray-config write failed: {e}");
                }
            }
        }

        sys.refresh_all();
        let self_pid = sysinfo::Pid::from(std::process::id() as usize);
        if let Some(proc) = sys.process(self_pid) {
            let agent_cpu = proc.cpu_usage();
            if agent_cpu > cfg.max_cpu_percent {
                log::warn!(
                    "Agent CPU {agent_cpu:.1}% > limit {:.1}%, throttling 5s",
                    cfg.max_cpu_percent
                );
                tokio::time::sleep(std::time::Duration::from_secs(5)).await;
                continue;
            }
        }
        let payload = heartbeat::build_payload(&cfg, &sys, &cap_mgr);
        if let Some(body) = heartbeat::send(&cfg, payload, &buf, &client).await {
            uninstall::update_from_heartbeat(&mut cfg, &body);
        }
        instructions::poll(&cfg, &client).await;

        tick += 1;
        log::debug!("Tick {tick} complete");
        tokio::time::sleep(interval).await;
    }
}
