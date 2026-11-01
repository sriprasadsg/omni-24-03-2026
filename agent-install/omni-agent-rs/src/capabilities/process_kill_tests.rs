//! `plan_kill`, `survivors` and `kill_body` on scripted process lists, and the dispatch arm's
//! refusals. Nothing here signals a process: the only `kill_by_exe` call names a program that
//! is not running.

use super::*;
use crate::capabilities::quarantine::RunningProcess;
use serde_json::json;

const ORIGINAL: &str = "/tmp/evil/evil.bin";
const STORED: &str = "/var/lib/omni-agent/quarantine/task-1";
const T: u64 = 1_761_900_000;
const SELF_PID: u32 = 31_337;

fn proc(pid: u32, start: u64, exe: Option<&str>) -> RunningProcess {
    RunningProcess { pid, name: "evil.bin".into(), start_time: start, exe: exe.map(str::to_string) }
}

fn request(moved: Option<&str>, listed: &[(u32, u64)]) -> KillRequest {
    KillRequest {
        expected_exe: ORIGINAL.into(),
        moved_exe: moved.map(str::to_string),
        listed: listed.iter().map(|(pid, start_time)| ListedProcess { pid: *pid, start_time: *start_time }).collect(),
    }
}

fn plan(list: &[RunningProcess], req: &KillRequest) -> KillPlan {
    plan_kill(list, req, false, SELF_PID)
}

fn pids(list: &[RunningProcess]) -> Vec<u32> {
    list.iter().map(|p| p.pid).collect()
}

fn contract() -> Option<Value> {
    let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../shared/agent-response-contract.json");
    Some(serde_json::from_str(&std::fs::read_to_string(path).ok()?).unwrap())
}

// ── after a move ────────────────────────────────────────────────────────────

#[test]
fn a_listed_pid_that_reports_the_stored_path_is_in_kill() {
    // Linux, same volume: the running image follows the rename and reports its moved path.
    let p = plan(&[proc(100, T, Some(STORED))], &request(Some(STORED), &[(100, T)]));
    assert_eq!(pids(&p.kill), [100]);
    assert!(p.unconfirmed.is_empty());
}

#[test]
fn a_listed_pid_that_still_reports_the_original_path_is_in_kill() {
    // Windows after a rename, and Linux after a copy across volumes.
    let p = plan(&[proc(100, T, Some(ORIGINAL))], &request(Some(STORED), &[(100, T)]));
    assert_eq!(pids(&p.kill), [100]);
}

#[test]
fn an_unlisted_process_on_the_stored_path_is_in_kill() {
    let p = plan(&[proc(200, T + 50, Some(STORED))], &request(Some(STORED), &[(100, T)]));
    assert_eq!(pids(&p.kill), [200]);
}

#[test]
fn an_unlisted_process_on_the_original_path_is_left_alone_after_a_move() {
    // Whatever stands at that path now is a new file.
    let p = plan(&[proc(200, T + 50, Some(ORIGINAL))], &request(Some(STORED), &[(100, T)]));
    assert_eq!(p, KillPlan::default());
}

#[test]
fn a_reused_pid_with_an_unrelated_program_is_never_signalled_and_counts_as_gone() {
    let list = [proc(100, T + 9_000, Some("/usr/bin/vim"))];
    let p = plan(&list, &request(Some(STORED), &[(100, T)]));
    assert_eq!(p, KillPlan::default());
    // Nothing planned: the row says the process is gone, and that is true of the listed one.
    assert_eq!(kill_body(&p, &survivors(&p, &list))["outcome"], "process_gone");
}

#[test]
fn a_reused_pid_that_reports_the_original_path_is_unconfirmed_not_killed() {
    // A replaced file and a clock step look the same: neither killed nor called gone.
    let p = plan(&[proc(100, T + 9_000, Some(ORIGINAL))], &request(Some(STORED), &[(100, T)]));
    assert!(p.kill.is_empty());
    assert_eq!(pids(&p.unconfirmed), [100]);
}

#[test]
fn a_reused_pid_with_an_unreadable_exe_is_unconfirmed() {
    let p = plan(&[proc(100, T + 9_000, None)], &request(Some(STORED), &[(100, T)]));
    assert!(p.kill.is_empty());
    assert_eq!(pids(&p.unconfirmed), [100]);
}

#[test]
fn a_live_listed_process_that_no_longer_shows_the_image_is_unconfirmed() {
    for exe in [Some("/usr/bin/vim"), None] {
        let p = plan(&[proc(100, T, exe)], &request(Some(STORED), &[(100, T)]));
        assert!(p.kill.is_empty(), "{exe:?}");
        assert_eq!(pids(&p.unconfirmed), [100], "{exe:?}");
    }
}

#[test]
fn a_held_pid_with_an_unconfirmable_exe_never_gives_verify_ok_true() {
    let list = [proc(100, T, None)];
    let p = plan(&list, &request(Some(STORED), &[(100, T)]));
    let body = kill_body(&p, &survivors(&p, &list));
    assert_eq!(body["verify"]["ok"], false);
    assert_ne!(body["outcome"], "process_gone");
    assert_eq!(body["still_running"][0]["pid"], 100);
}

#[test]
fn start_times_two_seconds_apart_are_one_process_and_three_are_not() {
    assert!(same_process(5, 1_000, 5, 1_002) && same_process(5, 1_002, 5, 1_000));
    assert!(!same_process(5, 1_000, 5, 1_003));
    assert!(!same_process(5, 1_000, 6, 1_000));
    let at_edge = plan(&[proc(100, T + 2, Some(ORIGINAL))], &request(Some(STORED), &[(100, T)]));
    assert_eq!(pids(&at_edge.kill), [100]);
    let past_edge = plan(&[proc(100, T + 3, Some(ORIGINAL))], &request(Some(STORED), &[(100, T)]));
    assert!(past_edge.kill.is_empty());
}

// ── nothing moved ───────────────────────────────────────────────────────────

#[test]
fn with_nothing_moved_every_process_running_the_image_is_killed_listed_or_not() {
    let list = [proc(100, T, Some(ORIGINAL)), proc(200, T + 77, Some(ORIGINAL)), proc(300, T, Some("/bin/sh"))];
    let p = plan(&list, &request(None, &[(100, T)]));
    assert_eq!(pids(&p.kill), [100, 200]);
    assert!(p.unconfirmed.is_empty());
}

#[test]
fn with_nothing_moved_windows_style_compares_the_image_without_case() {
    let req = KillRequest { expected_exe: "C:\\Temp\\Evil.exe".into(), moved_exe: None, listed: Vec::new() };
    let list = [proc(100, T, Some("c:/temp/EVIL.EXE")), proc(200, T, Some("\\\\?\\C:\\Temp\\evil.exe"))];
    assert_eq!(pids(&plan_kill(&list, &req, true, SELF_PID).kill), [100, 200]);
    assert!(plan_kill(&list, &req, false, SELF_PID).kill.is_empty());
}

#[test]
fn with_nothing_moved_the_reuse_rule_is_unchanged() {
    let list = [proc(100, T, Some("/bin/sh")), proc(101, T + 9_000, Some("/bin/sh"))];
    let p = plan(&list, &request(None, &[(100, T), (101, T)]));
    assert!(p.kill.is_empty());
    assert_eq!(pids(&p.unconfirmed), [100], "same start, another program: unconfirmed; reused pid: alone");
}

#[test]
fn the_agent_itself_and_critical_names_are_unconfirmed_never_dropped() {
    let mut critical = proc(400, T, Some(ORIGINAL));
    critical.name = "SYSTEMD".into();
    let list = [proc(SELF_PID, T, Some(ORIGINAL)), critical, proc(1, T, Some(ORIGINAL)), proc(500, T, Some(ORIGINAL))];
    let p = plan(&list, &request(None, &[]));
    assert_eq!(pids(&p.kill), [500]);
    assert_eq!(pids(&p.unconfirmed), [SELF_PID, 400, 1]);
    let body = kill_body(&p, &[]);
    assert_eq!(body["verify"]["ok"], false, "an excluded process keeps the answer from saying gone");
}

// ── the answer ──────────────────────────────────────────────────────────────

fn evil() -> RunningProcess {
    RunningProcess { pid: 4242, name: "evil.exe".into(), start_time: 1_761_900_000, exe: Some(ORIGINAL.into()) }
}

#[test]
fn the_four_bodies_equal_the_contract_examples() {
    let Some(c) = contract() else { return };
    let one = KillPlan { kill: vec![evil()], unconfirmed: vec![] };
    assert_eq!(kill_body(&KillPlan::default(), &[]), c["examples"]["kill_gone"]);
    assert_eq!(kill_body(&one, &[]), c["examples"]["kill_done"]);
    assert_eq!(kill_body(&one, &[evil()]), c["examples"]["kill_survived"]);
    let unconfirmed = KillPlan { kill: vec![], unconfirmed: vec![evil()] };
    assert_eq!(kill_body(&unconfirmed, &[evil()]), c["examples"]["kill_refused"]);
}

#[test]
fn the_body_is_decided_in_the_stated_order() {
    let a = evil();
    let b = RunningProcess { pid: 4243, ..evil() };
    // Something signalled and something unconfirmed: survived, naming both once.
    let mixed = KillPlan { kill: vec![a.clone()], unconfirmed: vec![b.clone()] };
    let body = kill_body(&mixed, &[]);
    assert_eq!((body["outcome"].as_str(), body["verify"]["ok"].clone()), (Some("killed"), json!(false)));
    assert_eq!(body["still_running"].as_array().unwrap().len(), 1);
    let body = kill_body(&mixed, &[a.clone()]);
    assert_eq!(body["still_running"].as_array().unwrap().len(), 2);
    // Nothing signalled and something unconfirmed: refused, even if it has since left.
    let refused = kill_body(&KillPlan { kill: vec![], unconfirmed: vec![b] }, &[]);
    assert_eq!(refused["outcome"], "refused");
    assert_eq!(refused["status"], "error");
}

#[test]
fn survivors_match_by_pid_and_start_time() {
    let p = KillPlan { kill: vec![evil()], unconfirmed: vec![] };
    assert_eq!(survivors(&p, &[evil()]).len(), 1);
    assert!(survivors(&p, &[]).is_empty(), "a process that left is not a survivor");
    let reused = RunningProcess { start_time: 1_761_990_000, ..evil() };
    assert!(survivors(&p, &[reused]).is_empty(), "a pid reused during the wait is not a survivor");
    let near = RunningProcess { start_time: 1_761_900_001, ..evil() };
    assert_eq!(survivors(&p, &[near]).len(), 1);
}

// ── input checks ────────────────────────────────────────────────────────────

#[test]
fn bad_requests_are_refused_before_anything_is_read() {
    let ok = json!({"expected_exe": ORIGINAL, "processes": [{"pid": 100, "start_time": T}]});
    assert!(parse_request(&ok).is_ok());
    let too_many: Vec<Value> = (0..=STILL_RUNNING_CAP).map(|i| json!({"pid": 100 + i, "start_time": T})).collect();
    let cases = [
        json!({"processes": [{"pid": 100, "start_time": T}]}),
        json!({"expected_exe": "", "processes": [{"pid": 100, "start_time": T}]}),
        json!({"expected_exe": ORIGINAL}),
        json!({"expected_exe": ORIGINAL, "processes": []}),
        json!({"expected_exe": ORIGINAL, "processes": "100"}),
        json!({"expected_exe": ORIGINAL, "processes": [{"pid": 0, "start_time": T}]}),
        json!({"expected_exe": ORIGINAL, "processes": [{"pid": 1, "start_time": T}]}),
        json!({"expected_exe": ORIGINAL, "processes": [{"pid": 100, "start_time": 0}]}),
        json!({"expected_exe": ORIGINAL, "processes": [{"pid": 100}]}),
        json!({"expected_exe": ORIGINAL, "processes": [{"pid": -5, "start_time": T}]}),
        json!({"expected_exe": ORIGINAL, "processes": too_many}),
    ];
    for case in cases {
        assert!(parse_request(&case).is_err(), "{case}");
    }
    let body = refused_body("why");
    assert_eq!((body["outcome"].clone(), body["still_running"].clone()), (json!("refused"), json!([])));
    assert_eq!(body["verify"]["ok"], false);
}

#[tokio::test]
async fn the_dispatch_arm_refuses_bad_requests_and_keeps_the_old_target_behaviour() {
    use crate::capabilities::response_actions::handle;
    let cfg = crate::capabilities::response_contract_tests::test_cfg();
    let client = reqwest::Client::new();
    let kill = |params: Value| json!({"task_id": "task-2", "parameters": params});
    for params in [
        json!({"expected_exe": ""}),
        json!({"expected_exe": ORIGINAL, "processes": [{"pid": 100, "start_time": T}], "quarantine_id": "bad id/../x"}),
        json!({"expected_exe": ORIGINAL, "processes": [{"pid": 1, "start_time": T}]}),
    ] {
        let body = handle("kill_process", &kill(params.clone()), &cfg, &client).await;
        assert_eq!(body["outcome"], "refused", "{params}");
        assert_eq!(body["still_running"], json!([]));
    }
    // Target only: the Phase 53 behaviour and body shape.
    let body = handle("kill_process", &kill(json!({"target": ""})), &cfg, &client).await;
    assert_eq!(body["status"], "error");
    assert!(body.get("outcome").is_none());
    let body = handle("kill_process", &kill(json!({"target": "systemd"})), &cfg, &client).await;
    assert!(body["error"].as_str().unwrap().contains("OS-critical"));
}

#[tokio::test]
async fn a_request_for_a_program_that_is_not_running_is_a_clean_no_op() {
    let req = KillRequest {
        expected_exe: "/definitely/not/running/anywhere.bin".into(),
        moved_exe: None,
        listed: vec![ListedProcess { pid: 4_000_000, start_time: T }],
    };
    let body = kill_by_exe(req).await;
    assert_eq!(body["outcome"], "process_gone");
    assert_eq!(body["verify"], json!({"ok": true, "check": "process_gone"}));
}
