//! `effero-safety-kerneld`: the safety kernel daemon.
//!
//! Loads a policy file and serves guardrail decisions over a TCP
//! socket. See the crate README for the wire protocol and an example of
//! calling this from Python.
//!
//! Usage:
//!   effero-safety-kerneld [--policy <path>] [--host <ip>] [--port <port>]
//!
//! Defaults: --policy policies/example.yaml --host 127.0.0.1 --port 9400
//!
//! (CLI parsing is done by hand rather than via a dependency such as
//! `clap`, to keep this crate's dependency surface -- and therefore its
//! audit surface -- as small as possible; see the crate README.)

use effero_safety_kernel::{Engine, Policy};
use std::path::PathBuf;

struct Args {
    policy: PathBuf,
    host: String,
    port: u16,
}

fn parse_args() -> Result<Args, String> {
    let mut policy = PathBuf::from("policies/example.yaml");
    let mut host = "127.0.0.1".to_string();
    let mut port = 9400;

    let mut args = std::env::args().skip(1);
    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--policy" => {
                policy = PathBuf::from(args.next().ok_or("--policy requires a value")?);
            }
            "--host" => {
                host = args.next().ok_or("--host requires a value")?;
            }
            "--port" => {
                let p = args.next().ok_or("--port requires a value")?;
                port = p.parse().map_err(|_| format!("invalid port: {}", p))?;
            }
            "-h" | "--help" => {
                println!(
                    "effero-safety-kerneld [--policy <path>] [--host <ip>] [--port <port>]\n\n\
                     Defaults: --policy policies/example.yaml --host 127.0.0.1 --port 9400"
                );
                std::process::exit(0);
            }
            other => return Err(format!("unrecognized argument: {other}")),
        }
    }

    Ok(Args { policy, host, port })
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let args = parse_args().map_err(|e| anyhow::anyhow!(e))?;

    let policy = Policy::from_yaml_file(&args.policy)?;
    eprintln!(
        "[effero-safety-kerneld] loaded {} rule(s) from {}",
        policy.rules.len(),
        args.policy.display()
    );

    let engine = Engine::load(policy)?;
    effero_safety_kernel::server::serve(engine, &args.host, args.port).await
}
