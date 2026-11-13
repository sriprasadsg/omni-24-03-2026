# Autonomous Ops go-live checks

Five things can only be proven on the live server with real machines. A platform administrator walks
them one by one, then records each on the **Going live** card (Autonomous Ops, platform scope) with a
note of 10 to 500 characters saying what was done and what was seen. A record is kept for good: a
later record of the same check never replaces the earlier one, and every record is written to the
audit log. The checks belong to the whole platform, not to one organization. An organization can leave
shadow mode only after all five are recorded (see the last sections).

The Summary line of each check is the exact sentence the Going live card shows. This document is the
authority for those sentences.

Use a dedicated **test organization** for every check that needs one. Never use a customer
organization, never paste a secret, a token or a password into a note, and never put a customer's
host name in one.

## Before you start

1. **Test organization.** None exists yet. Create one (Super Admin, Add Tenant) with a name that says
   it is a test, tick Autonomous Ops for it, set its level to **Automatic within limits** (the level
   named undoable_auto in the API), and enrol the disposable test hosts into it. Agent version 2.1.16
   or later is needed for check 1, 2.1.17 or later for check 2.
2. **Shadow mode must be off for the test organization** for checks 1, 2 and 5, because in shadow mode
   the platform only records what it would have done and sends nothing to the machines. Two layers
   hold shadow on, and both must be off:
   - The deployment-wide switch, the environment variable AUTONOMOUS_REMEDIATION_DRY_RUN. Only the
     values 0, false, no or off turn it off. Changing it and restarting the backend is the platform
     owner's step, not the app's.
   - The organization's own shadow flag. The **Lift shadow mode** button refuses every organization,
     the test one included, until all five checks are recorded and seven whole days of shadow records
     exist. That order cannot be followed for the checks that need real actions. **Open decision:**
     until the project decides how a test organization is lifted early, the platform owner turns the
     test organization's own flag off directly on the server (the shadow field of that organization's
     document in the autonomy_settings collection) and says so in the note of every check recorded
     that way. Do this for the test organization only.
3. **Turn shadow back on afterwards.** When the walk is finished, put the organization's flag back on
   (**Turn shadow mode back on**, never gated) and, if you changed it, the deployment-wide switch.
4. Everything below is done by a person on the live server. Nothing here is run by the platform.

## 1. Firewall round-trip

Check id: firewall_round_trip

Summary: Block a test address with Autonomous Ops, confirm the firewall refuses it, then undo the block and confirm the address works again.

Prerequisites
- The test organization from "Before you start", shadow off, level Automatic within limits.
- A disposable Linux test host with root, enrolled in it with agent 2.1.16 or later. If the platform
  has Windows agents, a Windows test host with Defender on is walked the same way.
- A public address that you control and can connect to from the test host, for example a small
  server of yours that listens on one port. It is written below as [public address you control].
  It must be a real public address: the agent refuses every address that is not on the public
  internet (private, loopback, link-local, shared, benchmarking, documentation and multicast ranges),
  so an address from those ranges can never be blocked.

Steps
1. From the test host, confirm that [public address you control] is reachable, for example
   `curl --max-time 5 http://[public address you control]/`. Note that it answers.
2. Get the address flagged by two different sources. It is listed in a threat feed the platform
   reads, and a second source flags it too. Alternatively, in the test organization's **Response
   settings** switch **Require two sources before blocking or quarantining** off so that one source is
   enough (confirm the dialog), and write down that you did so. You put it back in step 7.
3. Make the test host connect to [public address you control] again so the platform sees the
   connection.
4. Wait for the next sweep. In the test organization's **Activity** list a block of that address
   appears as done. Until then you may see it as a suggestion when only one source has flagged it.
5. From the test host, repeat the connection of step 1. It must now fail or time out: the host
   firewall refuses the address. On Linux you can also list the firewall rules and see the entry.
6. In **Activity** press **Undo** on that row. Repeat the connection of step 1: it must work again.
7. If you switched the two-source rule off in step 2, switch it back on and save.
8. If the host has public IPv6 connectivity, repeat steps 1 to 6 with a public IPv6 address you
   control. If it has none, say so in the note.

Expected result: the address answers before, is refused after the block, and answers again after
the undo, and the Activity row ends as undone.

What to write in the note: what was blocked and in which direction, the times, whether you used the
two-source path or switched the rule off, and the host system. Example: "Blocked [public address you
control] from the Linux test host. Firewall refused it at 14:02, Undo at 14:05, reachable again at
14:06. Two sources used, IPv6 not available on this host."

## 2. Reboot gate

Check id: reboot_gate

Summary: Confirm a patch that needs a reboot waits for approval on its card, and the machine does not restart on its own.

Both parts are walked and the check is recorded only when both pass.

Prerequisites
- The test organization, shadow off, an enrolled agent at 2.1.17 or later on each disposable host.
- Patch rings set up for the test organization and an open maintenance window that covers the walk
  (Patch management, Rings and Change management windows).
- Linux part: a disposable Linux host with a kernel package update available and not yet installed
  (for example `apt list --upgradable` shows a linux-image package, or the equivalent for your
  distribution). If none is pending, the host cannot be used until one is.
- Windows part: a disposable Windows host for which Windows Update offers a cumulative update. This
  depends on what Windows Update offers on the day, and it is the slower part.

Steps (once for Linux, once for Windows)
1. In **Patch management**, open the **Rollouts** tab and press **Start rollout**. Pick the ring
   holding the test host and the pending update (the kernel package, or the cumulative update).
   Read the "What will happen" block: it must list a restart for this update.
2. Start the rollout. When the install step is done, the rollout waits at its **Restart** line.
3. In **Needs your decision** the rollout approval card shows the Restart line with its own Approve
   and Deny. Leave it unapproved for at least five minutes. On the host confirm that it did not
   restart (on Linux `uptime` or `who -b` is unchanged, on Windows the last boot time is unchanged).
4. Approve the Restart line. Confirm the host restarts, reports back, and the rollout continues
   through its health checks. One approval covers that stage; there is no approve-all.
5. On the Windows part, confirm in addition that Windows did not restart by itself during step 3.

Expected result: nothing restarts before the approval; after it the host restarts once and the
rollout continues from the heartbeat the host sends after the restart.

What to write in the note: both host systems, the update used for each, the time the card appeared,
the time you approved, and that the host stayed up until then. Example: "Linux: kernel update held at
the Restart card from 10:12, no reboot until Approve at 10:25. Windows: cumulative update, same
result, approved 11:40. Both hosts healthy afterwards."

## 3. Watchdog stop and start

Check id: watchdog_stop_start

Summary: Stop the watchdog timer on the server, confirm Platform health shows Silent, start it again and confirm it shows Running.

Prerequisites
- The watchdog is installed as described in deploy/omni-watchdog/INSTALL.md (sections 7 and 8) and
  Platform health shows its services as Running before you begin. It runs as a one-shot service that
  the omni-watchdog.timer unit starts, so you stop and start the timer.
- Never run run-on-ubuntu.sh on this server: it changes the firewall and can lock you out of SSH.
- The backend has been up for more than 3 minutes, because it never judges the watchdog silent
  sooner after a restart.

Steps
1. Open **Platform health** and note that the services show **Running**.
2. On the server run `sudo systemctl stop omni-watchdog.timer`.
3. Wait more than 5 minutes. Platform health must show the watchdog as **Silent**, and one alarm
   appears in the app. A shorter wait proves nothing.
4. Run `sudo systemctl start omni-watchdog.timer`.
5. Within about two minutes Platform health shows **Running** again.
6. Optional: stop one watched service and see it restarted by the watchdog, MongoDB first. Skip it if
   the restart drop-ins of INSTALL.md section 5 are not installed.

Expected result: Silent after more than 5 minutes without the timer, Running within about two minutes
of starting it.

What to write in the note: the times of stop, of Silent, of start and of Running. Example: "Timer
stopped 09:00, Silent shown at 09:06 with one alarm, timer started 09:07, Running at 09:08."

## 4. Alert delivery

Check id: alert_delivery

Summary: Send a test alert from Platform health and confirm it reaches the on-call channel.

Prerequisites
- The watchdog is running (check 3 passed or Platform health shows Running).
- An on-call channel is configured in the root-only file /etc/omni-watchdog/oncall.env (INSTALL.md
  sections 3 and 8). Do not open that file in front of anyone and never copy its contents into a
  note.

Steps
1. Open **Platform health**, find the **On-call alerting** card and press **Send test alert**.
2. The button shows that it is waiting for the watchdog. Wait for it to finish.
3. On the real on-call channel (the device or inbox of the person on call) confirm exactly one alert
   arrives, and that it then resolves.
4. Back in the app confirm the "no working channel" banner is gone.

Expected result: one alert on the real channel, resolved, and no banner.

What to write in the note: which kind of channel received it and the times. Example: "Test alert sent
at 15:20, one alert on the on-call phone at 15:21, resolved at 15:22, banner cleared."

## 5. Live stop drill

Check id: live_stop_drill

Summary: Use Stop all organizations and confirm new decisions halt, queued instructions are held back, approvals and rollouts freeze and AI ticket replies pause. Then resume.

The automated half of this drill runs in the test suite. This is the live half, with real agents.

Prerequisites
- The test organization with a real agent, shadow off.
- A queued instruction for that agent that has not been picked up yet, an action waiting on an
  approval card in **Needs your decision**, a running rollout (from check 2), and a portal ticket
  with the local language model running so the assistant would normally answer it.

Steps
1. In platform scope press **Stop all organizations** and confirm.
2. The next time the test agent checks in, confirm it is not given the queued instruction.
3. Press **Approve** on the waiting card. The answer must say that automatic actions are stopped,
   and nothing runs.
4. Open the running rollout. It shows as paused.
5. Raise a new portal ticket. The assistant does not answer it and the ticket is handed to a person.
6. Wait for one sweep and confirm that no new automatic decision was recorded in **Activity**.
7. Press **Resume all organizations**, enter a reason (it is required) and confirm. Confirm that the
   instruction is now delivered, the rollout continues, and decisions are recorded again.
8. Repeat steps 1 to 7 for the test organization alone: in its own scope press **Stop automatic
   actions**, check the same effects for that organization only, then **Resume automatic actions**
   with a reason.

Expected result: while stopped nothing is delivered, approved, decided or answered automatically;
after the resume everything continues.

What to write in the note: what you queued, what each stop held back, the stop and resume times and
the reason you entered. Example: "Stop all at 16:00: instruction not delivered, Approve answered
stopped, rollout paused, ticket handed to a person, no new decisions. Resumed 16:12 with a reason,
all continued. Tenant-only stop repeated with the same result."

## After the checks: lifting one organization

An organization leaves shadow mode only when all of these hold:
- All five checks above are recorded (the card shows how many of the five are done).
- At least 7 whole days have passed since the organization's first shadow record. The control shows
  the days observed and how many actions would have been done.
- You type the organization's name exactly as shown to confirm.

The server enforces this on the lift itself, not only in the screen. Turning shadow mode back on is
always allowed and needs no gate. Every lift and every restore is written to the audit log; neither
adds a row to the organization's Activity list.

The deployment-wide shadow switch stays on until the platform owner removes it on the server (an
environment change and a restart of the backend). While it is on, lifting one organization takes
effect only once it is removed. That is the owner's step.

## Digest and export spot checks

These are not recorded on the card. Do them once after go-live.
- The daily digest is sent at 07:00 UTC. On a day with activity or simulation items every
  administrator of the organization gets one in the app (and by email where the deployment has a
  front-end address set). On a quiet day, with nothing run, undone or waiting and no simulation
  item, nothing is sent.
- Press **Export activity** on the Activity screen, and use the export on the Reporting screen,
  for both CSV and PDF. Confirm the file downloads and holds the rows in view, that more than 5000
  rows are cut off with a note saying so, and that each export appears in the audit log.
