/*!
 * Real-time ETW telemetry engine — Phase 1 (Kernel-Process).
 *
 * Streams process start/stop events from the ETW Kernel-Process provider, normalizes
 * them to `RawEvent`, batches, and uploads to `POST /api/agents/{id}/telemetry`,
 * reusing the offline `Spool` so telemetry survives backend outages.
 *
 * This is the pipeline skeleton described in docs/etw-telemetry-design.md §11 P1.
 * Later phases add providers (network/registry/file/DNS), a process-tree correlator,
 * and a behavioural rule engine behind the same `RawEvent` boundary.
 *
 * Non-Windows builds compile a no-op stub so the crate checks/builds on Linux CI.
 */
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Arc;

use reqwest::Client;
use serde_json::{json, Value};
use tokio::sync::RwLock;

use crate::{buffer::Spool, config::Config};

use once_cell::sync::OnceCell;

pub struct EtwMetrics {
    pub events_total: AtomicU64,
    pub dropped_total: AtomicU64,
    pub detections_total: AtomicU64,
    pub restarts: AtomicU64,
    pub session_up: AtomicBool,
    pub last_event_unix: AtomicU64,
    /// True when high-volume providers (file) have been shed to survive a storm.
    pub file_shed: AtomicBool,
}

pub static METRICS: OnceCell<EtwMetrics> = OnceCell::new();

impl EtwMetrics {
    pub fn new() -> Self {
        EtwMetrics {
            events_total: AtomicU64::new(0),
            dropped_total: AtomicU64::new(0),
            detections_total: AtomicU64::new(0),
            restarts: AtomicU64::new(0),
            session_up: AtomicBool::new(false),
            last_event_unix: AtomicU64::new(0),
            file_shed: AtomicBool::new(false),
        }
    }

    pub fn snapshot_json(&self) -> Value {
        json!({
            "session_up":       self.session_up.load(Ordering::Relaxed),
            "events_total":     self.events_total.load(Ordering::Relaxed),
            "dropped_total":    self.dropped_total.load(Ordering::Relaxed),
            "detections_total": self.detections_total.load(Ordering::Relaxed),
            "restarts":         self.restarts.load(Ordering::Relaxed),
            "last_event_unix":  self.last_event_unix.load(Ordering::Relaxed),
            "file_shed":        self.file_shed.load(Ordering::Relaxed),
        })
    }
}

#[cfg(not(windows))]
#[allow(dead_code)]
pub async fn start_engine(
    _cfg: Arc<RwLock<Config>>,
    _client: Arc<Client>,
    _running: Arc<AtomicBool>,
    _spool: Arc<Spool>,
) {
    crate::olog!("[etw] real-time telemetry unsupported on this platform — engine disabled");
    METRICS.get_or_init(EtwMetrics::new).session_up.store(false, Ordering::Relaxed);
}

#[cfg(windows)]
pub async fn start_engine(
    cfg: Arc<RwLock<Config>>,
    client: Arc<Client>,
    running: Arc<AtomicBool>,
    spool: Arc<Spool>,
) {
    let _ = METRICS.set(EtwMetrics::new());
    windows_impl::run(cfg, client, running, spool).await;
}

#[cfg(windows)]
mod schema;

#[cfg(windows)]
mod rules;

#[cfg(windows)]
mod windows_impl {
    use super::*;
    use std::collections::{HashMap, VecDeque};
    use std::sync::atomic::{AtomicU64, Ordering};
    use std::time::Duration;

    use ferrisetw::provider::Provider;
    use ferrisetw::schema_locator::SchemaLocator;
    use ferrisetw::trace::UserTrace;
    use ferrisetw::EventRecord;
    use serde_json::{json, Value};
    use tokio::sync::mpsc;

    use super::rules;
    use super::schema::{
        decode_dns, decode_file, decode_network, decode_process, decode_registry, RawEvent, DNS_CLIENT_GUID,
        KERNEL_FILE_GUID, KERNEL_NETWORK_GUID, KERNEL_PROCESS_GUID, KERNEL_REGISTRY_GUID,
    };

    const CHANNEL_CAP: usize = 65_536;
    const BATCH_MAX: usize = 512;
    const FLUSH_SECS: u64 = 2;
    const PROC_TABLE_CAP: usize = 16_384;
    const SHED_DROP_THRESHOLD_PCT: f64 = 10.0;
    const SHED_CHECK_SECS: u64 = 10;

    type DecodeFn = fn(&EventRecord, &SchemaLocator) -> Option<RawEvent>;

    fn make_provider(
        guid: &str, tx: mpsc::Sender<RawEvent>, dropped: Arc<AtomicU64>, decode: DecodeFn,
    ) -> Provider {
        Provider::by_guid(guid)
            .add_callback(move |record: &EventRecord, sl: &SchemaLocator| {
                if let Some(ev) = decode(record, sl) {
                    if tx.try_send(ev).is_err() { dropped.fetch_add(1, Ordering::Relaxed); }
                }
            })
            .build()
    }

    struct Correlator {
        table: HashMap<u32, (Option<u32>, Option<String>)>,
        order: VecDeque<u32>,
    }

    impl Correlator {
        fn new() -> Self { Correlator { table: HashMap::new(), order: VecDeque::new() } }
        fn observe(&mut self, ev: &RawEvent) {
            if let RawEvent::Process { kind, pid, ppid, image, .. } = ev {
                if *kind == "process_start" && self.table.insert(*pid, (*ppid, image.clone())).is_none() {
                    self.order.push_back(*pid);
                    if self.order.len() > PROC_TABLE_CAP {
                        if let Some(old) = self.order.pop_front() { self.table.remove(&old); }
                    }
                }
            }
        }
        fn enrich(&self, ev: &RawEvent) -> Value {
            let mut j = ev.to_json();
            let obj = match j.as_object_mut() { Some(o) => o, None => return j };
            if let Some((ppid, image)) = self.table.get(&ev.pid()) {
                if let Some(img) = image { obj.entry("proc_image").or_insert_with(|| json!(img)); }
                if let Some(pp) = ppid { obj.entry("proc_ppid").or_insert_with(|| json!(pp)); }
            }
            if let RawEvent::Process { ppid: Some(pp), .. } = ev {
                if let Some((_, Some(parent_img))) = self.table.get(pp) {
                    obj.insert("parent_image".into(), json!(parent_img));
                }
            }
            j
        }
    }

    // Helper to get connection info for run_loop
    async fn get_conn_info(cfg: &Arc<RwLock<Config>>) -> (String, String, String) {
        loop {
            let c = cfg.read().await;
            if let (Some(id), Some(tok)) = (&c.agent_id, &c.agent_token) {
                return (id.clone(), tok.clone(), c.api_base_url.trim_end_matches('/').to_string());
            }
            tokio::time::sleep(Duration::from_secs(5)).await;
        }
    }

    async fn run_engine_loop(
        _cfg: Arc<RwLock<Config>>, client: Arc<Client>, running: Arc<AtomicBool>, spool: Arc<Spool>,
        agent_id: String, token: String, base: String,
        trace: UserTrace, mut rx: mpsc::Receiver<RawEvent>, dropped_events_counter: Arc<AtomicU64>,
        file_provider_enabled: bool,
    ) -> bool { // Returns true if shedding triggered restart
        METRICS.get().unwrap().session_up.store(true, Ordering::Relaxed);
        METRICS.get().unwrap().last_event_unix.store(chrono::Utc::now().timestamp_millis() as u64, Ordering::Relaxed);
        crate::olog!("[etw] telemetry started: file_enabled={}", file_provider_enabled);

        let url = format!("{}/api/agents/{}/telemetry", base, agent_id);
        let mut batch: Vec<Value> = Vec::with_capacity(BATCH_MAX);
        let mut detections: Vec<Value> = Vec::new();
        let mut correlator = Correlator::new();
        let mut ticker = tokio::time::interval(Duration::from_secs(FLUSH_SECS));
        let mut shed_ticker = tokio::time::interval(Duration::from_secs(SHED_CHECK_SECS));
        let mut events_since_check: u64 = 0;

        loop {
            if !running.load(Ordering::Relaxed) { break; }
            tokio::select! {
                maybe = rx.recv() => match maybe {
                    Some(ev) => {
                        events_since_check += 1;
                        METRICS.get().unwrap().events_total.fetch_add(1, Ordering::Relaxed);
                        correlator.observe(&ev);
                        let enriched = correlator.enrich(&ev);
                        for det in rules::evaluate(&enriched) { detections.push(det.to_json()); }
                        METRICS.get().unwrap().detections_total.fetch_add(detections.len() as u64, Ordering::Relaxed);
                        batch.push(enriched);
                        METRICS.get().unwrap().last_event_unix.store(chrono::Utc::now().timestamp_millis() as u64, Ordering::Relaxed);
                        if batch.len() >= BATCH_MAX { flush(&client, &url, &token, &agent_id, &mut batch, &mut detections, &spool, &dropped_events_counter).await; }
                    }
                    None => break,
                },
                _ = ticker.tick() => { flush(&client, &url, &token, &agent_id, &mut batch, &mut detections, &spool, &dropped_events_counter).await; }
                _ = shed_ticker.tick() => {
                    if file_provider_enabled { // Only shed if file provider is currently enabled
                        let current_dropped = dropped_events_counter.load(Ordering::Relaxed);
                        if events_since_check > 0 {
                            let drop_pct = (current_dropped as f64 / (events_since_check + current_dropped) as f64) * 100.0;
                            if drop_pct > SHED_DROP_THRESHOLD_PCT {
                                crate::olog!("[etw] drop rate {:.1}% > {:.1}% threshold — shedding Kernel-File provider", drop_pct, SHED_DROP_THRESHOLD_PCT);
                                METRICS.get().unwrap().file_shed.store(true, Ordering::Relaxed);
                                return true; // Signal shedding restart
                            }
                        }
                        events_since_check = 0;
                        dropped_events_counter.store(0, Ordering::Relaxed); // Reset dropped count after check
                    }
                }
            }
        }

        // Abnormal termination detection: channel closed while engine still marked as running.
        if running.load(Ordering::Relaxed) {
            METRICS.get().unwrap().restarts.fetch_add(1, Ordering::Relaxed);
            METRICS.get().unwrap().session_up.store(false, Ordering::Relaxed);
        }
        METRICS.get().unwrap().last_event_unix.store(0, Ordering::Relaxed);
        flush(&client, &url, &token, &agent_id, &mut batch, &mut detections, &spool, &dropped_events_counter).await;
        let _ = trace.stop();
        crate::olog!("[etw] telemetry engine stopped");
        false // No restart
    }

    pub async fn run(
        cfg: Arc<RwLock<Config>>,
        client: Arc<Client>,
        running: Arc<AtomicBool>,
        spool: Arc<Spool>,
    ) {
        let mut file_enabled = true;
        loop {
            let (agent_id, token, base) = get_conn_info(&cfg).await;
            let (tx, rx) = mpsc::channel::<RawEvent>(CHANNEL_CAP);
            let dropped_events_counter = Arc::new(AtomicU64::new(0)); // Dropped events for shedding calc

            let mut trace_builder = UserTrace::new().named("OmniAgent-ETW".to_string())
                .enable(make_provider(KERNEL_PROCESS_GUID, tx.clone(), dropped_events_counter.clone(), decode_process))
                .enable(make_provider(KERNEL_NETWORK_GUID, tx.clone(), dropped_events_counter.clone(), decode_network))
                .enable(make_provider(KERNEL_REGISTRY_GUID, tx.clone(), dropped_events_counter.clone(), decode_registry))
                .enable(make_provider(DNS_CLIENT_GUID, tx.clone(), dropped_events_counter.clone(), decode_dns));

            if file_enabled {
                trace_builder = trace_builder.enable(make_provider(KERNEL_FILE_GUID, tx.clone(), dropped_events_counter.clone(), decode_file));
            }
            drop(tx); // Close original tx, only callbacks' clones keep it open

            let trace = match trace_builder.start_and_process() {
                Ok(t) => t,
                Err(e) => {
                    crate::olog!("[etw] failed to start user trace: {:?} — engine disabled", e);
                    return;
                }
            };

            let shed_triggered = run_engine_loop(
                cfg.clone(), client.clone(), running.clone(), spool.clone(),
                agent_id.clone(), token.clone(), base.clone(),
                trace, rx, dropped_events_counter, file_enabled
            ).await;

            if shed_triggered {
                file_enabled = false;
                crate::olog!("[etw] restarting engine without file provider due to shedding");
                tokio::time::sleep(Duration::from_millis(500)).await; // Small delay before restart
            } else {
                break; // run_engine_loop exited without shedding, so we stop
            }
        }
    }

    async fn flush(
        client: &Client,
        url: &str,
        token: &str,
        agent_id: &str,
        batch: &mut Vec<Value>,
        detections: &mut Vec<Value>,
        spool: &Spool,
        dropped: &AtomicU64,
    ) {
        if batch.is_empty() && detections.is_empty() {
            return;
        }
        let now = chrono::Utc::now();
        let body = json!({
            "batch_id": format!("{}-{}", agent_id, now.timestamp_millis()),
            "collected_at": now.to_rfc3339(),
            "dropped_events": dropped.swap(0, Ordering::Relaxed),
            "events": std::mem::take(batch),
            "detections": std::mem::take(detections),
        });
        // Only a transport failure is retryable (spool for later). A server response —
        // including a 404 from a backend that hasn't shipped /telemetry yet — is a
        // decision on the payload, not an outage, so it is dropped rather than spooled
        // (otherwise a missing endpoint would fill the spool with un-acceptable batches).
        if client.post(url).bearer_auth(token).json(&body).send().await.is_err() {
            spool.enqueue(url, &body);
        }
    }
}
