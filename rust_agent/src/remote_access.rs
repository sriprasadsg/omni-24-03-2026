
use tokio_tungstenite::{connect_async, tungstenite::protocol::Message};
use futures_util::{StreamExt, SinkExt};
use url::Url;
use std::process::{Command, Stdio};
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use std::sync::Arc;
use tokio::sync::Mutex;
use log::{info, error, debug};

pub struct RemoteAccess {
    server_url: String,
    agent_id: String,
}

impl RemoteAccess {
    pub fn new(server_url: String, agent_id: String) -> Self {
        RemoteAccess {
            server_url,
            agent_id,
        }
    }

    pub async fn start_session(&self) {
        let url_str = format!("{}/api/ws/remote/{}", self.server_url, self.agent_id);
        let url = Url::parse(&url_str).expect("Invalid WebSocket URL");

        info!("Connecting to Remote Shell at {}", url);

        match connect_async(url).await {
            Ok((ws_stream, _)) => {
                info!("WebSocket Connected!");
                let (mut write, mut read) = ws_stream.split();

                // Spawn a shell process
                let mut child = Command::new("powershell")
                    .stdin(Stdio::piped())
                    .stdout(Stdio::piped())
                    .stderr(Stdio::piped())
                    .spawn()
                    .expect("Failed to spawn shell");

                // We need to handle async IO with the child process.
                // NOTE: This is a simplified "Mock" shell for the implementation plan since 
                // full async pipe handling in Rust requires `tokio::process::Command` 
                // and careful stream bridging. 
                
                // For this implementation, we will just echo back for now 
                // to demonstrate the connectivity without complex pipe wiring 
                // compatible with the synchronous Command used above or needing big refactors.
                
                // Real implementation would use `tokio::process::Command`.
                
                while let Some(msg) = read.next().await {
                    match msg {
                        Ok(Message::Text(txt)) => {
                            info!("Received command: {}", txt);
                            // Execute simple command synchronously for demo
                            let output = Command::new("powershell")
                                .args(&["-Command", &txt])
                                .output();
                                
                            let response = match output {
                                Ok(o) => {
                                    format!("{}{}", 
                                        String::from_utf8_lossy(&o.stdout),
                                        String::from_utf8_lossy(&o.stderr)
                                    )
                                },
                                Err(e) => format!("Execution failed: {}", e)
                            };
                            
                            if let Err(e) = write.send(Message::Text(response)).await {
                                error!("Failed to send response: {}", e);
                                break;
                            }
                        },
                        Ok(Message::Close(_)) => {
                            info!("Session closed by server");
                            break;
                        },
                        Err(e) => {
                             error!("WebSocket error: {}", e);
                             break;
                        },
                        _ => {}
                    }
                }
            },
            Err(e) => {
                error!("Failed to connect to WebSocket: {}", e);
            }
        }
    }
}
