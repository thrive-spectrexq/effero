//! effero-safety-kernel: the runtime guardrail engine for Effero.
//!
//! This crate is deliberately independent of the LLM and of Effero's
//! Python core: it loads a declarative policy file, matches proposed
//! skill invocations against it, and returns a decision (allow / require
//! approval / deny / limit). It's designed to run as its own local
//! process (see `server`) so that no prompt-injection path inside the
//! Python orchestrator can silently bypass it.
//!
//! See the crate README for the current scope and known simplifications
//! relative to the policy shape sketched in the top-level project README.

pub mod condition;
pub mod engine;
pub mod policy;
pub mod server;

pub use condition::{Fact, Facts};
pub use engine::{Decision, Engine, GuardrailResult};
pub use policy::{Action, Policy, Rule};
