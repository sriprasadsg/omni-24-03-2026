//! A state file this release cannot use (it does not parse, or a newer agent wrote it) is set
//! aside and replaced, so blocks keep expiring and can be undone again (WR-18).
//!
//! Nothing is forgotten silently. Before the file goes aside the firewall is read for this agent's
//! own block rules (the `OMNI_BLOCK` chains, the `OmniAgent_Block_*` rules; nothing else adds
//! them), and each one becomes a claim named `recovered` that runs out after the default 24 hours,
//! so the rule still ends on its own and any unblock of that address ends it at once. When the
//! firewall cannot be read the file is left as it is and the next pass tries again. A file that
//! only could not be read (an I/O error) is never set aside. The set-aside copy keeps its contents
//! for a person to look at, and the new state notes where it went (`recovered`).
//!
//! The isolation record went with the file, so the sweeper then runs the start-up isolation pass,
//! which takes out isolation rules that have no record: the host keeps its network.

use super::{Claim, ResponseState, Store, FILE_NAME, RECOVERED_BLOCK_ID, STATE_VERSION, WRITE_LOCK};
use crate::capabilities::firewall::{Os, Target, LINUX_CHAIN, WINDOWS_RULE_PREFIX};
use crate::capabilities::privileged;
use crate::capabilities::remediation_actions::RemediationError;
use crate::capabilities::response_actions::BLOCK_TTL_DEFAULT;

/// What is wrong with the file's content, as the set-aside name says it: `corrupt` or `v<N>`.
/// None when it is fine, missing or cannot be read.
fn damage(store: &Store) -> Option<String> {
    let bytes = std::fs::read(store.path()).ok()?;
    let parsed = std::str::from_utf8(&bytes).ok().and_then(|text| serde_json::from_str::<ResponseState>(text).ok());
    match parsed {
        None => Some("corrupt".to_string()),
        Some(state) if state.v > STATE_VERSION => Some(format!("v{}", state.v)),
        Some(_) => None,
    }
}

/// Set a damaged state file aside and start again from the firewall's own block rules. The path
/// of the set-aside file when that happened.
pub(super) fn recover_damaged(store: &Store, os: Os, now: i64) -> Option<String> {
    let _guard = WRITE_LOCK.lock().unwrap_or_else(|poisoned| poisoned.into_inner());
    let kind = damage(store)?;
    let path = store.path().display().to_string();
    let targets = match owned_blocks(os) {
        Ok(targets) => targets,
        Err(e) => {
            log::error!("{path} cannot be used and its blocks could not be read from the firewall, will retry: {e}");
            return None;
        }
    };
    let aside = store.path().with_file_name(format!("{FILE_NAME}.{kind}-{now}"));
    if let Err(e) = std::fs::rename(store.path(), &aside) {
        log::error!("{path} cannot be used and could not be set aside, will retry: {e}");
        return None;
    }
    let mut state = ResponseState::default();
    for target in &targets {
        let claim = Claim { target: target.to_string(), block_id: RECOVERED_BLOCK_ID.to_string(), expires_at: now + BLOCK_TTL_DEFAULT };
        state.claims.push(claim);
    }
    let name = aside.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default();
    state.extra.insert("recovered".into(), serde_json::json!({"at": now, "from": name, "blocks": targets.len()}));
    if let Err(e) = store.write(&state) {
        log::error!("{path} could not be rewritten after it was set aside, will retry: {e}");
        let _ = std::fs::rename(&aside, store.path());
        return None;
    }
    log::error!(
        "{path} could not be used ({kind}); it was set aside as {} and the {} block(s) found in the firewall now end in 24 hours",
        aside.display(),
        targets.len()
    );
    Some(aside.display().to_string())
}

/// The targets of this agent's own block rules in the firewall right now.
pub(super) fn owned_blocks(os: Os) -> Result<Vec<Target>, RemediationError> {
    let mut found: Vec<Target> = Vec::new();
    let mut keep = |target: Option<Target>| {
        if let Some(t) = target.filter(|t| !found.contains(t)) {
            found.push(t);
        }
    };
    match os {
        Os::Linux => {
            for tool in ["iptables", "ip6tables"] {
                let listing = match privileged::run_status(tool, &["-w", "-S", LINUX_CHAIN]) {
                    Err(RemediationError::FileNotFound(_)) => continue, // not installed: holds no rules
                    other => other?,
                };
                match listing.code {
                    Some(0) => listing.stdout.lines().for_each(|line| keep(linux_rule_target(line))),
                    Some(1) => {} // no chain, so no block
                    code => return Err(privileged::exit_failure(tool, code, listing.stderr.trim())),
                }
            }
        }
        Os::Windows => {
            // Every Windows host has built-in rules, so anything but a clean listing is an error.
            let listing = privileged::run_status("netsh", &["advfirewall", "firewall", "show", "rule", "name=all"])?;
            if listing.code != Some(0) {
                return Err(privileged::exit_failure("netsh", listing.code, listing.stderr.trim()));
            }
            listing.stdout.lines().for_each(|line| keep(windows_rule_target(line)));
        }
    }
    Ok(found)
}

/// `-A OMNI_BLOCK -s 45.33.32.156/32 -j DROP` names 45.33.32.156.
fn linux_rule_target(line: &str) -> Option<Target> {
    let mut words = line.split_whitespace();
    if words.next()? != "-A" || words.next()? != LINUX_CHAIN {
        return None;
    }
    host_or_network(words.skip_while(|w| *w != "-s" && *w != "-d").nth(1)?)
}

/// A line that holds `OmniAgent_Block_45.33.32.0_24_in` names 45.33.32.0/24. The label before
/// the name is in the local language; the name is not.
fn windows_rule_target(line: &str) -> Option<Target> {
    let at = line.find(WINDOWS_RULE_PREFIX)?;
    let key = line[at + WINDOWS_RULE_PREFIX.len()..].trim();
    let key = key.strip_suffix("_in").or_else(|| key.strip_suffix("_out")).unwrap_or(key);
    host_or_network(&key.replace('_', "/"))
}

/// The claim key the platform's unblock would use: a full-length prefix is the address alone.
fn host_or_network(text: &str) -> Option<Target> {
    let target = crate::capabilities::net_safety::parse_target(text)?;
    let full = if target.addr.is_ipv4() { 32 } else { 128 };
    Some(if target.prefix == Some(full) { Target::host(target.addr) } else { target })
}
