use std::env;
use std::fs;
use tempfile::tempdir;

fn main() {
    let dir = tempdir().unwrap();
    env::set_var("OMNI_AGENT_BASELINE_DIR", dir.path());
    println!("Baseline dir: {:?}", env::var("OMNI_AGENT_BASELINE_DIR"));
}
