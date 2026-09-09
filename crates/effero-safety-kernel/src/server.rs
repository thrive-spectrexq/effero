//! A minimal local IPC server exposing [`crate::engine::Engine`] over a
//! TCP socket (default 127.0.0.1:9400), so Effero's Python orchestrator can call into the
//! guardrail engine as a separate, independently-running process rather
//! than an in-process Python module.
//!
//! Protocol: newline-delimited JSON. One request per line in, one
//! response per line out. This is intentionally simple (not gRPC/HTTP)
//! to keep the kernel's dependency surface small and auditable -- see
//! the crate README for the rationale and for swapping in a richer
//! transport later if needed.

use crate::condition::{Fact, Facts};
use crate::engine::{Engine, GuardrailResult};
use crate::watchdog::Watchdog;
use serde::Deserialize;
use std::sync::Arc;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::net::{TcpListener, TcpStream};

#[derive(Debug, Deserialize)]
#[serde(untagged)]
enum IncomingMessage {
    Typed(TypedCommand),
    Legacy(LegacyRequest),
}

#[derive(Debug, Deserialize)]
#[serde(tag = "type")]
enum TypedCommand {
    #[serde(rename = "heartbeat")]
    Heartbeat,
    #[serde(rename = "status")]
    Status,
    #[serde(rename = "reset_watchdog")]
    ResetWatchdog,
    #[serde(rename = "evaluate")]
    Evaluate {
        skill: String,
        #[serde(default)]
        facts: std::collections::HashMap<String, RequestFact>,
    },
}

#[derive(Debug, Deserialize)]
struct LegacyRequest {
    skill: String,
    #[serde(default)]
    facts: std::collections::HashMap<String, RequestFact>,
}

#[derive(Debug, Deserialize)]
#[serde(untagged)]
enum RequestFact {
    Number(f64),
    Bool(bool),
}

impl From<RequestFact> for Fact {
    fn from(value: RequestFact) -> Self {
        match value {
            RequestFact::Number(n) => Fact::Number(n),
            RequestFact::Bool(b) => Fact::Bool(b),
        }
    }
}

pub async fn serve(
    engine: Engine,
    host: &str,
    port: u16,
    watchdog: Option<Watchdog>,
) -> anyhow::Result<()> {
    let addr = format!("{}:{}", host, port);
    let listener = TcpListener::bind(&addr).await?;
    let engine = Arc::new(engine);
    let watchdog = watchdog.map(Arc::new);
    eprintln!("[effero-safety-kerneld] listening on {}", addr);

    loop {
        let (stream, _addr) = listener.accept().await?;
        let engine = Arc::clone(&engine);
        let watchdog = watchdog.clone();
        tokio::spawn(async move {
            if let Err(err) = handle_connection(stream, &engine, watchdog.as_deref()).await {
                eprintln!("[effero-safety-kerneld] connection ended with an error: {err}");
            }
        });
    }
}

async fn handle_connection(
    mut stream: TcpStream,
    engine: &Engine,
    watchdog: Option<&Watchdog>,
) -> anyhow::Result<()> {
    let (read_half, mut write_half) = stream.split();
    let mut lines = BufReader::new(read_half).lines();

    while let Some(line) = lines.next_line().await? {
        if line.trim().is_empty() {
            continue;
        }

        let response_json = match serde_json::from_str::<IncomingMessage>(&line) {
            Ok(IncomingMessage::Typed(TypedCommand::Heartbeat)) => {
                if let Some(wd) = watchdog {
                    wd.heartbeat();
                }
                serde_json::json!({
                    "status": "ok",
                    "type": "heartbeat_ack",
                    "watchdog_tripped": watchdog.map(|w| w.is_tripped()).unwrap_or(false)
                })
                .to_string()
            }
            Ok(IncomingMessage::Typed(TypedCommand::Status)) => {
                serde_json::json!({
                    "status": "ok",
                    "watchdog": watchdog.map(|w| w.status())
                })
                .to_string()
            }
            Ok(IncomingMessage::Typed(TypedCommand::ResetWatchdog)) => {
                if let Some(wd) = watchdog {
                    wd.reset();
                }
                serde_json::json!({
                    "status": "ok",
                    "type": "reset_ack",
                    "watchdog_tripped": false
                })
                .to_string()
            }
            Ok(IncomingMessage::Typed(TypedCommand::Evaluate { skill, facts })) => {
                evaluate_action(engine, watchdog, &skill, facts)?
            }
            Ok(IncomingMessage::Legacy(req)) => {
                evaluate_action(engine, watchdog, &req.skill, req.facts)?
            }
            Err(err) => {
                serde_json::json!({
                    "decision": "require_approval",
                    "matched_rule": null,
                    "reason": format!("malformed request, failing safe: {err}")
                })
                .to_string()
            }
        };

        write_half.write_all(response_json.as_bytes()).await?;
        write_half.write_all(b"\n").await?;
    }

    Ok(())
}

fn evaluate_action(
    engine: &Engine,
    watchdog: Option<&Watchdog>,
    skill: &str,
    raw_facts: std::collections::HashMap<String, RequestFact>,
) -> anyhow::Result<String> {
    // If watchdog is enabled and tripped, lockout actuation
    if let Some(wd) = watchdog {
        if wd.is_tripped() {
            let res = serde_json::json!({
                "decision": "deny",
                "matched_rule": "watchdog_lockout",
                "reason": "Safety watchdog expired: heartbeat lost from agent supervisor. Actuation locked out."
            });
            return Ok(res.to_string());
        }
    }

    let facts: Facts = raw_facts.into_iter().map(|(k, v)| (k, v.into())).collect();
    let result: GuardrailResult = engine.evaluate(skill, &facts);
    Ok(serde_json::to_string(&result)?)
}
