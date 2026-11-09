---
phase: 85-first-line-service-desk
reviewed: 2026-11-09
depth: standard
files_reviewed: 142
findings:
  critical: 2
  warning: 14
  info: 12
  total: 28
status: issues_found
---

# Phase 85: Code Review Report (merged from 4 area passes)

The scope was 142 files from the SUMMARY key-files, cross-checked against the phase evaluation scope with nothing missing. Four parallel `gsd-code-reviewer` passes covered it at standard depth, following the Phase 83/84 precedent. Finding IDs carry the area number: CR/WR/IN-1xx to 4xx. The user's uncommitted hunks in `tickets_endpoints.py`, `InternalTicketsDashboard.tsx` and the Cargo files were excluded.

| Area | Scope | Critical | Warning | Info |
|------|-------|----------|---------|------|
| 1 | backend/service_desk core | 1 | 3 | 2 |
| 2 | endpoints, autonomous_ops gate layer, tickets, notifications, migration, eval script | 0 | 3 | 4 |
| 3 | backend tests and fixtures | 0 | 3 | 3 |
| 4 | UI, services, tray scripts, tray.rs, Cargo version lines | 1 | 5 | 3 |

**Coverage caveats.** Each area report states what it read in full and what it only grep-scanned. Area 3 left several test files unread, and area 4 skimmed the test files and four small components. Treat unread files as unreviewed, not clean.

---

## Area 1: backend/service_desk core


**Reviewed:** 2026-11-09
**Depth:** standard
**Files Reviewed:** 26
**Status:** issues_found

## Summary

Area 1 is well built: tenant scoping is explicit on every raw query, status and comment changes are compare-and-set, the
rule order is fixed, and the model reply never chooses an outcome. The worker and the hand-off paths log and continue
instead of leaving tickets stranded.

Depth note: `messages.py`, `phrases.py`, `tray_contract.py` and the tail of `settings.py` (probe and status view, after
line 260) were skimmed only; the logic files were read in full. One finding (CR-101) was reproduced by running the code.
SECURITY.md accepted risks (T-85-29, 34, 37, 55, 73, 77, 82) were not re-raised.

## Critical Issues

### CR-101: Output checks (D-19) can be bypassed with hidden or compatibility characters, so a foreign link or email reaches the requester

**File:** `backend/service_desk/checks.py:131-173` (the answer is posted unchanged at `backend/service_desk/pipeline.py:134` and `backend/service_desk/outcomes.py:79`)
**Issue:** `check()` runs every extraction regex on the raw `reply.answer`. The article text it compares against is NFKC
normalised (`_norm`), but the answer is never normalised and hidden characters are never rejected. Run against
`backend/venv` with one cited article ("Open the Settings page. Contact IT support from the tray for help."), every
variant below returned `None` (accepted):

- `Visit evil.​com now for Settings page help` (zero-width space after the dot)
- `Visit evil​.com for Settings help`
- `Visit ｅｖｉｌ．ｃｏｍ Settings` (full-width letters and dot)
- `Visit EVIL。com Settings` (ideographic full stop)
- `Mail a​@evil.com about Settings`: the local part before the zero-width character is not `\w`, so `_EMAIL` does not match, and `_BARE_DOMAIN` has `(?<![\w@.-])`, so `evil.com` after the `@` is skipped too.

By contrast `ipc​onfig` and a zero-width-split phone number were still caught, so the gap is specific to the
link and email rules. The text is stored and shown as written. Rendered, those strings read as an ordinary domain or
address and a pasted or auto-linked form is a working link. This contradicts the stated mitigation for T-85-19 and
T-85-48 ("every link, email, phone and command must occur in a cited article"). The model is told to ignore injected
instructions, but a prompt-injected ticket is exactly the case these checks exist for. Drafts are read by technicians,
so the injected text can phish staff even when the desk is in Drafts only mode.
**Fix:** Normalise before extracting, and fail closed on hidden characters. In `check()`, before the `_is_html` call:

```python
import unicodedata

def _canonical(answer: str) -> str:
    return unicodedata.normalize("NFKC", answer)

# in check():
if any(unicodedata.category(ch) == "Cf" or (unicodedata.category(ch) == "Cc" and ch not in "\n\t")
       for ch in answer):
    return "html"                      # or a new rule "hidden_characters" added to RULES
answer = _canonical(answer)            # then run every regex on this form
```

Post and store the NFKC form (return it from `check`, or normalise in `parse_reply`) so the text that was checked is
the text that is shown. Also treat `。`, `．` and `｡` as dots after NFKC (NFKC already maps the first two), and add the
variants above to the `checks` fixture set.

## Warnings

### WR-101: The loopback guard can be defeated by environment proxy settings, sending ticket text to a proxy

**File:** `backend/service_desk/model.py:128-129`
**Issue:** `_http()` builds `httpx.AsyncClient(transport=self._transport, timeout=..., follow_redirects=False)` with the
default `trust_env=True`. With `HTTP_PROXY` or `ALL_PROXY` set in the backend's environment and no `NO_PROXY` entry for
127.0.0.1, httpx routes `http://127.0.0.1:11434/...` through the proxy. Confirmed locally: with
`HTTP_PROXY=http://10.9.9.9:3128`, `client._transport_for_url(URL("http://127.0.0.1:11434/api/generate"))._pool` is an
`AsyncHTTPProxy`. The prompt (cleaned ticket text plus article text) would then leave the VM, which breaks the
"ticket text never leaves this server" rule (T-85-03, T-85-22) even though the host allow-list passes. The same applies to
`_get` (probe) and `loaded()`.
**Fix:**
```python
return httpx.AsyncClient(transport=self._transport, timeout=timeout, follow_redirects=False, trust_env=False)
```

### WR-102: A failure after the status move in `outcomes.post` or `keep_draft` leaves a posted answer, a stuck ledger row and a contradicting hand-off

**File:** `backend/service_desk/outcomes.py:88-98` and `backend/service_desk/outcomes.py:109-122` (caller `backend/service_desk/worker.py:211-216`)
**Issue:** In `post`, only the `add_comment` is wrapped. After the ticket is `pending_customer` and the requester-visible
comment exists, `set_desk`, `ledger.transition`, `ledger.set_display` and `notify.requester_notice` are unguarded. If one
of the first three raises, `worker._fail` runs `_to_a_person(..., only_if_unanswered=True)`. The desk phase is still
`queued`, so it is not treated as answered, and the ticket gets a `service_desk_busy` hand-off: a staff note, a requester
notice saying a person will take over, and an `autonomy_actions` hand-off row. Meanwhile the ticket stays
`pending_customer` with the answer visible, the original ledger row stays `dispatching` (never `executed`, so Undo and
the breaker never see it), and the job is closed as `error`. `keep_draft` has the same shape: the comment is written
first, and a failure in `set_desk` or the ledger calls leaves a draft with no `desk.draftWaiting` and a row stuck in
`dispatching`.
**Fix:** Order the writes so the visible effect comes last, or guard each follow-up step the way `lifecycle._guarded` and
`withdraw._step` do (log, continue, and always end the ledger row). At minimum wrap the post-comment steps and, on failure,
still call `ledger.transition(..., ("dispatching",), "executed", ...)` and `set_desk(phase="posted")` in a final
`try/finally`, so the phase check in `_to_a_person` sees `posted`.

### WR-103: `send_draft` makes the answer visible before the status move, and ignores a lost status move

**File:** `backend/service_desk/lifecycle.py:110-120`
**Issue:** `_turn_draft` flips the comment to `kind=ai_answer, visibility=requester` first. Then `move_status(..., _SEND_FROM,
"pending_customer")` runs inside `_guarded`, so a `False` result (the ticket became `resolved` or `closed`, or moved to
`pending_customer` through another path, between the `projection.blocked` read and the write) is ignored. The requester
can then read an answer on a ticket that is closed, `desk.phase` is set to `sent` with `undoable: True`, and
`confirmable()` is false so the requester gets no buttons. The window is small but the design elsewhere (outcomes.post)
moves status first for exactly this reason.
**Fix:** Move the status first and send only if it moved, as `outcomes.post` does:
```python
moved = await ticket_writes.move_status(db, tenant_id, ticket_id, _SEND_FROM, "pending_customer", actor=..., now=now)
if not moved:
    return refused("ticket_closed", state=ticket.get("status"))
won = await _turn_draft(...)
if not won:  # put the status back
    await ticket_writes.move_status(db, tenant_id, ticket_id, ("pending_customer",), ticket["status"], actor=..., now=now)
    return refused("already_handled")
```

## Info

### IN-101: `retrieval.candidates` has no order, so more than 300 Help desk articles are cut at random

**File:** `backend/service_desk/retrieval.py:109-111`
**Issue:** `find(...).to_list(MAX_CANDIDATES)` takes the first 300 in natural order. A tenant with more Help desk articles
silently loses the best match for some questions (hand-off `no_article`, and a false gap-list entry). Unlikely today
(four starters plus tenant additions) but the cap gives no warning.
**Fix:** Sort for a stable result, for example `.sort([("updatedAt", -1), ("id", 1)])`, and log a warning when the list is
full.

### IN-102: Smaller consistency items

**File:** `backend/service_desk/starters.py:149` and `backend/service_desk/returns.py:48-56`
**Issue:** (a) `_iso(None)` uses `datetime.utcnow()`, which is deprecated and naive, while every other desk timestamp is
timezone-aware; use `datetime.now(timezone.utc)`. (b) `returns._return_ticket` does not look at `desk.personReplied`: a
ticket a technician already replied to (set by `lifecycle.on_comment_added`) but left in `pending_customer` is flipped to
`open` after three working days and handed off as `no_reply_to_ai_answer`, which misstates what happened. Skip the sweep
for such tickets or use a different reason.
**Fix:** As described in each point.

---

_Reviewed: 2026-11-09_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

---

## Area 2: endpoints, autonomous_ops gate layer, tickets, notifications, migration, eval script


**Reviewed:** 2026-11-09
**Depth:** standard
**Files Reviewed:** 30
**Status:** issues_found

## Summary

Reviewed the phase's committed diff (`fbb6e263f..HEAD`) of all 30 files, plus the new files in full. For
`backend/tickets_endpoints.py` only the phase's committed hunks were reviewed. The user's uncommitted attachment
hunks were not reviewed.

What holds up, traced against the code:
- Every new portal route (`service_desk_endpoints.py`) reads the ticket through `tickets_service.get_ticket` with the
  caller's own tenant (a Super Admin's empty tenant gives 404). The reporter gets only the requester projection and
  is refused on the draft routes. The article route checks the id against the ids cited on that ticket and filters
  `tenantId` and `helpdesk: True`, so it never reads the global set.
- The tray routes bind the agent through `verify_agent_key` (`bind_path_agent`). Every query filters `tenantId`,
  `agent_id`, `raised_via` and `myTickets`, and every answer is an explicit projection.
- The gate refuses `ticket_answer` and `ticket_withdraw` from any other dispatcher (`gate._step_class`, unrecorded).
  `dispatch_check.bind` refuses every ticket command. `approvals.approve` and `deny` refuse desk rows. `undo` falls
  through to `not_undoable` when no handler is registered.
- The desk's hourly pool is separate from the default pool (`ledger._pool_filter`). The `kind` override in
  `{**_AUTO_ROWS, **_pool_filter()}` is intentional and correct.
- The settings routes carry the exact permission plus an interactive session, on top of the catalogue guard.

No critical issues. Three warnings concern notification audience handling and one logic gap in the gap-to-article
flow.

Accepted residual, not raised as a finding (AR-85-01, T-85-29, T-85-55, T-85-77): the legacy
`GET /api/tickets/{id}`, the ticket list, `PATCH` and `POST /comments` still return every comment, including
`ai_draft` text and `desk.lastReason`/`draftReason`, to the reporter. The code does not contradict the acceptance.

## Warnings

### WR-201: the `ticket_staff` audience tag on staff-only comment notices is never enforced, so the feed and socket still tell the reporter

**File:** `backend/ticket_notifications.py:149` (reader: `backend/notification_endpoints.py:75-85`)
**Issue:** The docstring says a staff-only notice "is tagged for ticket staff", and the test only asserts the tag
(`tests/test_service_desk_comments.py:205`). Nothing reads `metadata.audience == "ticket_staff"`:
`get_notifications` filters only `tenant_admins` and `recipient`, and `send_alert` broadcasts the full title and
message over the tenant WebSocket for notices with no `recipient`. The notice is stored with only `tenantId` and no
reader filter, so every tenant user, the reporter included, sees
`[TKT-n] New comment by <staff email>` and `New staff comment on ticket '<title>'` in the bell and the socket.
Excluding the reporter from `recipients` only stops direct channel delivery. The comment text does not leak, but the
fact that a staff-only comment exists, and who wrote it, does. That is the information the staff-only default is
meant to hide (T-85-26 is closed on "excludes the reporter", which holds only for recipients).
**Fix:** Make the tag effective. For example, store `metadata.excludeRecipient = reporter` on the staff notice and
add to the reader query:
```python
query["$and"].append({"$or": [
    {"metadata.excludeRecipient": {"$exists": False}},
    {"metadata.excludeRecipient": None},
    {"metadata.excludeRecipient": {"$nin": me}},
]})
```
Blank the socket `message` and title for `audience == "ticket_staff"` as it is done for `recipient`. Alternatively,
send one notice per staff recipient with `metadata.recipient` set, which the reader already honours. Add a test with
the reporter as a reader.

### WR-202: addressed notices can be marked read or deleted by any tenant user

**File:** `backend/notification_endpoints.py:93-135` (`mark_as_read`, `mark_all_as_read`, `delete_notification`)
**Issue:** Phase 85 makes notices personal (`metadata.recipient`) and filters only the list route.
`PUT /read-all` with no ids does `update_many({"tenantId": tenant})`. It flips the `read` flag on every
recipient-addressed notice of every other user, so the reporter's "your ticket has an answer" notice can be
silently marked read by a colleague. `DELETE /{notification_id}` and `PUT /{id}/read` take any `alert_id` in the
tenant without the recipient check. Before this phase every notice was tenant-wide, so a shared read state was
consistent. Now it loses the one-person guarantee the list route claims (D-33).
**Fix:** Apply the same recipient predicate to the three write queries, for example
```python
_mine = {"$or": [{"metadata.recipient": {"$exists": False}}, {"metadata.recipient": None},
                 {"metadata.recipient": {"$in": me}}]}
query = {"tenantId": tenant_id, **_mine}   # and `{"$and": [...]}` when combined with alert_id
```
Factor `me` and `_mine` into one helper shared with `get_notifications`.

### WR-203: writing an article from a gap with `helpdesk: false` marks the gap group written although the desk can never use the article

**File:** `backend/knowledge_helpdesk_endpoints.py:266-309` (`ArticleIn.helpdesk`, `write_article`)
**Issue:** `ArticleIn.helpdesk` defaults to `True` but is accepted as `False`. With `gapGroupId` set, the group's
rows are claimed as `written` (and leave the list) before the article is inserted. When `helpdesk` is `False` the
article is not retrievable by the desk, so the unanswered question is hidden from authors while still unanswered. The
same question will keep reaching a person with no gap entry to prompt a new article.
**Fix:** Reject the combination before claiming:
```python
if body.gapGroupId and not body.helpdesk:
    raise HTTPException(status_code=422, detail="An article written from a gap must be a Help desk article.")
```

## Info

### IN-201: the desk branch of the gate does not require ticket-kind actions

**File:** `backend/autonomous_ops/gate.py:221-222`, `backend/autonomous_ops/desk_gate.py:23-43`
**Issue:** `_step_protected_targets` hands every `dispatcher == "service_desk"` request to `ticket_owner_step`, and
`ticket_owner_step` checks only that the request has no targets and a ticket id. A `service_desk` request naming an
agent action (`isolate_host`, `block_ip`, ...) therefore skips the agent-target, never-touch and IP checks and records
a card row with empty `targets`. It cannot be dispatched, because `bind` refuses it as `target_mismatch`, so the
effect is a stray decision row and a missing defence-in-depth layer. The registry restricts only the opposite
direction (ticket actions to the desk). Only the desk code builds these requests today.
**Fix:** In `ticket_owner_step`, refuse unless every spec in `ctx.specs + ctx.rollback_specs` has
`target_kind == "ticket"` (code `invalid_target`), and add an invariant test.

### IN-202: a Windows user name between 201 and 256 characters can never match its own tickets

**File:** `backend/service_desk_tray_endpoints.py:111-113` and `:148`
**Issue:** `create_tray_ticket` stores `windowsUser` truncated to `intake.WINDOWS_USER_CAP` (200). The query user and
the body user are allowed up to `USER_MAX` (256) and are compared untruncated in `_is_user`. A longer name sees an
empty list and gets 404 on confirm and help. Rare, but it is a silent mismatch.
**Fix:** Compare `projection.same_person(channel.get("windowsUser"), user[:intake.WINDOWS_USER_CAP])`, or lower
`USER_MAX` to the cap.

### IN-203: the eval script documents passing the database URL on the command line

**File:** `backend/scripts/service_desk_eval.py:20-37` (usage text), `:110-113` (`open_database`)
**Issue:** The documented commands use `--mongo "$MONGODB_URL"`. A URL with credentials then appears in the process
arguments (`ps`, `/proc/*/cmdline`) for the duration of the run, on a shared VM. The script already falls back to
the environment variable when `--mongo` is absent.
**Fix:** Change the documented commands to rely on the exported `MONGODB_URL` (drop `--mongo "$MONGODB_URL"`) and
keep `--mongo` only as an override.

### IN-204: body-size bounds on the new Knowledge Base models are checked after full parsing

**File:** `backend/knowledge_helpdesk_endpoints.py:76-82` (`DocPatch`), `:266-273` (`ArticleIn`)
**Issue:** `title`, `content` and `tags` have no `max_length`, so the 20,000-character, title and tag limits run only
in `_validated` after the whole body is parsed. The portal routes use `max_length=20000` on the model for exactly
this reason (`HelpNote`, `DraftEdit`). `patch_doc` also applies the Help desk content cap to every article edit,
marked or not.
**Fix:** Add `Field(max_length=...)` bounds to the models, with a generous bound on `content`. Decide whether the cap
should apply to unmarked articles, or document that it does.

---

_Reviewed: 2026-11-09_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

---

## Area 3: backend tests and fixtures


**Coverage caveat (reviewer):** the reviewer's context ran short, so coverage is not uniform.

- **Read in full or in large part:**
  - the five `service_desk_*_support.py` helpers
  - `test_service_desk_gate.py`, `_injection.py`, `_eval_script.py` and `_worker.py`
  - the key parts of `_portal_routes.py`, `_tray_routes.py`, `_knowledge_gaps.py`, `_retrieval.py` and `_model.py` (loopback)
- **Grep-scanned only:** every `test_*` file, for wall-clock, sleep, task-spawn and skip patterns.
- **Not read in full** (treat as unreviewed, not clean):
  - the five `test_autonomous_ops_*` / `test_catalogue_slice_*` files
  - `_lifecycle.py`, `_withdraw.py`, `_pipeline.py`, `_intake.py`, `_ledger.py`, `_comments.py`, `_rules.py`, `_sanitize.py`, `_settings.py`, `_tracer.py`, `_tray_actions.py`, `_tray_server_contract.py` and `_tray_static.py`
  - the five JSONL fixtures

## Summary

The tests that were read are mostly strong.

- **Database isolation:** every database test goes through `tests/_mongo_test_db.mongo_db`, which uses a unique `omni_test_<uuid>` database and drops it afterwards.
- **No real Ollama:** every model call uses `httpx.MockTransport`.
- **Staff-only text never reaches a requester:** this is tested with real planted secrets (`hunter2`, a staff note, a draft, a withdrawn answer), each asserted against the raw response text.
- **Tenant isolation:** asserted as 404 on every portal route.
- **Loopback guard:** the check covers look-alike hosts, a non-http scheme and a LAN address.
- **Injection set:** runs the whole pipeline and checks queues, status, assignee, priority, prompt content and posted text.
- **Clocks:** the desk code is time-injected, and the tests mostly pass explicit clocks and timezones.

There are no Critical findings. The three Warnings are a date-dependent flake, a brittle assertion and an unproven claim.

## Warnings

### WR-301: A fixed "now" plus a 90-day TTL index makes the worker and hand-off tests flaky after about 2027-02-06

**Files:**
- `backend/tests/service_desk_worker_support.py:23` (`NOW = datetime(2026, 11, 9, 12, 0, ...)`)
- `backend/tests/test_service_desk_handoff.py:24` (`NOW = datetime(2026, 11, 8, 10, 0, ...)`)

**Issue:**
- The `world` fixtures call `store.ensure_indexes(mongo_db)` and `ledger.ensure_indexes`. That creates the real TTL indexes: 90 days on `service_desk_jobs.finishedAt` (`store.py:31`) and on `service_desk_gaps.createdAt` (`store.py:35`).
- The tests stamp those fields from the fixed clock: `worker.py:89` writes `finishedAt = now`, and `gaps.record` is passed `now=NOW`.
- Once the real date is more than 90 days past the fixed date, the TTL monitor can delete rows in the middle of a test. That gives intermittent failures, for example in `test_a_finished_job_keeps_its_times_and_a_datetime_for_the_ttl` (`test_service_desk_worker.py` around line 230) and in the hand-off gap assertions.
- The 100-day-old row in `test_service_desk_knowledge_gaps.py` can also vanish silently. The test then still passes, but it no longer exercises the filter it claims to cover.

**Fix:** Do one of the following, and keep the dedicated migration/index test for the indexes themselves:
- Don't create the TTL indexes in these fixtures.
- Derive the test clock once per module from the real time: `datetime.now(timezone.utc).replace(microsecond=0)`.

### WR-302: The migration-number assertion breaks as soon as migration 033 ships

**File:** `backend/tests/test_service_desk_worker.py:314`

**Issue:** `test_the_runner_finds_migration_032_and_it_follows_031` asserts `max(found) == "032"`. That is a property of the repository at one moment, not of migration 032, and it compares migration numbers as strings.

**Fix:** Keep `found["032"] == "032_service_desk"` and `"031" in found`, and drop the `max` line.

### WR-303: The claim that `--sets` makes no database connection is not actually tested

**File:** `backend/tests/test_service_desk_eval_script.py:303-307`

**Issue:**
- The test only deletes `MONGODB_URL` and `MONGO_URI` and checks that "not reachable" is absent from stderr. If `--sets` connected to the default `mongodb://localhost:27017` (the live mongod on this VM) and succeeded, nothing would fail.
- `MONGODB_URI` is not deleted.
- `assert 1 <= stand_in.generates <= len(...)` (around line 205) is loose.

**Fix:** Patch the script's client factory, or `motor.motor_asyncio.AsyncIOMotorClient`, to raise. Assert exit 0, and delete `MONGODB_URI` as well.

## Info

### IN-301: The Mongo test URL default (127.0.0.1:27017) is duplicated in two places

**Files:** `backend/tests/test_service_desk_eval_script.py:35`, and `backend/tests/_mongo_test_db.py:13` (outside this area; listed for context)

**Issue:**
- Both default to the live mongod's port. Per-test unique database names keep the data safe.
- The eval-script test re-reads `MONGO_TEST_URL` instead of importing `_mongo_test_db._URL`, so the two defaults can drift apart.
- Several `--calibrate ... --mongo` calls (lines 205, 311 and 336) omit `--db-name`.

**Fix:** Import the shared URL and always pass `--db-name mongo_db.name`.

### IN-302: The injection test's output-check pass is partly circular

**File:** `backend/tests/test_service_desk_injection.py:57-67, 112`

**Issue:**
- `_problems` re-runs the production `check()` on text the pipeline already accepted with that same function. The independent regex (`https?:|www\.|@`) is the real leak check.
- Line 112 only shows that at least one case reaches the output check.

**Fix:** Optionally, for every case whose `compliant_reply` carries a link, address or command, assert that the outcome is either a hand-off or `output_check_failed`.

### IN-303: An order-tolerant assertion hides the worker's ordering

**File:** `backend/tests/test_service_desk_worker.py:69`

**Issue:** `counts["jobs"] == [a, b, c] or ... == [a, c, b]` accepts either order.

**Fix:** Assert the one order the worker defines.

---

_Reviewed: 2026-11-09 · Reviewer: gsd-code-reviewer (area 3 of 4) · Depth: standard · Written to disk by the orchestrator from the reviewer's returned report (the reviewer's own instructions forbade writing files)._

---

## Area 4: UI, services, tray scripts, tray.rs, Cargo version lines


**Reviewed:** 2026-11-09
**Depth:** standard (phase diff `fbb6e263f..HEAD`; user WIP hunks in `InternalTicketsDashboard.tsx`, `Cargo.toml`, `Cargo.lock` excluded)
**Status:** issues_found

## Summary

The tray scripts never evaluate server text (no `Invoke-Expression`, no `iex`, text goes into `.Text` properties only), and the routes, field names, limits and timings match `backend/service_desk/tray_contract.py`. The new panels (`RequesterAnswerPanel`, `TicketDraftPanel`, `CitedArticles`) render server text as plain React text, and none of the reviewed components uses `dangerouslySetInnerHTML`. The service layer is thin and consistent.

The main defect is on the requester side of the ticket screen. The comment list in `InternalTicketsDashboard.tsx` hides only `ai_draft` comments, and only once the desk view has loaded. Staff-only comments are never hidden. The remaining findings are one tray telemetry bug, one half-wired "Open ticket" link, a few copy-contract leaks and some client/server validation drift.

Not fully verified (context budget): the test files, `DeskModeGroup.tsx`, `HelpDeskToggle.tsx`, `DeskDialogs.tsx` and `StarterArticlesDialog.tsx` were only skimmed with pattern greps. The bulk of `serviceDeskCopy.ts` was not read line by line.

## Critical Issues

### CR-401: Requester's comment list renders staff-only comments and, while the desk view is loading or failed, unsent AI drafts

**File:** `components/InternalTicketsDashboard.tsx:1385`
**Issue:** The comments list is `(selected.comments || []).filter(c => !(deskView?.isRequester && c.kind === 'ai_draft')).map(...)`. This has two holes, which breaks the phase rule that the requester UI must not render staff-only text.
1. Only `ai_draft` is filtered. Every other comment that is not requester-visible (`visibility` missing or `'staff'`, which is the default per `CommentVisibility`) is still rendered to the person who raised the ticket. `CommentMarks` and `CommentBody` mark requester-visible comments, but nothing hides the rest. The `Comment` type added in this phase carries `visibility`, so the client has what it needs.
2. The filter fails open. `deskView` is `null` on first render of each ticket (`setDeskView(null)` in the effect at about line 561) and again whenever `fetchTicketDesk` fails (`catch { setDeskView(null) }`). In both cases `deskView?.isRequester` is `undefined`, so an unsent AI draft is shown to the requester.

I checked the generic ticket read path. `backend/tickets_endpoints.py` has no comment projection for the reporter, and the `projection.is_reporter` / `requester_view` calls appear only in `service_desk_endpoints.py`. So the full ticket JSON reaches the browser (backend part of this is outside area 4, please cross-check in the area covering `tickets_endpoints.py`). The UI is therefore the only barrier here, and it is incomplete.
**Fix:**
```tsx
// Decide "is this viewer the requester" from the ticket itself as well, so the first paint and a failed desk read stay closed.
const viewerIsReporter = deskView?.isRequester === true
  || (deskView === null && (selected.reporter || '').toLowerCase() === userEmail.toLowerCase());
const visibleComments = (selected.comments || []).filter(c =>
  !viewerIsReporter || (c.kind !== 'ai_draft' && c.visibility === 'requester'));
```
Also strip `ai_draft` and non-requester comments from `GET /api/tickets/{id}` and the list endpoint for the reporter on the server, so the browser never receives them.

## Warnings

### WR-401: Tray reports an empty `client.version` on every ticket (`agent_version` is never written to tray-config.json)

**File:** `agent-install/omni-agent-rs/scripts/tray_icon.ps1:204`
**Issue:** The script sends `version = [string]$cfg.agent_version`. `write_tray_config` in `agent-install/omni-agent-rs/src/config.rs:174-199` writes `api_base_url, agent_id, agent_token, chat_ui, accept_invalid_certs, server_cert_der_b64, enrolled, enrollment_problem` and no `agent_version`. `$cfg.agent_version` is therefore always `$null`, and the contract field `client.version` is always `""`. The server cannot tell which tray raised the ticket, which is the purpose of the field.
**Fix:** Add `"agent_version": env!("CARGO_PKG_VERSION")` to the JSON in `write_tray_config`. `$cfg` is refreshed from this file by `Sync-TrayConfig`, so no script change is needed.

### WR-402: "Open ticket {number}" on a desk row drops the ticket id and only opens the Tickets screen

**File:** `components/AutonomousOpsRowActions.tsx:57` (caller `DeskTicketLink`, same file)
**Issue:** `DeskTicketLink` calls `open(row.ticketId ?? null)`. The handler built at line 57 is `out.internalTickets = () => go('internalTickets')`, which discards the argument. The control is labelled "Open ticket TKT-123" but lands on the unfiltered Tickets list. The code comment admits the screen does not accept an intent yet, so the link promises something it cannot do.
**Fix:** Either pass the id through the opener and have `InternalTicketsDashboard` select it, or use a label that does not promise a specific ticket until the intent exists. Add a test that pins the chosen behavior.

### WR-403: Unanswered "My tickets" window ignores a clicked balloon while the window is already open

**File:** `agent-install/omni-agent-rs/scripts/tray_my_tickets.ps1:268` (caller at line 171-177)
**Issue:** `Show-MyTickets` returns immediately when `$watch.WindowOpen` is true. A balloon click for a different ticket then does nothing: the user clicks "Your ticket has an answer" and nothing happens. `PendingTicketId` has already been cleared, so there is no retry.
**Fix:** Keep a reference to the open form in `$script:TicketWatch` and, when `$selectId` is given, bring it to front and re-run `$ui.Load $selectId $false` instead of returning silently.

### WR-404: Draft panel decides "already handled" by comparing the server's text to a copy string

**File:** `components/serviceDesk/TicketDraftPanel.tsx:111`
**Issue:** `message === DRAFT_PANEL.alreadyHandled.replace(/[.\s]+$/, '')` ties client behavior to the exact wording of `messages.py` ("This draft was already handled."). Any server copy change, or a language change, silently turns the friendly handled state into a red error. 409 with another reason (closed ticket, person already replied) is correctly distinguished only by this string match.
**Fix:** Have the server send a machine code (for example `{detail, code: "already_handled"}`) and compare the code. Failing that, treat any 409 as "handled elsewhere", re-read the ticket and show the server's text unchanged.

### WR-405: Word editor accepts words the server refuses (leading space, hyphen, apostrophe, `&`, `/`, `.`)

**File:** `components/serviceDesk/DeskWords.tsx:12-13`
**Issue:** The client rule is `^[\p{L}\p{N} '\-&/.]+$`. The server rule at `backend/service_desk/settings.py:88` is `^[^\W_](?:[^\W_]|[ \-'&/.])*$`, so the first character must be a letter or digit. A word such as `-vpn` or `.net` passes the client, is staged and then fails the save with a 422. The comment says "the server's rule" and it is not.
**Fix:** Use `/^[\p{L}\p{N}][\p{L}\p{N} '\-&/.]*$/u` and add a test case for a leading punctuation character.

## Info

### IN-401: Hard-coded user-visible strings outside `serviceDeskCopy.ts`

**File:** `components/serviceDesk/TicketDraftPanel.tsx:84-85` (`'you'`), `components/serviceDesk/ReplyVisibilityPicker.tsx:56` (`'The requester'`), `components/serviceDesk/DeskSettingsCard.tsx` (`formatTypical`: `' s'`, `' min'`), `components/InternalTicketsDashboard.tsx` (placeholder `'Add a comment… (Enter to send, @ to mention)'`, pre-existing)
**Issue:** The phase rule is that every user-visible string comes from `serviceDeskCopy.ts`, and these slip through. The tray scripts also hard-code balloon title, window labels, the "AI-assisted answer from your IT knowledge base" mark and the `Based on:` prefix, which is the "fixed labels live in the script" allowance, but the balloon title (`'Your ticket has an answer'`), the done and error lines (`'Thanks. Your ticket is marked resolved.'`, `'Sent to IT. A person will take over.'`) are display strings the contract says should come from the server.
**Fix:** Move the three TS strings into the copy file. For the tray, either accept the labels as fixed or return the two done lines in `display`.

### IN-402: Redundant length check and stale doc comment

**File:** `components/serviceDesk/TicketDraftPanel.tsx:100`, `services/serviceDesk/knowledgeApi.ts` (`patchArticle` doc comment)
**Issue:** `text.length > max || trimmed.length > max` is redundant, because `trimmed.length <= text.length`. The `patchArticle` comment says the changeable keys include "text", but the type and the backend `DocPatch` use `content`.
**Fix:** Drop the second operand and change "text" to "content" in the comment.

### IN-403: `postTicketComment` returns `Promise<any>`

**File:** `services/serviceDesk/ticketApi.ts` (`postTicketComment`)
**Issue:** The result is assigned to `setSelected(t)` in `InternalTicketsDashboard.tsx:595`, so a shape change on the server is invisible to the compiler.
**Fix:** Type it as the dashboard's `Ticket` (export the interface) instead of `any`.

---

_Reviewed: 2026-11-09_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
