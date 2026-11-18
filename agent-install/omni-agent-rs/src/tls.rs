//! TLS trust for connections to the platform.
//!
//! Installers put the platform's certificate in config.yaml (`server_ca_cert`,
//! PEM; during a certificate change, several). When it is set, every connection
//! to the platform trusts those certificates and nothing else — not the OS store
//! — so someone on the network can't pose as the server, even with a publicly
//! trusted certificate. Calls to third-party hosts (the public-IP lookup) keep
//! the OS store.
//!
//! Certificate changes: a heartbeat reply may carry `serverTrust.certs`, the
//! whole list the platform wants trusted. It is taken only while the agent pins
//! (so the reply came over a pinned connection) and only if it keeps a
//! certificate trusted now, so a wrong reply cannot cut the agent off. It
//! replaces the trust at once and is saved to config.yaml. With `next` and
//! `probePort`, the agent also connects to the probe port trusting only the next
//! certificate and reports the result (`tls_probe`), so the platform switches
//! only once its agents have passed.
//!
//! Without a pinned certificate the legacy `accept_invalid_certs` flag still
//! applies, so agents installed before pinning keep working until reinstalled.

use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::sync::{Mutex, RwLock};
use std::time::{Duration, Instant};

#[derive(Clone, Default)]
struct Trust {
    pinned_pem: Option<String>,
    accept_invalid: bool,
}

static TRUST: RwLock<Option<Trust>> = RwLock::new(None);

/// Record the platform trust settings. Called once at startup, after config
/// load; later calls are ignored (a certificate change goes through
/// `update_from_heartbeat`).
pub fn init(cfg: &crate::config::Config) {
    let pinned_pem = cfg
        .server_ca_cert
        .as_deref()
        .map(str::trim)
        .filter(|pem| !pem.is_empty())
        .map(str::to_string);
    let mut guard = TRUST.write().unwrap_or_else(|p| p.into_inner());
    if guard.is_some() {
        return;
    }
    if let Some(pem) = &pinned_pem {
        log::info!("TLS: platform connections trust only the pinned server certificate(s): {}", fingerprints_of(pem).join(", "));
    } else if cfg.accept_invalid_certs {
        log::warn!("TLS: certificate checks are OFF for the platform (accept_invalid_certs); reinstall to pin");
    }
    *guard = Some(Trust { pinned_pem, accept_invalid: cfg.accept_invalid_certs });
}

fn trust() -> Trust {
    TRUST.read().unwrap_or_else(|p| p.into_inner()).clone().unwrap_or_default()
}

/// The certificates in a PEM text, each with its armor.
pub fn split_pem(text: &str) -> Vec<String> {
    let (mut out, mut cur, mut inside) = (Vec::new(), String::new(), false);
    for line in text.lines().map(str::trim) {
        if line == "-----BEGIN CERTIFICATE-----" {
            inside = true;
            cur.clear();
        }
        if inside {
            cur.push_str(line);
            cur.push('\n');
            if line == "-----END CERTIFICATE-----" {
                out.push(std::mem::take(&mut cur));
                inside = false;
            }
        }
    }
    out
}

/// SHA-256 of a certificate's DER, lowercase hex: how the platform names a certificate.
pub fn fingerprint(pem: &str) -> Option<String> {
    let der = native_tls::Certificate::from_pem(pem.as_bytes()).ok()?.to_der().ok()?;
    Some(hex::encode(Sha256::digest(der)))
}

fn fingerprints_of(pem: &str) -> Vec<String> {
    split_pem(pem).iter().filter_map(|c| fingerprint(c)).collect()
}

/// The pinned certificates' fingerprints (empty when nothing is pinned), sent with each heartbeat.
pub fn fingerprints() -> Vec<String> {
    trust().pinned_pem.as_deref().map(fingerprints_of).unwrap_or_default()
}

/// Each pinned certificate as DER, base64-encoded: what the PowerShell tray and
/// chat windows compare the server's certificate against.
pub fn pinned_der_base64() -> Vec<String> {
    let Some(pem) = trust().pinned_pem else { return Vec::new() };
    split_pem(&pem)
        .iter()
        .map(|c| c.lines().filter(|l| !l.starts_with("-----")).collect::<String>())
        .filter(|body| !body.is_empty())
        .collect()
}

fn pinned_reqwest_certs(pem: &str) -> Vec<reqwest::Certificate> {
    let certs: Vec<reqwest::Certificate> = split_pem(pem)
        .iter()
        .filter_map(|c| match reqwest::Certificate::from_pem(c.as_bytes()) {
            Ok(cert) => Some(cert),
            Err(e) => {
                log::error!("TLS: a certificate in server_ca_cert is not valid PEM ({e}); it is not trusted");
                None
            }
        })
        .collect();
    if certs.is_empty() {
        // Fail closed: with tls_certs_only and no roots, nothing verifies.
        log::error!("TLS: server_ca_cert holds no valid certificate; platform connections will fail");
    }
    certs
}

/// Async HTTP client builder for platform requests. A client built before a
/// certificate change keeps the old trust; agent_loop rebuilds its own.
pub fn platform_client() -> reqwest::ClientBuilder {
    client_for(&trust())
}

fn client_for(t: &Trust) -> reqwest::ClientBuilder {
    let builder = reqwest::Client::builder();
    match &t.pinned_pem {
        Some(pem) => builder.tls_certs_only(pinned_reqwest_certs(pem)),
        None => builder.danger_accept_invalid_certs(t.accept_invalid),
    }
}

/// Blocking HTTP client builder for platform requests.
pub fn platform_blocking_client() -> reqwest::blocking::ClientBuilder {
    let t = trust();
    let builder = reqwest::blocking::Client::builder();
    match t.pinned_pem {
        Some(pem) => builder.tls_certs_only(pinned_reqwest_certs(&pem)),
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
            for c in split_pem(pem) {
                match native_tls::Certificate::from_pem(c.as_bytes()) {
                    Ok(cert) => {
                        builder.add_root_certificate(cert);
                    }
                    Err(e) => log::error!("TLS: a certificate in server_ca_cert is not valid PEM ({e})"),
                }
            }
        }
        None if t.accept_invalid => {
            builder.danger_accept_invalid_certs(true);
        }
        None => return Ok(None),
    }
    Ok(Some(tokio_tungstenite::Connector::NativeTls(builder.build()?)))
}

/// The list to trust instead of `current`: None when it holds the same certificates. Refused when it
/// is empty or too long, when a certificate does not parse, or when it keeps none of the current ones.
pub(crate) fn accept_bundle(current: &str, bundle: &str) -> Result<Option<String>, String> {
    let new = split_pem(bundle);
    if new.is_empty() || new.len() > 8 {
        return Err(format!("{} certificates (1 to 8 expected)", new.len()));
    }
    let mut new_fps = Vec::new();
    for c in &new {
        if reqwest::Certificate::from_pem(c.as_bytes()).is_err() {
            return Err("a certificate does not parse".into());
        }
        new_fps.push(fingerprint(c).ok_or("a certificate does not parse")?);
    }
    let mut current_fps = fingerprints_of(current);
    if !new_fps.iter().any(|f| current_fps.contains(f)) {
        return Err("it keeps none of the certificates trusted now".into());
    }
    let mut sorted_new = new_fps.clone();
    sorted_new.sort();
    sorted_new.dedup();
    current_fps.sort();
    current_fps.dedup();
    Ok((sorted_new != current_fps).then(|| new.concat()))
}

/// Takes the certificate list a heartbeat reply carries (see the module notes) and saves it to
/// config.yaml. True when the trust changed: the caller rebuilds its long-lived client and the tray config.
pub fn update_from_heartbeat(cfg: &mut crate::config::Config, body: &Value) -> bool {
    if !apply_reply(cfg, body) {
        return false;
    }
    if let Err(e) = crate::config::save(cfg) {
        log::warn!("TLS: could not save the new certificates to config.yaml ({e}); they apply until a restart");
    }
    true
}

/// The trust and `cfg` changed by a reply, without saving: true when the trusted list changed.
fn apply_reply(cfg: &mut crate::config::Config, body: &Value) -> bool {
    let Some(server_trust) = body.get("serverTrust").filter(|v| v.is_object()) else { return false };
    note_probe_request(cfg, server_trust);
    let Some(bundle) = server_trust.get("certs").and_then(Value::as_str) else { return false };
    let Some(current) = trust().pinned_pem else {
        log::warn!("TLS: ignored a certificate list from the platform: nothing is pinned, so the reply is not authenticated");
        return false;
    };
    match accept_bundle(&current, bundle) {
        Ok(None) => false,
        Ok(Some(pem)) => {
            log::info!("TLS: the platform changed the trusted certificates to {}", fingerprints_of(&pem).join(", "));
            cfg.server_ca_cert = Some(pem.clone());
            let mut guard = TRUST.write().unwrap_or_else(|p| p.into_inner());
            let accept_invalid = guard.as_ref().map_or(cfg.accept_invalid_certs, |t| t.accept_invalid);
            *guard = Some(Trust { pinned_pem: Some(pem), accept_invalid });
            true
        }
        Err(why) => {
            log::warn!("TLS: refused a certificate list from the platform: {why}");
            false
        }
    }
}

// ── Probe of the next certificate ───────────────────────────────────────────

#[derive(Clone, PartialEq)]
struct ProbeAsk {
    url: String,
    next: Vec<String>,
}

#[derive(Default)]
struct ProbeState {
    ask: Option<ProbeAsk>,
    result: Option<(ProbeAsk, bool, Value)>,
    last_try: Option<Instant>,
}

static PROBE: Mutex<ProbeState> = Mutex::new(ProbeState { ask: None, result: None, last_try: None });

/// A failed probe is tried again after this long; a passed one only when the ask changes.
const PROBE_RETRY: Duration = Duration::from_secs(1800);

/// The probe URL: the platform's own host on `port`, path /api/health. None for a non-https platform.
pub(crate) fn probe_url(api_base_url: &str, port: u16) -> Option<String> {
    let mut url = reqwest::Url::parse(api_base_url.trim()).ok()?;
    if url.scheme() != "https" || url.set_port(Some(port)).is_err() {
        return None;
    }
    url.set_path("/api/health");
    url.set_query(None);
    Some(url.to_string())
}

fn note_probe_request(cfg: &crate::config::Config, server_trust: &Value) {
    let next: Vec<String> = server_trust.get("next").and_then(Value::as_array).into_iter().flatten()
        .filter_map(Value::as_str).filter(|f| f.len() == 64 && f.chars().all(|c| c.is_ascii_hexdigit()))
        .map(str::to_lowercase).collect();
    let port = server_trust.get("probePort").and_then(Value::as_u64).and_then(|p| u16::try_from(p).ok());
    let ask = match (next.is_empty(), port.and_then(|p| probe_url(&cfg.api_base_url, p))) {
        (false, Some(url)) => Some(ProbeAsk { url, next }),
        _ => None,
    };
    PROBE.lock().unwrap_or_else(|p| p.into_inner()).ask = ask;
}

/// The last probe result for the platform (null when none was asked).
pub fn probe_report() -> Value {
    let state = PROBE.lock().unwrap_or_else(|p| p.into_inner());
    match (&state.ask, &state.result) {
        (Some(ask), Some((done, _, report))) if done == ask => report.clone(),
        _ => Value::Null,
    }
}

/// Connects to the probe port trusting only the next certificate(s), when the platform asked and the
/// last try is not current. Called once per loop turn, after the heartbeat.
pub async fn probe_if_due() {
    let ask = {
        let state = PROBE.lock().unwrap_or_else(|p| p.into_inner());
        let Some(ask) = state.ask.clone() else { return };
        let fresh = matches!(&state.result, Some((done, ok, _)) if *done == ask
                             && (*ok || state.last_try.map_or(false, |t| t.elapsed() < PROBE_RETRY)));
        if fresh {
            return;
        }
        ask
    };
    let pinned = trust().pinned_pem.unwrap_or_default();
    let next_pem: String = split_pem(&pinned).into_iter()
        .filter(|c| fingerprint(c).map_or(false, |f| ask.next.contains(&f))).collect();
    let outcome = if next_pem.is_empty() {
        Err("the next certificate is not in this agent's trusted list".to_string())
    } else {
        let only_next = Trust { pinned_pem: Some(next_pem), accept_invalid: false };
        match client_for(&only_next).timeout(Duration::from_secs(15)).build() {
            Err(e) => Err(format!("client: {e}")),
            Ok(client) => match client.get(&ask.url).send().await {
                Ok(resp) => Ok(resp.status().as_u16()),
                Err(e) => Err(probe_error(&e)),
            },
        }
    };
    let ok = outcome.is_ok();
    let report = json!({
        "url": ask.url,
        "fingerprints": ask.next,
        "ok": ok,
        "status": outcome.as_ref().ok(),
        "error": outcome.as_ref().err(),
        "at": chrono::Utc::now().to_rfc3339(),
    });
    match &outcome {
        Ok(status) => log::info!("TLS: the next certificate passed on {} (HTTP {status})", ask.url),
        Err(e) => log::warn!("TLS: the next certificate failed on {}: {e}", ask.url),
    }
    let mut state = PROBE.lock().unwrap_or_else(|p| p.into_inner());
    state.result = Some((ask, ok, report));
    state.last_try = Some(Instant::now());
}

/// The whole error chain, so "connect" and "certificate" failures read apart.
fn probe_error(e: &reqwest::Error) -> String {
    let mut text = if e.is_connect() { "could not connect: ".to_string() } else if e.is_timeout() { "timed out: ".to_string() } else { String::new() };
    let mut source: Option<&dyn std::error::Error> = Some(e);
    let mut parts = Vec::new();
    while let Some(err) = source {
        parts.push(err.to_string());
        source = err.source();
    }
    text.push_str(&parts.join(": "));
    text.chars().take(300).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    const A: &str = include_str!("../tests/fixtures/rollover_a.crt");
    const B: &str = include_str!("../tests/fixtures/rollover_b.crt");
    const FP_A: &str = "df858a8cf168dd3fea515aa3163cae31ed1ca69f93f719770c7aade34214dc3d";
    const FP_B: &str = "b149b57417c27f76f8529bdf11319bf63fd02b25f37b1d312a08f22e9b7f986d";

    /// Opt-in end-to-end check against a real HTTPS endpoint, e.g.
    /// OMNI_PIN_URL=https://127.0.0.1/api/agents/version
    /// OMNI_PIN_CERT=/etc/nginx/ssl/omni.crt cargo test pin_ -- --ignored
    #[tokio::test]
    #[ignore]
    async fn pin_accepts_the_pinned_server_and_nothing_else() {
        let url = std::env::var("OMNI_PIN_URL").expect("OMNI_PIN_URL");
        let pem = std::fs::read_to_string(std::env::var("OMNI_PIN_CERT").expect("OMNI_PIN_CERT")).unwrap();
        let pinned = Trust { pinned_pem: Some(pem.clone()), accept_invalid: false };
        assert!(client_for(&pinned).build().unwrap().get(&url).send().await.is_ok(), "pinned cert must verify");

        // A list holding the server's certificate and another one verifies too.
        let both = Trust { pinned_pem: Some(format!("{A}{pem}")), accept_invalid: false };
        assert!(client_for(&both).build().unwrap().get(&url).send().await.is_ok(), "a list with the cert must verify");

        let unpinned = Trust::default(); // OS store only: a self-signed server is refused
        assert!(client_for(&unpinned).build().unwrap().get(&url).send().await.is_err());

        // A different certificate pinned: refused even though the legacy flag is set.
        let other = Trust { pinned_pem: Some(A.to_string()), accept_invalid: true };
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
    fn a_pem_list_splits_into_certificates_named_by_their_der_hash() {
        let list = format!("{A}\n\n{B}");
        let certs = split_pem(&list);
        assert_eq!(certs.len(), 2);
        assert_eq!((fingerprint(&certs[0]).as_deref(), fingerprint(&certs[1]).as_deref()), (Some(FP_A), Some(FP_B)));
        assert!(split_pem("-----BEGIN CERTIFICATE-----\nAAAA\n").is_empty(), "an unterminated block is no certificate");
        assert_eq!(fingerprint("-----BEGIN CERTIFICATE-----\nAAAA\n-----END CERTIFICATE-----\n"), None);
    }

    #[test]
    fn a_new_list_is_taken_only_if_it_keeps_a_trusted_certificate() {
        let both = format!("{A}{B}");
        // Adding the next certificate, then dropping the old one: both keep one trusted now.
        assert_eq!(accept_bundle(A, &both).unwrap().map(|p| split_pem(&p).len()), Some(2));
        assert_eq!(accept_bundle(&both, B).unwrap().map(|p| fingerprints_of(&p)), Some(vec![FP_B.to_string()]));
        // The same certificates in another order are no change.
        assert_eq!(accept_bundle(&both, &format!("{B}{A}")), Ok(None));
        // Replacing everything at once would cut the agent off.
        assert!(accept_bundle(A, B).unwrap_err().contains("keeps none"));
        assert!(accept_bundle(A, "").is_err());
        assert!(accept_bundle(A, &format!("{A}-----BEGIN CERTIFICATE-----\nAAAA\n-----END CERTIFICATE-----\n")).is_err());
        assert!(accept_bundle(A, &A.repeat(9)).is_err());
    }

    #[test]
    fn the_probe_goes_to_the_platform_host_on_the_probe_port() {
        assert_eq!(probe_url("https://135.237.98.107", 8443).as_deref(), Some("https://135.237.98.107:8443/api/health"));
        assert_eq!(probe_url("https://10.0.0.4:443/api/?x=1", 8443).as_deref(), Some("https://10.0.0.4:8443/api/health"));
        assert_eq!(probe_url("http://10.0.0.4", 8443), None);
        assert_eq!(probe_url("not a url", 8443), None);
    }

    #[test]
    fn trust_changes_only_through_an_authenticated_reply_and_reports_the_probe_it_was_asked_for() {
        // One test owns the process-wide trust, so the steps run in order.
        *TRUST.write().unwrap() = Some(Trust { pinned_pem: Some(A.to_string()), accept_invalid: true });
        assert_eq!(pinned_der_base64().len(), 1);
        let mut cfg: crate::config::Config =
            serde_norway::from_str(include_str!("../tests/fixtures/installer_config.yaml")).unwrap();
        cfg.api_base_url = "https://10.0.0.1".into();
        let reply = json!({"serverTrust": {"certs": format!("{A}{B}"), "next": [FP_B], "probePort": 8443}});
        assert!(apply_reply(&mut cfg, &reply));
        assert_eq!(fingerprints(), vec![FP_A.to_string(), FP_B.to_string()]);
        assert_eq!(pinned_der_base64().len(), 2);
        assert_eq!(cfg.server_ca_cert.as_deref().map(split_pem).map(|c| c.len()), Some(2));
        assert_eq!(PROBE.lock().unwrap().ask.as_ref().map(|a| a.url.clone()).as_deref(), Some("https://10.0.0.1:8443/api/health"));
        assert_eq!(probe_report(), Value::Null, "nothing tried yet");
        assert!(!apply_reply(&mut cfg, &reply), "the same list again is no change");
        assert!(!apply_reply(&mut cfg, &json!({"serverTrust": {"certs": "garbage"}})));
        assert_eq!(fingerprints().len(), 2);
        assert!(PROBE.lock().unwrap().ask.is_none(), "a reply without a next certificate ends the probe");
    }
}
