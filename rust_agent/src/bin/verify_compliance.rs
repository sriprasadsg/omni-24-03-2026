use rust_agent::capabilities::CapabilityManager;
use serde_json::to_string_pretty;
use std::fs;

fn main() {
    let cm = CapabilityManager::new();
    println!("Running Compliance Scan (Test Mode)...");
    
    // Simulate Instruction Execution
    let result = cm.run_compliance_scan();
    
    let json_output = to_string_pretty(&result).unwrap();
    println!("{}", json_output);

    // Save to file for HTML consumption
    fs::write("compliance_report.json", json_output).expect("Unable to write file");
    println!("Saved report to compliance_report.json");
}
