//! Declarative policy schema.
//!
//! This mirrors the shape used by the Python-side example policy at
//! `src/effero/safety/policies/example.yaml`, with one deliberate
//! simplification for this first skeleton: conditions are evaluated
//! against a **flat** context of named facts (e.g. `nearest_person_distance_m`)
//! rather than dotted paths (`time.hour`). Unifying the two policy grammars
//! is tracked as a follow-up -- see the crate README.

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct Policy {
    pub version: u32,
    pub rules: Vec<Rule>,
    #[serde(default)]
    pub defaults: Defaults,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct Rule {
    pub id: String,
    pub description: String,
    /// Glob patterns matched against a skill name, e.g. `"iot.locks.*"`.
    pub applies_to: Vec<String>,
    /// A boolean expression evaluated against the request's facts, e.g.
    /// `"nearest_person_distance_m < 1.0"`. Use `"true"` for a rule that
    /// always applies once `applies_to` matches.
    pub condition: String,
    pub action: Action,
    /// Free-form extra parameters for `Action::Limit` (e.g. `max_speed_mps`).
    #[serde(default)]
    pub limit: Option<HashMap<String, f64>>,
}

#[derive(Debug, Clone, Copy, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Action {
    Allow,
    RequireApproval,
    Deny,
    Limit,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct Defaults {
    #[serde(default = "default_unknown_skill_action")]
    pub unknown_skill_action: Action,
}

impl Default for Defaults {
    fn default() -> Self {
        Self {
            unknown_skill_action: default_unknown_skill_action(),
        }
    }
}

fn default_unknown_skill_action() -> Action {
    // Fail safe: anything not explicitly covered by a rule requires a
    // human in the loop rather than being silently allowed.
    Action::RequireApproval
}

impl Policy {
    pub fn from_yaml_str(s: &str) -> anyhow::Result<Self> {
        let policy: Policy = serde_yaml::from_str(s)?;
        Ok(policy)
    }

    pub fn from_yaml_file(path: &std::path::Path) -> anyhow::Result<Self> {
        let contents = std::fs::read_to_string(path)?;
        Self::from_yaml_str(&contents)
    }
}
