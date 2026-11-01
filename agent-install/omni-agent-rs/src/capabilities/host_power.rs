//! RED stub: every function panics until the implementation lands.
use crate::capabilities::firewall::Os;
use serde_json::{json, Value};

pub const DELAY_MIN: i64 = 30;
pub const DELAY_MAX: i64 = 300;
pub const DELAY_DEFAULT: i64 = 60;
pub const REASON_MAX: usize = 200;

pub fn parse_delay(_value: Option<&Value>) -> Result<i64, String> { todo!() }
pub fn clean_reason(_raw: &str) -> String { todo!() }
pub fn schedule_reboot(_os: Os, _delay_seconds: i64, _reason: &str) -> Value { todo!() }
pub(crate) fn handle(_item: &Value, _os: Os) -> Value { todo!() }

#[cfg(test)]
mod tests {
    use super::*;
    use crate::capabilities::privileged::with_recorder;

    fn fresh() {
        with_recorder(|r| {
            r.script.clear();
            r.calls.clear();
        });
    }

    fn calls() -> Vec<Vec<String>> {
        with_recorder(|r| r.calls.clone())
    }

    fn item(params: Value) -> Value {
        json!({"task_id": "task-1", "parameters": params})
    }

    #[test]
    fn a_delay_from_30_to_300_passes_and_29_and_301_are_refused() {
        assert_eq!(parse_delay(Some(&json!(30))), Ok(30));
        assert_eq!(parse_delay(Some(&json!(300))), Ok(300));
        assert!(parse_delay(Some(&json!(29))).is_err());
        assert!(parse_delay(Some(&json!(301))).is_err());
        assert!(parse_delay(Some(&json!(-60))).is_err());
    }

    #[test]
    fn a_missing_delay_is_60_and_a_delay_that_is_not_a_whole_number_is_refused() {
        assert_eq!(parse_delay(None), Ok(60));
        for bad in [json!("60"), json!(60.5), json!(true), json!([60])] {
            assert!(parse_delay(Some(&bad)).is_err(), "{bad}");
        }
    }

    #[test]
    fn the_linux_argv_is_shutdown_r_in_whole_minutes_rounded_up() {
        for (delay, minutes) in [(30, "+1"), (60, "+1"), (61, "+2"), (120, "+2"), (121, "+3"), (300, "+5")] {
            fresh();
            schedule_reboot(Os::Linux, delay, "patching");
            assert_eq!(calls(), vec![vec!["shutdown", "-r", minutes, "patching"]], "{delay}");
        }
    }

    #[test]
    fn the_windows_argv_is_shutdown_r_t_n_c_reason_one_element_each() {
        fresh();
        schedule_reboot(Os::Windows, 90, "patching");
        assert_eq!(calls(), vec![vec!["shutdown", "/r", "/t", "90", "/c", "patching"]]);
    }

    #[test]
    fn a_long_reason_is_cut_and_control_characters_are_removed() {
        let long = "x".repeat(REASON_MAX + 50);
        assert_eq!(clean_reason(&long).chars().count(), REASON_MAX);
        assert_eq!(clean_reason("Patch\r\nTuesday\t\u{7}now\u{0}"), "PatchTuesdaynow");
        // multi-byte text is cut on a character, never in the middle of one
        assert_eq!(clean_reason(&"é".repeat(300)).chars().count(), REASON_MAX);
    }

    #[test]
    fn a_reason_can_never_read_as_an_option_and_an_empty_one_gets_a_default() {
        assert_eq!(clean_reason("--halt now"), "halt now");
        assert_eq!(clean_reason("/a"), "a");
        assert!(!clean_reason("").is_empty());
        assert!(!clean_reason("\n\t").is_empty());
        assert!(!clean_reason("---").is_empty());
        assert_eq!(clean_reason("  patching  "), "patching");
    }

    #[test]
    fn a_hostile_reason_stays_one_argv_element() {
        fresh();
        schedule_reboot(Os::Linux, 60, "x; reboot -f && --poweroff");
        let c = calls();
        assert_eq!(c.len(), 1);
        assert_eq!(c[0].len(), 4);
        assert_eq!(c[0][3], "x; reboot -f && --poweroff");
    }

    #[test]
    fn the_body_says_scheduled_and_verified() {
        fresh();
        let body = schedule_reboot(Os::Linux, 60, "patching");
        assert_eq!(body, json!({"status": "success", "outcome": "scheduled", "verify": {"ok": true, "check": "reboot_scheduled"}}));
    }

    #[test]
    fn a_delay_outside_the_range_is_refused_and_no_command_runs() {
        fresh();
        for delay in [0, 29, 301, 100_000] {
            let body = schedule_reboot(Os::Linux, delay, "x");
            assert_eq!((body["status"].as_str(), body["outcome"].as_str()), (Some("error"), Some("refused")), "{delay}");
        }
        assert!(calls().is_empty());
        let body = handle(&item(json!({"delay_seconds": 29})), Os::Windows);
        assert_eq!(body["outcome"], "refused");
        assert!(calls().is_empty());
    }

    #[test]
    fn the_instruction_reads_delay_and_reason_from_its_parameters() {
        fresh();
        let body = handle(&item(json!({"delay_seconds": 90, "reason": "Patch window"})), Os::Windows);
        assert_eq!(body["outcome"], "scheduled");
        assert_eq!(calls(), vec![vec!["shutdown", "/r", "/t", "90", "/c", "Patch window"]]);
        fresh();
        handle(&item(json!({})), Os::Linux);
        assert_eq!(calls()[0][..3], ["shutdown", "-r", "+1"]);
    }

    #[test]
    fn a_failed_command_is_an_error_body_and_a_security_block_has_its_own_outcome() {
        fresh();
        with_recorder(|r| r.fail_next(1));
        let body = schedule_reboot(Os::Linux, 60, "x");
        assert_eq!(body["status"], "error");
        assert!(body.get("outcome").is_none());
        fresh();
        with_recorder(|r| r.fail_spawn(225));
        assert_eq!(schedule_reboot(Os::Windows, 60, "x")["outcome"], "blocked_by_local_security");
    }
}
