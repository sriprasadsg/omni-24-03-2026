use std::time::Duration;
use tokio::time::sleep;
use log::{info, error, warn};
use std::sync::Arc;
use tokio::sync::Mutex;

mod ai_core;
mod remediation;
mod remote_access;

use rust_agent::api::BackendClient;
use rust_agent::capabilities::CapabilityManager;
use ai_core::AICore;
use remediation::RemediationEngine;
use remote_access::RemoteAccess;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    env_logger::init_from_env(env_logger::Env::default().default_filter_or("info"));
    
    info!("Starting Rust Omni-Agent...");

    let client = Arc::new(BackendClient::new("http://localhost:5000".to_string()));
    let capability_manager = Arc::new(Mutex::new(CapabilityManager::new()));
    
    // Initialize Advanced Modules
    let ai_core = Arc::new(AICore::new(None, None));
    let remediation = Arc::new(RemediationEngine::new());
    
    let mut registered_agent_id = String::new();

    // Registration Loop
    loop {
        info!("Attempting to register with backend...");
        match client.register(capability_manager.clone()).await {
            Ok(config) => {
                info!("Registration successful! Agent ID: {}", config.agent_id);
                registered_agent_id = config.agent_id.clone();
                break;
            }
            Err(e) => {
                error!("Registration failed: {}. Retrying in 5s...", e);
                sleep(Duration::from_secs(5)).await;
            }
        }
    }
    
    // Start Remote Access Listener (Background Task)
    let ra_agent_id = registered_agent_id.clone();
    tokio::spawn(async move {
        let remote = RemoteAccess::new("ws://localhost:5000".to_string(), ra_agent_id);
        loop {
            // Keep trying to connect/reconnect
            remote.start_session().await;
            sleep(Duration::from_secs(5)).await;
        }
    });

    // Main Loop
    loop {
        // Heartbeat
        if let Err(e) = client.send_heartbeat(capability_manager.clone()).await {
            error!("Heartbeat failed: {}", e);
        }

        // Poll Instructions
        match client.get_instructions().await {
            Ok(instructions) => {
                for instruction in instructions {
                    info!("Received instruction: {}", instruction.id);

                    // Standard Execution
                    let result = capability_manager.lock().await.execute_instruction(&instruction).await;
                    if let Err(e) = client.send_instruction_result(&instruction.id, result).await {
                        error!("Failed to send instruction result: {}", e);
                    }
                }
            }
            Err(e) => {
                warn!("Failed to poll instructions: {}", e);
            }
        }

        sleep(Duration::from_secs(5)).await;
    }
}
