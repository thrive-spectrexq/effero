//! A minimal local IPC server exposing [`crate::engine::Engine`] over a
//! Unix domain socket, so Effero's Python orchestrator can call into the
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
use serde::Deserialize;
use std::sync::Arc;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::net::{TcpListener, TcpStream};

#[derive(Debug, Deserialize)]
struct Request {
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

pub async fn serve(engine: Engine, host: &str, port: u16) -> anyhow::Result<()> {
    let addr = format!("{}:{}", host, port);
    let listener = TcpListener::bind(&addr).await?;
    let engine = Arc::new(engine);
    eprintln!("[effero-safety-kerneld] listening on {}", addr);

    loop {
        let (stream, _addr) = listener.accept().await?;
        let engine = Arc::clone(&engine);
        tokio::spawn(async move {
            if let Err(err) = handle_connection(stream, &engine).await {
                eprintln!("[effero-safety-kerneld] connection ended with an error: {err}");
            }
        });
    }
}

async fn handle_connection(mut stream: TcpStream, engine: &Engine) -> anyhow::Result<()> {
    let (read_half, mut write_half) = stream.split();
    let mut lines = BufReader::new(read_half).lines();

    while let Some(line) = lines.next_line().await? {
        if line.trim().is_empty() {
            continue;
        }

        let response_json = match serde_json::from_str::<Request>(&line) {
            Ok(request) => {
                let facts: Facts = request
                    .facts
                    .into_iter()
                    .map(|(k, v)| (k, v.into()))
                    .collect();
                let result: GuardrailResult = engine.evaluate(&request.skill, &facts);
                serde_json::to_string(&result)?
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
