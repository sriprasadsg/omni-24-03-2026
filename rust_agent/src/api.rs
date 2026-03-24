use serde::{Deserialize, Serialize};
use reqwest::Client;
use std::sync::Arc;
use tokio::sync::Mutex;
use log::{info, debug};
use sysinfo::{System, SystemExt};
use crate::capabilities::CapabilityManager;

#[derive(Serialize, Deserialize, Debug)]
pub struct RegistrationConfig {
    pub agent_id: String,
    // Add other config fields if needed
}

#[derive(Serialize, Deserialize, Debug)]
pub struct Instruction {
    pub id: String,
    pub instruction: String,
    // Add other fields from backend/tasks.py structure if needed
}

pub struct BackendClient {
    client: Client,
    base_url: String,
    agent_id: Mutex<Option<String>>,
}

impl BackendClient {
    pub fn new(base_url: String) -> Self {
        Self {
            client: Client::new(),
            base_url,
            agent_id: Mutex::new(None),
        }
    }


    pub async fn register(&self, manager: Arc<Mutex<CapabilityManager>>) -> Result<RegistrationConfig, Box<dyn std::error::Error>> {
        let mut sys = System::new_all();
        sys.refresh_all();
        let hostname = hostname::get()?.to_string_lossy().to_string();
        let os = std::env::consts::OS.to_string();
        
        let capabilities = vec![
            "compliance_enforcement", "metrics_collection", "system_patching"
        ];
        
        // Hardcoded key for demo/default tenant
        let reg_key = "reg_937f5bbead6643e7";

        let payload = serde_json::json!({
            "hostname": hostname,
            "ipAddress": "127.0.0.1", 
            "os": os,
            "version": "2.0.0-rust",
            "capabilities": capabilities,
            "registrationKey": reg_key, 
            "system_info": {
                "cpu_arch": std::env::consts::ARCH,
                "total_memory": sys.total_memory(),
            }
        });

        let resp = self.client.post(format!("{}/api/agents/register", self.base_url))
            .json(&payload)
            .send()
            .await?
            .json::<serde_json::Value>()
            .await?;
            
        println!("DEBUG REGISTRATION RESPONSE: {}", serde_json::to_string_pretty(&resp).unwrap_or_default());

        // Fix: Backend returns "agentId" (camelCase)
        let agent_id = resp["agentId"].as_str().ok_or("No agentId in response")?.to_string();
        // Backend V2 Register doesn't return a token, we rely on the key we validated with? 
        // Or we use X-Tenant-Key header subsequent calls.
        
        *self.agent_id.lock().await = Some(agent_id.clone());
        manager.lock().await.set_agent_id(agent_id.clone());

        Ok(RegistrationConfig { agent_id })
    }

    pub async fn send_heartbeat(&self, manager: Arc<Mutex<CapabilityManager>>) -> Result<(), Box<dyn std::error::Error>> {
        let agent_id = self.agent_id.lock().await.clone().ok_or("Not registered")?;
        
        let mut sys = System::new_all();
        sys.refresh_cpu();
        sys.refresh_memory();

        let data = manager.lock().await.collect_metrics(&sys);
        // Also collect compliance for heartbeat meta
        let compliance = manager.lock().await.run_compliance_scan();
        
        let payload = serde_json::json!({
            "hostname": hostname::get()?.to_string_lossy().to_string(), // Fallback for backend
            "status": "online",
            "version": "2.0.0-rust",
            "metrics": data,
            "meta": {
                "compliance_enforcement": compliance
            }
        });

        // Add X-Tenant-Key header
        self.client.post(format!("{}/api/agents/{}/heartbeat", self.base_url, agent_id))
            .header("X-Tenant-Key", "reg_937f5bbead6643e7") 
            .json(&payload)
            .send()
            .await?;
            
        Ok(())
    }

    pub async fn get_instructions(&self) -> Result<Vec<Instruction>, Box<dyn std::error::Error>> {
        let agent_id = self.agent_id.lock().await.clone().ok_or("Not registered")?;
        
        let resp = self.client.get(format!("{}/api/agents/{}/instructions", self.base_url, agent_id))
            .header("X-Tenant-Key", "reg_937f5bbead6643e7")
            .send()
            .await?;
            
        if resp.status().is_success() {
             let instructions: Vec<Instruction> = resp.json().await?;
             Ok(instructions)
        } else {
            Ok(vec![])
        }
    }

    pub async fn send_instruction_result(&self, instruction_id: &str, result: serde_json::Value) -> Result<(), Box<dyn std::error::Error>> {
        let agent_id = self.agent_id.lock().await.clone().ok_or("Not registered")?;
        
        let payload = serde_json::json!({
            "status": result["status"], 
            "result": result
        });

        self.client.post(format!("{}/api/agents/{}/instructions/{}/result", self.base_url, agent_id, instruction_id))
            .header("X-Tenant-Key", "reg_937f5bbead6643e7")
            .json(&payload)
            .send()
            .await?;
            
        Ok(())
    }
}
