//! `effero-safety-kerneld`: the safety kernel daemon.
//!
//! Loads a policy file and serves guardrail decisions over a Unix domain
//! socket. See the crate README for the wire protocol and an example of
//! calling this from Python.
//!
//! Usage:
//!   effero-safety-kerneld [--policy <path>] [--socket <path>]
//!
//! Defaults: --policy policies/example.yaml --socket /tmp/effero-safety-kernel.sock
//!
//! (CLI parsing is done by hand rather than via a dependency such as
//! `clap`, to keep this crate's dependency surface -- and therefore its
//! audit surface -- as small as possible; see the crate README.)

use effero_safety_kernel::{Engine, Policy};
use std::path::PathBuf;

struct Args {
    policy: PathBuf,
    socket: PathBuf,
}

fn parse_args() -> Result<Args, String> {
    let mut policy = PathBuf::from("policies/example.yaml");
    let mut socket = PathBuf::from("/tmp/effero-safety-kernel.sock");

    let mut args = std::env::args().skip(1);
    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--policy" => {
                policy = PathBuf::from(args.next().ok_or("--policy requires a value")?);
            }
            "--socket" => {
                socket = PathBuf::from(args.next().ok_or("--socket requires a value")?);
            }
            "-h" | "--help" => {
                println!(
                    "effero-safety-kerneld [--policy <path>] [--socket <path>]\n\n\
                     Defaults: --policy policies/example.yaml --socket /tmp/effero-safety-kernel.sock"
                );
                std::process::exit(0);
            }
            other => return Err(format!("unrecognized argument: {other}")),
        }
    }

    Ok(Args { policy, socket })
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
    effero_safety_kernel::server::serve(engine, &args.socket).await
}
