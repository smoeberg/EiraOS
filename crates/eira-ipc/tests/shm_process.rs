use eira_ipc::shm::{SharedMemoryDescriptor, SharedMemoryReader, SharedMemoryWriter};
use std::process::Command;
use std::time::{SystemTime, UNIX_EPOCH};

const DESCRIPTOR_ENV: &str = "EIRA_TEST_SHM_DESCRIPTOR";

fn unique_name() -> String {
    format!(
        "/eira_shm_process_{}_{}",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("system clock is after UNIX epoch")
            .as_nanos()
    )
}

#[test]
fn child_process_reads_published_segment() {
    // This test is also used as a subprocess entry point. Ordinary test-suite
    // execution has no descriptor and exits; the parent supplies it explicitly.
    let Ok(encoded) = std::env::var(DESCRIPTOR_ENV) else {
        return;
    };
    let descriptor: SharedMemoryDescriptor =
        serde_json::from_str(&encoded).expect("valid shared-memory descriptor");
    let reader = SharedMemoryReader::open(&descriptor).expect("open published segment");
    assert_eq!(reader.payload(), b"producer-to-consumer payload");
}

#[test]
fn producer_and_consumer_exchange_payload_across_processes() {
    let name = unique_name();
    let mut writer = SharedMemoryWriter::create(&name, 256).expect("create segment");
    let descriptor = writer
        .publish(b"producer-to-consumer payload")
        .expect("publish payload");
    let encoded = serde_json::to_string(&descriptor).expect("serialize descriptor");

    let status = Command::new(std::env::current_exe().expect("test executable path"))
        .arg("--exact")
        .arg("child_process_reads_published_segment")
        .arg("--nocapture")
        .env(DESCRIPTOR_ENV, encoded)
        .status()
        .expect("spawn consumer process");

    assert!(status.success(), "consumer process failed: {status}");
    // Keep writer alive until the consumer has completed; Drop unlinks afterward.
}
