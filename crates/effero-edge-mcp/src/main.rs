//! effero-edge-mcp: a minimal MCP server template for constrained /
//! embedded devices.
//!
//! This demonstrates the pattern for exposing a device as its own MCP
//! server using Anthropic's official Rust MCP SDK (`rmcp`), so it plugs
//! into Effero's skill layer identically to a Python skill, from the
//! orchestrator's point of view. See the crate README for scope and
//! toolchain notes -- this crate was written against the confirmed
//! current `rmcp` API but could not be compiled in the sandbox this
//! scaffold was built in (see README for why).
//!
//! The two tools below simulate a GPIO pin bank in memory. Swap the
//! `EdgeDevice` internals for a real `embedded-hal` implementation (or a
//! board-specific HAL crate) to drive actual hardware -- the `#[tool]`
//! surface and MCP wiring stay the same either way.

use rmcp::{
    handler::server::wrapper::Parameters, schemars, tool, tool_router, transport::stdio,
    ServiceExt,
};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;

const PIN_COUNT: usize = 32;

#[derive(Debug, serde::Deserialize, schemars::JsonSchema)]
struct ReadPinParams {
    /// Which pin to read, in the range 0-31.
    pin: u8,
}

#[derive(Debug, serde::Deserialize, schemars::JsonSchema)]
struct SetPinParams {
    /// Which pin to set, in the range 0-31.
    pin: u8,
    /// The digital value to write.
    value: bool,
}

#[derive(Clone)]
struct EdgeDevice {
    // Simulated pin state. A real port replaces this field (and the two
    // tool bodies below) with calls into `embedded-hal`'s `OutputPin` /
    // `InputPin` traits against real hardware. Everything else --
    // the tool schema, the MCP wiring, how Effero's skill layer talks
    // to this process -- is unchanged by that swap.
    pins: Arc<[AtomicBool; PIN_COUNT]>,
}

impl Default for EdgeDevice {
    fn default() -> Self {
        Self { pins: Arc::new(std::array::from_fn(|_| AtomicBool::new(false))) }
    }
}

#[tool_router(server_handler)]
impl EdgeDevice {
    #[tool(description = "Read the current digital state of a GPIO pin.")]
    fn read_pin(&self, Parameters(ReadPinParams { pin }): Parameters<ReadPinParams>) -> String {
        match self.pins.get(pin as usize) {
            Some(state) => {
                serde_json::json!({"pin": pin, "value": state.load(Ordering::SeqCst)}).to_string()
            }
            None => serde_json::json!({
                "error": format!("pin {pin} out of range (0-{})", PIN_COUNT - 1)
            })
            .to_string(),
        }
    }

    #[tool(description = "Set the digital state of a GPIO pin.")]
    fn set_pin(&self, Parameters(SetPinParams { pin, value }): Parameters<SetPinParams>) -> String {
        match self.pins.get(pin as usize) {
            Some(state) => {
                state.store(value, Ordering::SeqCst);
                serde_json::json!({"pin": pin, "value": value}).to_string()
            }
            None => serde_json::json!({
                "error": format!("pin {pin} out of range (0-{})", PIN_COUNT - 1)
            })
            .to_string(),
        }
    }
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let service = EdgeDevice::default().serve(stdio()).await?;
    service.waiting().await?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_edge_device_default_pins() {
        let device = EdgeDevice::default();
        for pin in 0..PIN_COUNT as u8 {
            let res = device.read_pin(Parameters(ReadPinParams { pin }));
            let json: serde_json::Value = serde_json::from_str(&res).unwrap();
            assert_eq!(json["pin"], pin);
            assert_eq!(json["value"], false);
        }
    }

    #[test]
    fn test_edge_device_set_and_read_pin() {
        let device = EdgeDevice::default();

        let set_res = device.set_pin(Parameters(SetPinParams { pin: 7, value: true }));
        let set_json: serde_json::Value = serde_json::from_str(&set_res).unwrap();
        assert_eq!(set_json["pin"], 7);
        assert_eq!(set_json["value"], true);

        let read_res = device.read_pin(Parameters(ReadPinParams { pin: 7 }));
        let read_json: serde_json::Value = serde_json::from_str(&read_res).unwrap();
        assert_eq!(read_json["pin"], 7);
        assert_eq!(read_json["value"], true);

        // Verify other pin remains false
        let other_res = device.read_pin(Parameters(ReadPinParams { pin: 8 }));
        let other_json: serde_json::Value = serde_json::from_str(&other_res).unwrap();
        assert_eq!(other_json["value"], false);
    }

    #[test]
    fn test_edge_device_out_of_range_pin() {
        let device = EdgeDevice::default();

        let read_err = device.read_pin(Parameters(ReadPinParams { pin: 32 }));
        let read_json: serde_json::Value = serde_json::from_str(&read_err).unwrap();
        assert!(read_json["error"].as_str().unwrap().contains("out of range"));

        let set_err = device.set_pin(Parameters(SetPinParams { pin: 33, value: true }));
        let set_json: serde_json::Value = serde_json::from_str(&set_err).unwrap();
        assert!(set_json["error"].as_str().unwrap().contains("out of range"));
    }
}
