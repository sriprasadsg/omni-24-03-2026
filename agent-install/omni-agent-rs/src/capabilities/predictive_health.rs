use super::Capability;
use serde_json::{json, Value};
use std::collections::VecDeque;
use std::sync::Mutex;
use sysinfo::{Disks, System};

const HISTORY_LEN: usize = 30;
const TICKS_PER_HOUR: f32 = 120.0; // 3600s / 30s per tick

struct HealthHistory {
    cpu: VecDeque<f32>,
    mem: VecDeque<f32>,
    disk: VecDeque<f32>,
}

pub struct PredictiveHealthCapability {
    history: Mutex<HealthHistory>,
}

impl PredictiveHealthCapability {
    pub fn new() -> Self {
        PredictiveHealthCapability {
            history: Mutex::new(HealthHistory {
                cpu: VecDeque::with_capacity(HISTORY_LEN),
                mem: VecDeque::with_capacity(HISTORY_LEN),
                disk: VecDeque::with_capacity(HISTORY_LEN),
            }),
        }
    }
}

impl Capability for PredictiveHealthCapability {
    fn id(&self) -> &'static str { "predictive_health" }
    fn name(&self) -> &'static str { "Predictive Health" }

    fn collect(&self, sys: &System) -> Value {
        let cpus = sys.cpus();
        let cpu_now = if cpus.is_empty() {
            0.0f32
        } else {
            cpus.iter().map(|c| c.cpu_usage()).sum::<f32>() / cpus.len() as f32
        };
        let total_mem = sys.total_memory();
        let mem_now = if total_mem > 0 {
            sys.used_memory() as f32 / total_mem as f32 * 100.0
        } else {
            0.0f32
        };

        let disks = Disks::new_with_refreshed_list();
        let disk_now = disks.iter().next()
            .map(|d| {
                let total = d.total_space();
                let free = d.available_space();
                if total == 0 { 0.0f32 } else { (total - free) as f32 / total as f32 * 100.0 }
            })
            .unwrap_or(0.0f32);

        let mut hist = self.history.lock().unwrap_or_else(|p| p.into_inner());
        if hist.cpu.len() >= HISTORY_LEN {
            hist.cpu.pop_front();
            hist.mem.pop_front();
            hist.disk.pop_front();
        }
        hist.cpu.push_back(cpu_now);
        hist.mem.push_back(mem_now);
        hist.disk.push_back(disk_now);

        let cpu_trend = trend_label(&hist.cpu);
        let mem_trend = trend_label(&hist.mem);
        let disk_trend = trend_label(&hist.disk);

        let slope_cpu = slope(&hist.cpu);
        let slope_mem = slope(&hist.mem);
        let _slope_disk = slope(&hist.disk);

        let cpu_exhaust = exhaust_hours(&hist.cpu, 95.0);
        let mem_exhaust = exhaust_hours(&hist.mem, 95.0);
        let disk_exhaust = exhaust_hours(&hist.disk, 95.0);

        let history_points = hist.cpu.len();
        drop(hist); // release lock before building output

        // Health score: weighted inverse of resource usage (0–100)
        let current_score = ((100.0 - (cpu_now * 0.4 + mem_now * 0.35 + disk_now * 0.25)) as i64)
            .max(0)
            .min(100);

        // 24-hour forecast: extrapolate each resource linearly from current values
        let now = chrono::Utc::now();
        let predictions: Vec<Value> = (0..24).map(|i| {
            let t = now + chrono::Duration::hours(i as i64);
            let ts = t.format("%H:%M").to_string();

            let cpu_t = (cpu_now + slope_cpu * TICKS_PER_HOUR * i as f32).max(0.0).min(100.0);
            let mem_t = (mem_now + slope_mem * TICKS_PER_HOUR * i as f32).max(0.0).min(100.0);
            let health = (100.0 - (cpu_t * 0.4 + mem_t * 0.35)).max(0.0).min(100.0);

            json!({
                "timestamp": ts,
                "cpu_prediction": (cpu_t * 10.0).round() / 10.0,
                "memory_prediction": (mem_t * 10.0).round() / 10.0,
                "health_score": (health * 10.0).round() / 10.0,
            })
        }).collect();

        // Warnings from exhaustion projections
        let mut warnings: Vec<String> = Vec::new();
        if let Some(h) = cpu_exhaust {
            if h < 24.0 {
                warnings.push(format!("CPU projected to reach 95% in {:.1} hours", h));
            }
        }
        if let Some(h) = mem_exhaust {
            if h < 24.0 {
                warnings.push(format!("Memory projected to reach 95% in {:.1} hours", h));
            }
        }
        if let Some(h) = disk_exhaust {
            if h < 24.0 {
                warnings.push(format!("Disk projected to reach 95% in {:.1} hours", h));
            }
        }

        json!({
            "current_score": current_score,
            "predictions": predictions,
            "warnings": warnings,
            "cpu_trend": cpu_trend,
            "memory_trend": mem_trend,
            "disk_trend": disk_trend,
            "current_cpu_percent": (cpu_now * 10.0).round() / 10.0,
            "current_memory_percent": (mem_now * 10.0).round() / 10.0,
            "current_disk_percent": (disk_now * 10.0).round() / 10.0,
            "history_points": history_points,
            "timestamp": now.to_rfc3339(),
        })
    }
}

fn slope(data: &VecDeque<f32>) -> f32 {
    if data.len() < 2 {
        return 0.0;
    }
    let n = data.len() as f32;
    let x_mean = (n - 1.0) / 2.0;
    let y_mean: f32 = data.iter().sum::<f32>() / n;
    let numerator: f32 = data
        .iter()
        .enumerate()
        .map(|(i, &y)| (i as f32 - x_mean) * (y - y_mean))
        .sum();
    let denominator: f32 = (0..data.len())
        .map(|i| (i as f32 - x_mean).powi(2))
        .sum();
    if denominator == 0.0 {
        0.0
    } else {
        numerator / denominator
    }
}

fn trend_label(data: &VecDeque<f32>) -> &'static str {
    let s = slope(data);
    if s > 1.0 {
        "increasing"
    } else if s < -1.0 {
        "decreasing"
    } else {
        "stable"
    }
}

fn exhaust_hours(data: &VecDeque<f32>, threshold: f32) -> Option<f64> {
    if data.is_empty() {
        return None;
    }
    let current = *data.back().unwrap();
    if current >= threshold {
        return Some(0.0);
    }
    let s = slope(data);
    if s <= 0.0 {
        return None;
    }
    let ticks_to_exhaust = (threshold - current) / s;
    Some((ticks_to_exhaust * 30.0 / 3600.0) as f64)
}
