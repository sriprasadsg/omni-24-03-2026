<task type="checkpoint:human-verify" gate="blocking-human">
  <what-built>Fanotify requires sudo/CAP_SYS_ADMIN — human verification required</what-built>
  <how-to-verify>
    The fanotify test failed with `PermissionDenied` because fanotify requires `CAP_SYS_ADMIN` capability.
    1. Acknowledge this is expected for fanotify.
    2. Confirm if the execution environment supports running tests with elevated privileges or if this should be skipped for this phase.
  </how-to-verify>
  <resume-signal>Type "verified" if you want to proceed with elevated privileges (e.g., re-running test with sudo), or "abort" to stop the phase</resume-signal>
</task>
