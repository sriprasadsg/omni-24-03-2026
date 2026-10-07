//! TLS trust for connections to the platform.
//!
//! Installers put the platform's certificate in config.yaml (`server_ca_cert`,
//! PEM). When it is set, every connection to the platform trusts that
//! certificate and nothing else — not the OS store — so someone on the network
//! can't pose as the server, even with a publicly trusted certificate. Calls to
//! third-party hosts (the public-IP lookup) keep the OS store.
//!
//! Without a pinned certificate the legacy `accept_invalid_certs` flag still
//! applies, so agents installed before pinning keep working until reinstalled.

use std::sync::OnceLock;

#[derive(Clone, Default)]
struct Trust {
    pinned_pem: Option<String>,
    accept_invalid: bool,
}

static TRUST: OnceLock<Trust> = OnceLock::new();

/// Record the platform trust settings. Called once at startup, after config
/// load; later calls are ignored.
pub fn init(cfg: &crate::config::Config) {
    let pinned_pem = cfg
        .server_ca_cert
        .as_deref()
        .map(str::trim)
        .filter(|pem| !pem.is_empty())
        .map(str::to_string);
    if pinned_pem.is_some() {
        log::info!("TLS: platform connections trust only the pinned server certificate");
    } else if cfg.accept_invalid_certs {
        log::warn!("TLS: certificate checks are OFF for the platform (accept_invalid_certs); reinstall to pin");
    }
    let _ = TRUST.set(Trust { pinned_pem, accept_invalid: cfg.accept_invalid_certs });
}

fn trust() -> Trust {
    TRUST.get().cloned().unwrap_or_default()
}

/// The pinned certificate as DER, base64-encoded: what the PowerShell tray and
/// chat windows compare the server's certificate against.
pub fn pinned_der_base64() -> Option<String> {
    let pem = trust().pinned_pem?;
    let body: String = pem
        .lines()
        .filter(|l| !l.starts_with("-----"))
        .map(str::trim)
        .collect();
    (!body.is_empty()).then_some(body)
}

fn pinned_reqwest_cert(pem: &str) -> Vec<reqwest::Certificate> {
    match reqwest::Certificate::from_pem(pem.as_bytes()) {
        Ok(cert) => vec![cert],
        Err(e) => {
            // Fail closed: with tls_certs_only and no roots, nothing verifies.
            log::error!("TLS: server_ca_cert is not a valid PEM certificate ({e}); platform connections will fail");
            Vec::new()
        }
    }
}

/// Async HTTP client builder for platform requests.
pub fn platform_client() -> reqwest::ClientBuilder {
    client_for(&trust())
}

fn client_for(t: &Trust) -> reqwest::ClientBuilder {
    let builder = reqwest::Client::builder();
    match &t.pinned_pem {
        Some(pem) => builder.tls_certs_only(pinned_reqwest_cert(pem)),
        None => builder.danger_accept_invalid_certs(t.accept_invalid),
    }
}

/// Blocking HTTP client builder for platform requests.
pub fn platform_blocking_client() -> reqwest::blocking::ClientBuilder {
    let t = trust();
    let builder = reqwest::blocking::Client::builder();
    match t.pinned_pem {
        Some(pem) => builder.tls_certs_only(pinned_reqwest_cert(&pem)),
        None => builder.danger_accept_invalid_certs(t.accept_invalid),
    }
}

/// TLS connector for platform WebSockets (remote shell / desktop tunnels).
/// None means tokio-tungstenite's default (OS store), used when nothing is
/// pinned and certificates are checked.
pub fn platform_ws_connector() -> Result<Option<tokio_tungstenite::Connector>, native_tls::Error> {
    ws_connector_for(&trust())
}

fn ws_connector_for(t: &Trust) -> Result<Option<tokio_tungstenite::Connector>, native_tls::Error> {
    let mut builder = native_tls::TlsConnector::builder();
    match &t.pinned_pem {
        Some(pem) => {
            builder.disable_built_in_roots(true);
            match native_tls::Certificate::from_pem(pem.as_bytes()) {
                Ok(cert) => {
                    builder.add_root_certificate(cert);
                }
                Err(e) => log::error!("TLS: server_ca_cert is not a valid PEM certificate ({e})"),
            }
        }
        None if t.accept_invalid => {
            builder.danger_accept_invalid_certs(true);
        }
        None => return Ok(None),
    }
    Ok(Some(tokio_tungstenite::Connector::NativeTls(builder.build()?)))
}

#[cfg(test)]
mod tests {
    use super::*;

    const PEM: &str = "-----BEGIN CERTIFICATE-----\nAAAA\nBBBB\n-----END CERTIFICATE-----\n";

    /// Opt-in end-to-end check against a real HTTPS endpoint, e.g.
    /// OMNI_PIN_URL=https://127.0.0.1/api/agents/version
    /// OMNI_PIN_CERT=/etc/nginx/ssl/omni.crt cargo test pin_ -- --ignored
    #[tokio::test]
    #[ignore]
    async fn pin_accepts_the_pinned_server_and_nothing_else() {
        let url = std::env::var("OMNI_PIN_URL").expect("OMNI_PIN_URL");
        let pem = std::fs::read_to_string(std::env::var("OMNI_PIN_CERT").expect("OMNI_PIN_CERT")).unwrap();
        let pinned = Trust { pinned_pem: Some(pem), accept_invalid: false };
        assert!(client_for(&pinned).build().unwrap().get(&url).send().await.is_ok(), "pinned cert must verify");

        let unpinned = Trust::default(); // OS store only: a self-signed server is refused
        assert!(client_for(&unpinned).build().unwrap().get(&url).send().await.is_err());

        // A different certificate pinned: refused even though the legacy flag is set.
        let decoy = std::env::temp_dir().join(format!("omni-pin-decoy-{}.pem", std::process::id()));
        let made = std::process::Command::new("openssl")
            .args(["req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout"])
            .arg(if cfg!(windows) { "NUL" } else { "/dev/null" })
            .arg("-out").arg(&decoy)
            .args(["-days", "1", "-subj", "/CN=127.0.0.1", "-addext", "subjectAltName=IP:127.0.0.1"])
            .output()
            .expect("openssl");
        assert!(made.status.success());
        let other = Trust { pinned_pem: Some(std::fs::read_to_string(&decoy).unwrap()), accept_invalid: true };
        let _ = std::fs::remove_file(&decoy);
        assert!(client_for(&other).build().unwrap().get(&url).send().await.is_err());

        // WebSockets: with the pin the TLS handshake succeeds (whatever the
        // HTTP upgrade then answers); with the wrong pin it fails as TLS.
        let ws_url = url.replacen("https://", "wss://", 1);
        let ws = |t: Trust| {
            let ws_url = ws_url.clone();
            async move {
                tokio_tungstenite::connect_async_tls_with_config(ws_url, None, false, ws_connector_for(&t).unwrap()).await
            }
        };
        let tls_failed = |r: &Result<_, tokio_tungstenite::tungstenite::Error>| {
            matches!(r, Err(tokio_tungstenite::tungstenite::Error::Tls(_)))
        };
        assert!(!tls_failed(&ws(pinned.clone()).await), "pinned cert must pass the TLS handshake");
        assert!(tls_failed(&ws(other).await));
    }

    /// The config.yaml the installers write (backend config_yaml_text).
    #[test]
    fn installer_config_carries_the_certificate() {
        let cfg: crate::config::Config =
            serde_norway::from_str(include_str!("../tests/fixtures/installer_config.yaml")).unwrap();
        let pem = cfg.server_ca_cert.expect("server_ca_cert");
        assert!(pem.starts_with("-----BEGIN CERTIFICATE-----\n"));
        assert!(reqwest::Certificate::from_pem(pem.as_bytes()).is_ok());
        assert!(native_tls::Certificate::from_pem(pem.as_bytes()).is_ok());
        assert!(!cfg.accept_invalid_certs);
    }

    #[test]
    fn der_base64_strips_armor_and_newlines() {
        let _ = TRUST.set(Trust { pinned_pem: Some(PEM.to_string()), accept_invalid: true });
        assert_eq!(pinned_der_base64().as_deref(), Some("AAAABBBB"));
    }
}
