//! Deadman Watchdog for effero-safety-kernel.
//!
//! Inspired by the comma.ai panda safety model: high-level intelligence
//! (the Python agent / planner) must regularly emit heartbeats. If the
//! agent loop hangs, crashes, or stalls (e.g. during an unhandled LLM call),
//! the watchdog timer trips and locks out all physical actuation commands.

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

#[derive(Debug, Clone, serde::Serialize)]
pub struct WatchdogStatus {
    pub enabled: bool,
    pub tripped: bool,
    pub timeout_ms: u64,
    pub elapsed_since_heartbeat_ms: u64,
}

#[derive(Clone)]
pub struct Watchdog {
    timeout: Duration,
    last_heartbeat: Arc<Mutex<Instant>>,
    tripped: Arc<AtomicBool>,
    enabled: Arc<AtomicBool>,
}

impl Watchdog {
    pub fn new(timeout: Duration) -> Self {
        Self {
            timeout,
            last_heartbeat: Arc::new(Mutex::new(Instant::now())),
            tripped: Arc::new(AtomicBool::new(false)),
            enabled: Arc::new(AtomicBool::new(true)),
        }
    }

    pub fn heartbeat(&self) {
        if let Ok(mut lock) = self.last_heartbeat.lock() {
            *lock = Instant::now();
        }
        self.tripped.store(false, Ordering::SeqCst);
    }

    pub fn is_tripped(&self) -> bool {
        if !self.enabled.load(Ordering::Relaxed) {
            return false;
        }
        if self.tripped.load(Ordering::Relaxed) {
            return true;
        }
        if let Ok(lock) = self.last_heartbeat.lock() {
            if lock.elapsed() > self.timeout {
                self.tripped.store(true, Ordering::SeqCst);
                return true;
            }
        }
        false
    }

    pub fn reset(&self) {
        self.heartbeat();
    }

    pub fn set_enabled(&self, val: bool) {
        self.enabled.store(val, Ordering::SeqCst);
        if val {
            self.heartbeat();
        }
    }

    pub fn status(&self) -> WatchdogStatus {
        let elapsed_ms = if let Ok(lock) = self.last_heartbeat.lock() {
            lock.elapsed().as_millis() as u64
        } else {
            0
        };

        WatchdogStatus {
            enabled: self.enabled.load(Ordering::Relaxed),
            tripped: self.is_tripped(),
            timeout_ms: self.timeout.as_millis() as u64,
            elapsed_since_heartbeat_ms: elapsed_ms,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_watchdog_normal_heartbeat() {
        let wd = Watchdog::new(Duration::from_millis(50));
        assert!(!wd.is_tripped());
        wd.heartbeat();
        assert!(!wd.is_tripped());
    }

    #[test]
    fn test_watchdog_trips_on_timeout() {
        let wd = Watchdog::new(Duration::from_millis(10));
        std::thread::sleep(Duration::from_millis(25));
        assert!(wd.is_tripped());

        // Heartbeat resets the trip
        wd.heartbeat();
        assert!(!wd.is_tripped());
    }

    #[test]
    fn test_watchdog_disabled() {
        let wd = Watchdog::new(Duration::from_millis(10));
        wd.set_enabled(false);
        std::thread::sleep(Duration::from_millis(25));
        assert!(!wd.is_tripped());
    }
}
