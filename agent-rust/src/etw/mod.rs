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
use std::sync::{atomic::AtomicBool, Arc};

use reqwest::Client;
use tokio::sync::RwLock;

use crate::{buffer::Spool, config::Config};

#[cfg(not(windows))]
#[allow(dead_code)]
pub async fn start_engine(
    _cfg: Arc<RwLock<Config>>,
    _client: Arc<Client>,
    _running: Arc<AtomicBool>,
    _spool: Arc<Spool>,
) {
    crate::olog!("[etw] real-time telemetry unsupported on this platform — engine disabled");
}

#[cfg(windows)]
pub async fn start_engine(
    cfg: Arc<RwLock<Config>>,
    client: Arc<Client>,
    running: Arc<AtomicBool>,
    spool: Arc<Spool>,
) {
    windows_impl::run(cfg, client, running, spool).await;
}

#[cfg(windows)]
mod schema;

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

    use super::schema::{
        decode_network, decode_process, decode_registry, RawEvent, KERNEL_NETWORK_GUID,
        KERNEL_PROCESS_GUID, KERNEL_REGISTRY_GUID,
    };

    /// Bounded queue between the (synchronous) ETW callback and the async upload loop.
    /// The callback NEVER blocks — a full queue drops the event and bumps a counter, so a
    /// storm can't stall the kernel session (which would lose events system-wide).
    const CHANNEL_CAP: usize = 65_536;
    const BATCH_MAX: usize = 512;
    const FLUSH_SECS: u64 = 2;
    /// Live-process table bound. Beyond this, oldest-inserted entries are evicted.
    const PROC_TABLE_CAP: usize = 16_384;

    type DecodeFn = fn(&EventRecord, &SchemaLocator) -> Option<RawEvent>;

    /// Build a manifest provider whose callback decodes events and funnels them onto the
    /// bounded channel. The callback never blocks: a full queue drops + counts the event.
    fn make_provider(
        guid: &str,
        tx: mpsc::Sender<RawEvent>,
        dropped: Arc<AtomicU64>,
        decode: DecodeFn,
    ) -> Provider {
        Provider::by_guid(guid)
            .add_callback(move |record: &EventRecord, sl: &SchemaLocator| {
                if let Some(ev) = decode(record, sl) {
                    if tx.try_send(ev).is_err() {
                        dropped.fetch_add(1, Ordering::Relaxed);
                    }
                }
            })
            .build()
    }

    /// Process lineage seen so far. Enriches network/registry events with the owning
    /// process's image + parent, so a connection or Run-key write carries who did it.
    struct Correlator {
        table: HashMap<u32, (Option<u32>, Option<String>)>, // pid -> (ppid, image)
        order: VecDeque<u32>,
    }

    impl Correlator {
        fn new() -> Self {
            Correlator { table: HashMap::new(), order: VecDeque::new() }
        }

        fn observe(&mut self, ev: &RawEvent) {
            if let RawEvent::Process { kind, pid, ppid, image, .. } = ev {
                if *kind == "process_start" && self.table.insert(*pid, (*ppid, image.clone())).is_none() {
                    self.order.push_back(*pid);
                    if self.order.len() > PROC_TABLE_CAP {
                        if let Some(old) = self.order.pop_front() {
                            self.table.remove(&old);
                        }
                    }
                }
            }
        }

        fn enrich(&self, ev: &RawEvent) -> Value {
            let mut j = ev.to_json();
            if let Some((ppid, image)) = self.table.get(&ev.pid()) {
                if let Some(obj) = j.as_object_mut() {
                    if let Some(img) = image {
                        obj.entry("proc_image").or_insert_with(|| json!(img));
                    }
                    if let Some(pp) = ppid {
                        obj.entry("proc_ppid").or_insert_with(|| json!(pp));
                    }
                }
            }
            j
        }
    }

    pub async fn run(
        cfg: Arc<RwLock<Config>>,
        client: Arc<Client>,
        running: Arc<AtomicBool>,
        spool: Arc<Spool>,
    ) {
        // Wait until the agent is registered (mirrors the other pollers).
        let (agent_id, token, base) = loop {
            if !running.load(Ordering::Relaxed) {
                return;
            }
            {
                let c = cfg.read().await;
                if let (Some(id), Some(tok)) = (&c.agent_id, &c.agent_token) {
                    break (
                        id.clone(),
                        tok.clone(),
                        c.api_base_url.trim_end_matches('/').to_string(),
                    );
                }
            }
            tokio::time::sleep(Duration::from_secs(5)).await;
        };

        let (tx, mut rx) = mpsc::channel::<RawEvent>(CHANNEL_CAP);
        let dropped = Arc::new(AtomicU64::new(0));

        // One provider per manifest source; each callback funnels to the same channel.
        let process_provider = make_provider(KERNEL_PROCESS_GUID, tx.clone(), dropped.clone(), decode_process);
        let network_provider = make_provider(KERNEL_NETWORK_GUID, tx.clone(), dropped.clone(), decode_network);
        let registry_provider = make_provider(KERNEL_REGISTRY_GUID, tx.clone(), dropped.clone(), decode_registry);
        drop(tx); // only the callbacks' clones keep the channel open; rx ends when the trace stops

        let trace = match UserTrace::new()
            .named("OmniAgent-ETW".to_string())
            .enable(process_provider)
            .enable(network_provider)
            .enable(registry_provider)
            .start_and_process()
        {
            Ok(t) => t,
            Err(e) => {
                crate::olog!("[etw] failed to start user trace: {:?} — engine disabled", e);
                return;
            }
        };
        crate::olog!("[etw] telemetry started (session OmniAgent-ETW): process + network + registry");

        let url = format!("{}/api/agents/{}/telemetry", base, agent_id);
        let mut batch: Vec<Value> = Vec::with_capacity(BATCH_MAX);
        let mut correlator = Correlator::new();
        let mut ticker = tokio::time::interval(Duration::from_secs(FLUSH_SECS));

        loop {
            if !running.load(Ordering::Relaxed) {
                break;
            }
            tokio::select! {
                maybe = rx.recv() => match maybe {
                    Some(ev) => {
                        correlator.observe(&ev);
                        batch.push(correlator.enrich(&ev));
                        if batch.len() >= BATCH_MAX {
                            flush(&client, &url, &token, &agent_id, &mut batch, &spool, &dropped).await;
                        }
                    }
                    None => break, // trace stopped / channel closed
                },
                _ = ticker.tick() => {
                    flush(&client, &url, &token, &agent_id, &mut batch, &spool, &dropped).await;
                }
            }
        }

        flush(&client, &url, &token, &agent_id, &mut batch, &spool, &dropped).await;
        let _ = trace.stop();
        crate::olog!("[etw] telemetry engine stopped");
    }

    async fn flush(
        client: &Client,
        url: &str,
        token: &str,
        agent_id: &str,
        batch: &mut Vec<Value>,
        spool: &Spool,
        dropped: &AtomicU64,
    ) {
        if batch.is_empty() {
            return;
        }
        let now = chrono::Utc::now();
        let body = json!({
            "batch_id": format!("{}-{}", agent_id, now.timestamp_millis()),
            "collected_at": now.to_rfc3339(),
            "dropped_events": dropped.swap(0, Ordering::Relaxed),
            "events": std::mem::take(batch),
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
