
use reqwest::Client;
use serde_json::{json, Value};
use std::error::Error;
use log::{info, warn, error};

pub struct AICore {
    client: Client,
    base_url: String,
    model: String,
}

impl AICore {
    pub fn new(base_url: Option<String>, model: Option<String>) -> Self {
        AICore {
            client: Client::new(),
            base_url: base_url.unwrap_or("http://localhost:11434".to_string()),
            model: model.unwrap_or("llama3".to_string()),
        }
    }

    pub async fn ask_llm(&self, prompt: &str) -> Result<String, Box<dyn Error>> {
        let url = format!("{}/api/generate", self.base_url);
        let payload = json!({
            "model": self.model,
            "prompt": prompt,
            "stream": false
        });

        let res = self.client.post(&url)
            .json(&payload)
            .send()
            .await?;
            
        if !res.status().is_success() {
            return Err(format!("LLM API Request failed: {}", res.status()).into());
        }

        let body: Value = res.json().await?;
        let response = body["response"].as_str().unwrap_or("").to_string();
        Ok(response)
    }

    pub async fn analyze_system_health(&self, metrics: &Value) -> Result<Value, Box<dyn Error>> {
        let prompt = format!(
            "Analyze the following system metrics and compliance data. 
            Identify any critical issues and recommend specific remediation steps. 
            Respond in JSON format: {{ \"health_score\": <0-100>, \"issues\": [], \"recommendation\": \"...\" }}
            
            Data: {}", metrics
        );

        let response_text = self.ask_llm(&prompt).await?;
        
        // Simple JSON cleanup (find first { and last })
        let start = response_text.find('{').unwrap_or(0);
        let end = response_text.rfind('}').unwrap_or(response_text.len()) + 1;
        let json_str = &response_text[start..end];

        let analysis: Value = serde_json::from_str(json_str).unwrap_or(json!({
            "health_score": 0,
            "issues": ["Failed to parse LLM response"],
            "recommendation": "Manual check required"
        }));

        Ok(analysis)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[tokio::test]
    async fn test_ai_core_initialization() {
        let ai = AICore::new(Some("http://test-url".to_string()), Some("test-model".to_string()));
        assert_eq!(ai.base_url, "http://test-url");
        assert_eq!(ai.model, "test-model");
    }
}
