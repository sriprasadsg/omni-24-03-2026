# Installing the Omni-Agent AI platform watchdog

An operator checklist. Copy the commands line by line, as a user who has `sudo`, from the root of
the repository checkout. **Nothing in the application installs any of this.** The platform never
creates users, writes under `/etc`, or edits systemd or polkit; `start-all-services.sh` does not
know the watchdog exists. Every step below is yours to run, and each is reversible (see
"Uninstall" at the end).

The watchdog is one small Python program (standard library only) that a systemd timer starts every
minute. It checks MongoDB, the backend, nginx (and Ollama only where you say it is expected),
restarts what is down within a fixed budget, watches the TLS certificate and disk space, pages
your on-call channel, and reports everything to the backend, which shows it on the Platform
health panel. It runs as its own unprivileged user, `omni-watchdog`. The only privilege that user
has is a polkit rule allowing `restart`, `start` and `reset-failed` of three units.

## 0. Before you start

- **Never run `run-on-ubuntu.sh` on this machine.** It rewrites the firewall and can lock you out
  of SSH. This checklist does not need it.
- Read the current state of the units this checklist touches, and keep the output. You will compare
  against it later:

```bash
mkdir -p ~/omni-watchdog-install
systemctl cat mongod > ~/omni-watchdog-install/mongod-before.txt
systemctl cat nginx > ~/omni-watchdog-install/nginx-before.txt
systemctl cat omni-backend > ~/omni-watchdog-install/omni-backend-before.txt
```

- `mongod-before.txt` must show `/etc/systemd/system/mongod.service.d/kernel-rseq-check.conf` with
  the `GLIBC_TUNABLES` line. That drop-in is the MongoDB 8.0.34 kernel 7.0 fix. **Nothing here
  replaces or edits `kernel-rseq-check.conf`**; the restart drop-in below uses a different file
  name on purpose.

What gets installed where:

| File in the repository (`deploy/omni-watchdog/`) | Install destination | Owner and mode |
|---|---|---|
| `omni-watchdog.py` | `/usr/local/lib/omni-watchdog/omni-watchdog.py` | `root:root` 0644 |
| `omni_watchdog/*.py` (the package) | `/usr/local/lib/omni-watchdog/omni_watchdog/` | `root:root` 0644 |
| `systemd/omni-watchdog.service` | `/etc/systemd/system/omni-watchdog.service` | `root:root` 0644 |
| `systemd/omni-watchdog.timer` | `/etc/systemd/system/omni-watchdog.timer` | `root:root` 0644 |
| `systemd/omni-backend.service.d/10-omni-watchdog.conf` | `/etc/systemd/system/omni-backend.service.d/10-omni-watchdog.conf` | `root:root` 0644 |
| `systemd/mongod.service.d/50-omni-restart.conf` (optional) | `/etc/systemd/system/mongod.service.d/50-omni-restart.conf` | `root:root` 0644 |
| `systemd/nginx.service.d/50-omni-restart.conf` (optional) | `/etc/systemd/system/nginx.service.d/50-omni-restart.conf` | `root:root` 0644 |
| `polkit/49-omni-watchdog.rules` | `/etc/polkit-1/rules.d/49-omni-watchdog.rules` | `root:root` 0644 |
| `etc/watchdog.conf.example` | `/etc/omni-watchdog/watchdog.conf` | `root:omni-watchdog` 0640 |
| `etc/oncall.env.example` | `/etc/omni-watchdog/oncall.env` | `root:omni-watchdog` 0640 |
| (generated in step 3) | `/etc/omni-watchdog/ingest.token` | `root:omni-watchdog` 0640 |
| (created by systemd in step 7) | `/var/lib/omni-watchdog/` (state, spool, lock) | `omni-watchdog:omni-watchdog` 0750 |

The script and its package are installed **root-owned, outside the checkout**. The watchdog can
restart services, so the backend's user (and anyone who can edit the checkout) must not be able to
change the code or the configuration it runs with.

## 1. Create the user

```bash
sudo useradd --system --user-group --no-create-home --home-dir /nonexistent \
  --shell /usr/sbin/nologin omni-watchdog
id omni-watchdog
```

## 2. Install the script and the package (root-owned)

```bash
sudo install -d -o root -g root -m 0755 /usr/local/lib/omni-watchdog /usr/local/lib/omni-watchdog/omni_watchdog
sudo install -o root -g root -m 0644 deploy/omni-watchdog/omni-watchdog.py /usr/local/lib/omni-watchdog/omni-watchdog.py
sudo install -o root -g root -m 0644 deploy/omni-watchdog/omni_watchdog/*.py /usr/local/lib/omni-watchdog/omni_watchdog/
sudo chmod -R go-w /usr/local/lib/omni-watchdog
ls -l /usr/local/lib/omni-watchdog /usr/local/lib/omni-watchdog/omni_watchdog
```

Every line must show owner `root root` and no group or other write bit. Re-run this step after
any later update of the watchdog code in the repository (the installed copy does not follow the
checkout).

## 3. Configuration and the ingest token

`/etc/omni-watchdog` is readable by the watchdog user but never writable by it.

```bash
sudo install -d -o root -g omni-watchdog -m 0750 /etc/omni-watchdog
sudo install -o root -g omni-watchdog -m 0640 deploy/omni-watchdog/etc/watchdog.conf.example /etc/omni-watchdog/watchdog.conf
sudo install -o root -g omni-watchdog -m 0640 deploy/omni-watchdog/etc/oncall.env.example /etc/omni-watchdog/oncall.env
python3 -c "import secrets; print(secrets.token_hex(32))" | sudo tee /etc/omni-watchdog/ingest.token >/dev/null
sudo chown root:omni-watchdog /etc/omni-watchdog/ingest.token
sudo chmod 0640 /etc/omni-watchdog/ingest.token
ls -ld /etc/omni-watchdog && ls -l /etc/omni-watchdog
```

Expected: the directory is `drwxr-x--- root omni-watchdog`; `oncall.env` and `ingest.token` are
`-rw-r----- root omni-watchdog`. Do not print the token or paste it anywhere.

Edit `/etc/omni-watchdog/oncall.env` (a secret file once filled in; never commit it):

- `ONCALL_TYPE=pagerduty` with `PAGERDUTY_ROUTING_KEY=...`, or `ONCALL_TYPE=webhook` with
  `WEBHOOK_URL=...` (and `WEBHOOK_FORMAT=json|slack|teams`).
- **`HEARTBEAT_URL` is strongly recommended**: see step 10.

`watchdog.conf` needs no change on a stock server: every key in it is commented out and shows its
default.

## 4. Give the backend the token (backend restart is your step)

The backend receives the token through a systemd credential, so its own user never needs to read
the file.

```bash
sudo install -d -o root -g root -m 0755 /etc/systemd/system/omni-backend.service.d
sudo install -o root -g root -m 0644 deploy/omni-watchdog/systemd/omni-backend.service.d/10-omni-watchdog.conf \
  /etc/systemd/system/omni-backend.service.d/10-omni-watchdog.conf
sudo systemctl daemon-reload
systemd-analyze verify /etc/systemd/system/omni-backend.service
```

Then restart the backend at a time you choose (the running backend keeps working without the
credential; the new endpoint answers only after a restart):

```bash
sudo systemctl restart omni-backend
```

## 5. Optional: restart drop-ins for MongoDB and nginx

The stock units have no `Restart=`. These two drop-ins make systemd restart a crashed process in
5 seconds; the watchdog then only has to deal with hangs. Skip this step if you prefer; the
watchdog works without them.

```bash
sudo install -d -o root -g root -m 0755 /etc/systemd/system/mongod.service.d /etc/systemd/system/nginx.service.d
sudo install -o root -g root -m 0644 deploy/omni-watchdog/systemd/mongod.service.d/50-omni-restart.conf \
  /etc/systemd/system/mongod.service.d/50-omni-restart.conf
sudo install -o root -g root -m 0644 deploy/omni-watchdog/systemd/nginx.service.d/50-omni-restart.conf \
  /etc/systemd/system/nginx.service.d/50-omni-restart.conf
sudo systemctl daemon-reload
```

Prove that the existing MongoDB fix is untouched. Record `systemctl cat mongod` after the drop-ins
and compare it with the "before" copy from step 0:

```bash
systemctl cat mongod > ~/omni-watchdog-install/mongod-after.txt
diff ~/omni-watchdog-install/mongod-before.txt ~/omni-watchdog-install/mongod-after.txt
grep -n "GLIBC_TUNABLES" ~/omni-watchdog-install/mongod-after.txt
ls -l /etc/systemd/system/mongod.service.d/
```

The diff must show **only** the added `50-omni-restart.conf` block (`Restart=on-failure`,
`RestartSec=5s`). The `GLIBC_TUNABLES` line from `kernel-rseq-check.conf` must still be present and
that file must be unchanged. If the diff shows anything else, delete `50-omni-restart.conf`, run
`sudo systemctl daemon-reload` and stop. No MongoDB restart is needed for this step.

## 6. The polkit rule

```bash
sudo install -o root -g root -m 0644 deploy/omni-watchdog/polkit/49-omni-watchdog.rules \
  /etc/polkit-1/rules.d/49-omni-watchdog.rules
```

polkit reloads its rules on change. Verify it with `pkcheck` as the watchdog user. Replace nothing;
run both commands exactly:

```bash
sudo -u omni-watchdog bash -c 'pkcheck --action-id org.freedesktop.systemd1.manage-units --details unit nginx.service --details verb restart --process $$; echo $?'
sudo -u omni-watchdog bash -c 'pkcheck --action-id org.freedesktop.systemd1.manage-units --details unit ssh.service --details verb restart --process $$; echo $?'
```

The first (`nginx.service restart`) must print `0` (allowed). The second (`ssh.service restart`)
must print a non-zero number (refused). If the first is refused, polkit is not passing the unit with
its `.service` suffix as assumed, or the rule file has a problem: check
`journalctl -u polkit -n 50`, fix the rule, and do not enable the timer until the first command
prints `0`.

### Ollama (only where Ollama is expected)

By default the watchdog may not restart Ollama, and it never starts an Ollama that is not expected.
On a server where Ollama must run, make the one-line addition in the installed rule, changing

```javascript
var UNITS = ["mongod.service", "omni-backend.service", "nginx.service"];
```

to

```javascript
var UNITS = ["mongod.service", "omni-backend.service", "nginx.service", "ollama.service"];
```

and set `ollama_expected = true` under `[watchdog]` in `/etc/omni-watchdog/watchdog.conf`. Repeat the
`pkcheck` test with `ollama.service`.

## 7. Install and enable the timer

```bash
sudo install -o root -g root -m 0644 deploy/omni-watchdog/systemd/omni-watchdog.service /etc/systemd/system/omni-watchdog.service
sudo install -o root -g root -m 0644 deploy/omni-watchdog/systemd/omni-watchdog.timer /etc/systemd/system/omni-watchdog.timer
sudo systemctl daemon-reload
systemd-analyze verify /etc/systemd/system/omni-watchdog.service /etc/systemd/system/omni-watchdog.timer
sudo systemctl enable --now omni-watchdog.timer
```

The unit is `Type=oneshot`: a tick that arrives while the previous run is still active does not
start a second copy, a manual run beside the timer's run exits at once on its lock, and
`TimeoutStartSec=45` ends a hung run. The state directory `/var/lib/omni-watchdog` is created by
systemd on the first run (`omni-watchdog:omni-watchdog`, 0750).

## 8. Verify

```bash
systemctl list-timers omni-watchdog.timer
sudo systemctl start omni-watchdog.service
journalctl -u omni-watchdog -n 30 --no-pager
ls -ld /var/lib/omni-watchdog
```

- The journal shows a clean run (no traceback, no "permission denied" for systemctl).
- In the web app, Platform health shows the services as **Running** within about two minutes.
- With an on-call channel configured, press **Send test alert** on the panel: one alert arrives
  and resolves, and the "no working channel" banner clears.

### If the first run cannot reach systemd

The hardening in the unit assumes `systemctl` can still reach the system bus under
`ProtectSystem=strict` and `PrivateTmp=yes`. If the journal shows that it cannot (a bus connection
error rather than a polkit refusal), relax **one line at a time** with
`sudo systemctl edit omni-watchdog.service`, retry `sudo systemctl start omni-watchdog.service`
after each: first `ProtectSystem=full`, then `PrivateTmp=no`. Report which line was needed so the
shipped unit can be corrected. Keep `User=`, `NoNewPrivileges=yes` and the empty
`CapabilityBoundingSet=`.

## 9. Read-only checks that nothing else changed

```bash
systemctl cat mongod | grep -n "GLIBC_TUNABLES"
sudo -u omni-watchdog test -w /usr/local/lib/omni-watchdog && echo "BAD: script dir writable" || echo "ok"
# azureuser is the backend's user on this server; use the SERVICE_USER your units run as
sudo -u azureuser test -w /var/lib/omni-watchdog && echo "BAD: state writable by the backend user" || echo "ok"
```

## 10. External heartbeat (strongly recommended)

If this whole server goes down, nothing on it can page you. Set `HEARTBEAT_URL` in
`/etc/omni-watchdog/oncall.env` to a dead-man URL from an outside service (for example a
healthchecks.io check with a 5 minute period and grace); the watchdog pings it after every
successful run, and the outside service alerts you when the pings stop. The Platform health panel
shows the external heartbeat as "Not configured" until a URL is set.

## 11. Emergency stop (the STOP file)

Creating the file stops every automatic restart immediately, even if the backend and database are
down:

```bash
sudo touch /etc/omni-watchdog/STOP     # stop automatic restarts
sudo rm /etc/omni-watchdog/STOP        # resume
```

The watchdog keeps checking and reporting while stopped; it only refrains from restarting. The
stop can also be set from the panel; either source is enough to stop.

## 12. Data retention: confirm the first count soon

Scheduled retention counts what would be deleted at the next 02:00 UTC run (or sooner with **Run
cleanup now** on the Platform health panel) and deletes nothing until a platform administrator
reviews the count and confirms it. After you deploy, confirm the first retention count soon:
**the daily telemetry purge waits for that first confirmation (D-15)**, so unconfirmed telemetry
keeps growing. Review the counts on the panel after the first run, then confirm deletion.

## Uninstall

```bash
sudo systemctl disable --now omni-watchdog.timer
sudo rm -f /etc/systemd/system/omni-watchdog.service /etc/systemd/system/omni-watchdog.timer
sudo rm -f /etc/systemd/system/omni-backend.service.d/10-omni-watchdog.conf
sudo rm -f /etc/systemd/system/mongod.service.d/50-omni-restart.conf /etc/systemd/system/nginx.service.d/50-omni-restart.conf
sudo rm -f /etc/polkit-1/rules.d/49-omni-watchdog.rules
sudo systemctl daemon-reload
sudo rm -rf /usr/local/lib/omni-watchdog /etc/omni-watchdog /var/lib/omni-watchdog
sudo userdel omni-watchdog
```

Do not remove `/etc/systemd/system/mongod.service.d/kernel-rseq-check.conf`; it is not part of this
install. Restart the backend afterwards so it stops expecting the credential.
