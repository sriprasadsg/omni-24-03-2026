<task type="checkpoint:human-verify" gate="blocking-human">
  <what-built>Package install failed — human verification required</what-built>
  <how-to-verify>
    `fanotify` could not be installed. Before proceeding:
    1. Verify the package exists and is legitimate: https://npmjs.com/package/fanotify (Note: The user asked for Rust crates, so check crates.io)
    2. Confirm the package name is spelled correctly in PLAN.md
    3. If the package does not exist, re-run /gsd-plan-phase --research-phase <N> to find the correct package
  </how-to-verify>
  <resume-signal>Type "verified" with the correct package name, or "abort" to stop the phase</resume-signal>
</task>
