use effero_safety_kernel::{Engine, Policy, Rule, Action};
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::net::TcpStream;
use std::time::Duration;

#[tokio::test]
async fn test_tcp_server() {
    let rule = Rule {
        name: "allow_test".to_string(),
        description: None,
        skill: "test_skill".to_string(),
        conditions: vec![],
        action: Action::Allow,
    };
    
    let policy = Policy { rules: vec![rule] };
    let engine = Engine::load(policy).unwrap();
    
    let port = 19400 + (std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().subsec_nanos() % 1000) as u16;
    
    tokio::spawn(async move {
        effero_safety_kernel::server::serve(engine, "127.0.0.1", port).await.unwrap();
    });
    
    tokio::time::sleep(Duration::from_millis(100)).await;
    
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
