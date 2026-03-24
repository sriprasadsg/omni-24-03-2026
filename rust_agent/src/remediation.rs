
use std::process::Command;
use log::{info, warn, error};
use serde_json::Value;

pub struct RemediationEngine;

impl RemediationEngine {
    pub fn new() -> Self {
        RemediationEngine
    }

    pub fn execute_plan(&self, plan: &Value) -> bool {
        if let Some(steps) = plan["steps"].as_array() {
            for step in steps {
                let action = step["action"].as_str().unwrap_or("");
                let target = step["target"].as_str().unwrap_or("");
                
                info!("Executing Remediation Step: {} on {}", action, target);
                
                match action {
                    "restart_service" => self.restart_service(target),
                    "kill_process" => self.kill_process(target),
                    // "delete_file" => self.delete_file(target), // Commented out for safety in this demo
                    _ => warn!("Unknown or unsafe action: {}", action),
                }
            }
            return true;
        }
        false
    }

    fn restart_service(&self, service_name: &str) {
        // Windows specific
        let output = Command::new("powershell")
            .args(&["-Command", &format!("Restart-Service -Name '{}' -Force", service_name)])
            .output();
            
        match output {
            Ok(o) => {
                if o.status.success() {
                    info!("Successfully restarted service: {}", service_name);
                } else {
                    error!("Failed to restart service: {}", String::from_utf8_lossy(&o.stderr));
                }
            },
            Err(e) => error!("Command execution failed: {}", e),
        }
    }

    fn kill_process(&self, process_name: &str) {
         let output = Command::new("taskkill")
            .args(&["/F", "/IM", process_name])
            .output();

        match output {
            Ok(o) => {
                if o.status.success() {
                    info!("Successfully killed process: {}", process_name);
                } else {
                    error!("Failed to kill process: {}", String::from_utf8_lossy(&o.stderr));
                }
            },
            Err(e) => error!("Command execution failed: {}", e),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn test_execute_plan_parsing() {
        let engine = RemediationEngine::new();
        let plan = json!({
            "steps": [
                {"action": "echo_test", "target": "dummy"}
            ]
        });
        
        // Should return true because it parses successfully, 
        // even if action handles internally with warning
        let result = engine.execute_plan(&plan);
        assert!(result); 
    }
}
