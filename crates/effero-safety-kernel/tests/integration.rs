use effero_safety_kernel::{Engine, Policy, Watchdog};
use std::time::Duration;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::net::TcpStream;

#[tokio::test]
async fn test_tcp_server_legacy_and_allow() {
    let yaml = r#"
version: 1
rules:
  - id: allow_test
    description: "Allow test skill"
    applies_to:
      - "test_skill"
    condition: "true"
    action: allow
"#;
    let policy = Policy::from_yaml_str(yaml).unwrap();
    let engine = Engine::load(policy).unwrap();

    let port = 19400 + (std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().subsec_nanos() % 1000) as u16;

    tokio::spawn(async move {
        effero_safety_kernel::server::serve(engine, "127.0.0.1", port, None).await.unwrap();
    });

    tokio::time::sleep(Duration::from_millis(150)).await;

    let mut stream = TcpStream::connect(("127.0.0.1", port)).await.unwrap();
    let (read_half, mut write_half) = stream.split();
    let mut lines = BufReader::new(read_half).lines();

    let req = serde_json::json!({
        "skill": "test_skill",
        "facts": {}
    });

    write_half.write_all(req.to_string().as_bytes()).await.unwrap();
    write_half.write_all(b"\n").await.unwrap();

    let resp_str = lines.next_line().await.unwrap().unwrap();
    let resp: serde_json::Value = serde_json::from_str(&resp_str).unwrap();

    assert_eq!(resp["decision"], "allow");
}

#[tokio::test]
async fn test_tcp_server_watchdog_heartbeat_and_lockout() {
    let yaml = r#"
version: 1
rules:
  - id: allow_robot
    description: "Allow robot actuation"
    applies_to:
      - "robotics.*"
    condition: "true"
    action: allow
"#;
    let policy = Policy::from_yaml_str(yaml).unwrap();
    let engine = Engine::load(policy).unwrap();
    let watchdog = Watchdog::new(Duration::from_millis(100));

    let port = 20400 + (std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().subsec_nanos() % 1000) as u16;

    tokio::spawn(async move {
        effero_safety_kernel::server::serve(engine, "127.0.0.1", port, Some(watchdog)).await.unwrap();
    });

    tokio::time::sleep(Duration::from_millis(150)).await;

    let mut stream = TcpStream::connect(("127.0.0.1", port)).await.unwrap();
    let (read_half, mut write_half) = stream.split();
    let mut lines = BufReader::new(read_half).lines();

    // 1. Send heartbeat
    let hb_req = serde_json::json!({"type": "heartbeat"});
    write_half.write_all(hb_req.to_string().as_bytes()).await.unwrap();
    write_half.write_all(b"\n").await.unwrap();

    let hb_resp_str = lines.next_line().await.unwrap().unwrap();
    let hb_resp: serde_json::Value = serde_json::from_str(&hb_resp_str).unwrap();
    assert_eq!(hb_resp["status"], "ok");
    assert_eq!(hb_resp["watchdog_tripped"], false);

    // 2. Evaluation before watchdog timeout passes
    let eval_req = serde_json::json!({
        "type": "evaluate",
        "skill": "robotics.arm.move",
        "facts": {}
    });
    write_half.write_all(eval_req.to_string().as_bytes()).await.unwrap();
    write_half.write_all(b"\n").await.unwrap();

    let eval_resp_str = lines.next_line().await.unwrap().unwrap();
    let eval_resp: serde_json::Value = serde_json::from_str(&eval_resp_str).unwrap();
    assert_eq!(eval_resp["decision"], "allow");

    // 3. Sleep beyond 100ms timeout so watchdog trips
    tokio::time::sleep(Duration::from_millis(150)).await;

    // 4. Evaluation after timeout must be DENIED by watchdog lockout
    write_half.write_all(eval_req.to_string().as_bytes()).await.unwrap();
    write_half.write_all(b"\n").await.unwrap();

    let lockout_resp_str = lines.next_line().await.unwrap().unwrap();
    let lockout_resp: serde_json::Value = serde_json::from_str(&lockout_resp_str).unwrap();
    assert_eq!(lockout_resp["decision"], "deny");
    assert_eq!(lockout_resp["matched_rule"], "watchdog_lockout");

    // 5. Send reset_watchdog
    let reset_req = serde_json::json!({"type": "reset_watchdog"});
    write_half.write_all(reset_req.to_string().as_bytes()).await.unwrap();
    write_half.write_all(b"\n").await.unwrap();

    let reset_resp_str = lines.next_line().await.unwrap().unwrap();
    let reset_resp: serde_json::Value = serde_json::from_str(&reset_resp_str).unwrap();
    assert_eq!(reset_resp["status"], "ok");

    // 6. Actuation allowed again
    write_half.write_all(eval_req.to_string().as_bytes()).await.unwrap();
    write_half.write_all(b"\n").await.unwrap();

    let recovered_resp_str = lines.next_line().await.unwrap().unwrap();
    let recovered_resp: serde_json::Value = serde_json::from_str(&recovered_resp_str).unwrap();
    assert_eq!(recovered_resp["decision"], "allow");
}
