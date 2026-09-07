//! The core decision engine: given a skill name and a set of facts about
//! the current situation, decide whether the action may proceed.
//!
//! This is the piece meant to sit between Effero's Python skill layer and
//! the Device Abstraction Layer as an independent, LLM-free check (see
//! the "Safety & Governance" section of the top-level README).

use crate::condition::{evaluate, Facts};
use crate::policy::{Action, Policy, Rule};
use globset::{Glob, GlobSet, GlobSetBuilder};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Decision {
    Allow,
    RequireApproval,
    Deny,
    /// Allowed, but the caller must additionally honor the matched
    /// rule's `limit` values (e.g. a max speed).
    Limit,
}

impl From<Action> for Decision {
    fn from(action: Action) -> Self {
        match action {
            Action::Allow => Decision::Allow,
            Action::RequireApproval => Decision::RequireApproval,
            Action::Deny => Decision::Deny,
            Action::Limit => Decision::Limit,
        }
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct GuardrailResult {
    pub decision: Decision,
    pub matched_rule: Option<String>,
    pub reason: String,
}

struct CompiledRule {
    rule: Rule,
    globset: GlobSet,
}

pub struct Engine {
    policy: Policy,
    compiled: Vec<CompiledRule>,
}

impl Engine {
    pub fn load(policy: Policy) -> anyhow::Result<Self> {
        let mut compiled = Vec::with_capacity(policy.rules.len());
        for rule in &policy.rules {
            let mut builder = GlobSetBuilder::new();
            for pattern in &rule.applies_to {
                builder.add(Glob::new(pattern)?);
            }
            compiled.push(CompiledRule {
                rule: rule.clone(),
                globset: builder.build()?,
            });
        }
        Ok(Self { policy, compiled })
    }

    /// Evaluate every rule against `skill_name` and `facts`, in policy
    /// order, and return the first match. If nothing matches, fall back
    /// to `policy.defaults.unknown_skill_action`.
    pub fn evaluate(&self, skill_name: &str, facts: &Facts) -> GuardrailResult {
        for compiled in &self.compiled {
            if !compiled.globset.is_match(skill_name) {
                continue;
            }
            if evaluate(&compiled.rule.condition, facts) {
                return GuardrailResult {
                    decision: compiled.rule.action.into(),
                    matched_rule: Some(compiled.rule.id.clone()),
                    reason: compiled.rule.description.clone(),
                };
            }
        }

        GuardrailResult {
            decision: self.policy.defaults.unknown_skill_action.into(),
            matched_rule: None,
            reason: format!(
                "no policy rule matched skill '{skill_name}' under the current facts; \
                 falling back to the configured default action"
            ),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::condition::Fact;
    use crate::policy::Policy;

    fn test_policy() -> Policy {
        let yaml = r#"
version: 1
rules:
  - id: no-exterior-unlock-at-night
    description: "Never unlock an exterior door at night without approval."
    applies_to: ["iot.locks.*"]
    condition: "time_hour >= 23 || time_hour < 6"
    action: require_approval
  - id: always-allow-read-only-sensors
    description: "Sensor reads never touch the physical world."
    applies_to: ["iot.sensors.read_*"]
    condition: "true"
    action: allow
defaults:
  unknown_skill_action: require_approval
"#;
        Policy::from_yaml_str(yaml).unwrap()
    }

    #[test]
    fn matches_rule_and_condition() {
        let engine = Engine::load(test_policy()).unwrap();
        let mut facts = Facts::new();
        facts.insert("time_hour".to_string(), Fact::Number(23.5));

        let result = engine.evaluate("iot.locks.front_door", &facts);
        assert_eq!(result.decision, Decision::RequireApproval);
        assert_eq!(result.matched_rule.as_deref(), Some("no-exterior-unlock-at-night"));
    }

    #[test]
    fn glob_matches_correctly() {
        let engine = Engine::load(test_policy()).unwrap();
        let result = engine.evaluate("iot.sensors.read_temperature", &Facts::new());
        assert_eq!(result.decision, Decision::Allow);
    }

    #[test]
    fn unmatched_skill_falls_back_to_default() {
        let engine = Engine::load(test_policy()).unwrap();
        let result = engine.evaluate("robotics.arm_pick_place", &Facts::new());
        assert_eq!(result.decision, Decision::RequireApproval);
        assert!(result.matched_rule.is_none());
    }

    #[test]
    fn condition_false_falls_through_to_default() {
        let engine = Engine::load(test_policy()).unwrap();
        let mut facts = Facts::new();
        facts.insert("time_hour".to_string(), Fact::Number(14.0)); // daytime

        let result = engine.evaluate("iot.locks.front_door", &facts);
        // The night-time rule's condition is false, and no other rule
        // matches "iot.locks.*", so we fall back to the default.
        assert_eq!(result.decision, Decision::RequireApproval);
        assert!(result.matched_rule.is_none());
    }
}
