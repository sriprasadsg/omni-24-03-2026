---
status: diagnosed
phase: 88-plan-based-licensing-network-enrollment-rules
source: [88-01-SUMMARY.md, 88-02-SUMMARY.md, 88-03-SUMMARY.md, 88-04-SUMMARY.md, 88-05-SUMMARY.md, 88-06-SUMMARY.md, 88-07-SUMMARY.md, 88-08-SUMMARY.md, 88-09-SUMMARY.md, 88-10-SUMMARY.md, 88-11-SUMMARY.md, 88-12-SUMMARY.md, 88-13-SUMMARY.md, 88-14-SUMMARY.md, 88-15-SUMMARY.md, 88-16-SUMMARY.md]
started: 2026-11-19T14:38:10Z
updated: 2026-11-19T15:04:24.426Z
---

## Current Test

[testing complete]

## Tests

### 1. Cold Start Smoke Test
expected: Stop the backend, start it from scratch: it boots without errors, the migration runner reports migrations up to date (034 already applied), and /api/health plus a real query (Tenant Management's tenant list) answer with live data. Evidence so far: restart 2026-11-19 14:32:17, health 200 after ~23 s, no errors in the log.
result: pass
source: server-evidence
evidence: "Backend restarted 2026-11-19 14:04:45 and 14:32:17, health 200 within 14-23 s, no errors in the journal; Tenant Management then listed the live tenants (Exafluence 0/50 Pro, ABC 1/5 Free, shieldforgetech 0/5 Free) in the headless run."

### 2. Plans dialog in Tenant Management (Super Admin)
expected: Tenant Management shows the Plans button; the dialog lists Free, Pro, Enterprise and Custom with their seats, trial days and screens, disabled/marked boxes and the Custom seats field read well in the Spatial Glass UI; changing a plan's seats and saving reports the tenants updated, and a direct tenant without an override (shieldforgetech) shows the new limit in Manage Tenant; revert afterwards. (88-12 D5, 88-16 check 1)
result: pass
source: claude-headless
evidence: "Plans dialog: Free 5 seats / 14 trial days / 19 of 209 screens, Pro 50, Enterprise 500, Custom 'Set per tenant by contract'. Free 5 -> 6 showed the effect note and 'Saved. 2 tenants updated.'; shieldforgetech's licence panel read '0 of 6 seats in use'; reverted to 5 ('Saved. 2 tenants updated.'), then plans and tenants matched the snapshot exactly. Looks right in dark and light."

### 3. Your plan card on ABC's Agents screen
expected: As ABC's tenant admin, the Agents screen shows a read-only 'Your plan' card: Free, days left on the trial (ends 25 Nov), seats used of 5, the allowed network 115.245.47.74/32 with its source, no input or button; it looks right in dark and light themes. As the Platform (exempt) the card does not appear. (88-13 D3, D7, 88-16 check 2)
result: pass
source: claude-headless
evidence: "ABC admin: 'Your plan Free, 1 of 5 seats used, 6 days left in your free trial, Allowed networks 115.245.47.74 (migrated), Computers enrolling from any other network wait for approval.' No input or button in the card; fits in dark and light. The Platform (exempt) shows no card."

### 4. Licence panels show networks and the new fields
expected: Manage Tenant's licence panel (Super Admin) and the partner's customer panel list the allowed networks with their source, read-only; the plan, seats override and trial fields show; saving the existing fields still works; the trial/seat reminder wording reads well to a tenant admin and to a partner. (88-06 D6, 88-13 D6)
result: pass
source: claude-headless
evidence: "Manage Tenant > ABC licence panel: Plan Free 5 seats, Limit 5, trial ends Nov 25 (6 days left) with Extend, Allowed networks '115.245.47.74/32 (migrated)' read-only, Save license disabled with nothing changed; dark and light. The 7-day reminder reached ABC and the Platform: 'Free trial of ABC ends in 7 days / ... After that, new agents are held for approval; running agents and every screen keep working.' The partner customer panel and the partner's reminder were not seen: no partner organization exists on the live server (vitest covers them)."

### 5. Pending agents: holds, network range and moved agents
expected: Pending agents (Super Admin): each hold reads plainly (new network, seat limit, moved agent, trial ended); Allow network takes an optional range and refuses a bad one inline; a cross-tenant move needs a confirmation; bulk approve confirms moves and new networks first; the Moved agents list with Restore shows even when nothing waits; the controls fit the dense table. A tenant admin sees the holds without controls or other organizations. (88-14, all six deliverables; its coverage block is malformed, so none could auto-pass)
result: issue
reported: "Claude (headless run): the refusal for a bad range reads 'Couldn't allow this network: widenTo may be at most a /24 (IPv4). Try again.', showing the API field name widenTo to the decider; for 10.0.0.0/8 it also does not say the range must contain 135.237.98.107. Everything else seen works: the hold reads plainly for ABC's admin with no controls and no other organization, the decider gets the range field with its help, the 422 is inline and the typed range stays for the retry. Cross-tenant move, bulk approve and the Moved agents list could not be exercised live (no moved agents; the list renders nothing when empty) and rest on PendingAgentsPanel/PendingMovedAgents tests (51 pass)."
severity: minor

### 6. New network enrollment end to end
expected: A test machine for ABC enrolls from a different public address: ABC's admin sees 'New network <ip>, waiting for platform approval' with no approve button; the Super Admin approves with a range; the nginx client address of that register call equals the stored sourceIp. (88-16 check 3)
result: pass
source: claude-headless
evidence: "Test machine UAT88-NET-TEST enrolled for ABC through 135.237.98.107 (this server's public address): 202 pending new_network, stored sourceIp 135.237.98.107 = nginx client address of that register call. ABC's admin saw 'New network 135.237.98.107, waiting for platform approval' with no control. The Super Admin approved with 135.237.98.104/29: HTTP 200, ABC's networks gained it (source approved), the machine was admitted. The success toast was not captured live (its text 'Approved. <range> is now an allowed network.' is asserted by PendingAgentsPanel.test.tsx). Machine, network, notices and seat count then restored."

### 7. Partner portal plan column, plan modal and screen picker
expected: In the partner portal the Plan column shows each customer's plan, an open trial end, an ended trial in amber, a dash with no plan; admins get 'Plan and trial', viewers do not; the table fits 1280 px with the sidebar open. The customer screen picker greys screens outside the plan with one shared note and keeps held screens locked; a Free customer's ~190 greyed rows stay readable. (88-10 D5, 88-15 D2, D5)
result: blocked
blocked_by: other
reason: "No partner organization exists on the live server, so the partner portal Plan column, plan modal and the partner screen picker cannot be seen; their behaviour rests on PartnerPlanModal / PartnerScreenPicker tests."

### 8. Go-live check output reads well
expected: backend/scripts/check_plan_golive.py prints one line per tenant (plan, seats, override, trial end, networks), then FAIL lines or OK, and exits 1 on a failure; the 2026-11-19 run in 88-16-SUMMARY.md is the output to judge (its one FAIL is the roaming laptop EILT0197). (88-11 D5)
result: pass
source: server-evidence
evidence: "check_plan_golive.py on 2026-11-19 printed one line per tenant (plan, maxAgents, override, trial end, networks), then one FAIL line, and exited 1, as specified (output in 88-16-SUMMARY.md)."

### 9. 88-01 D1: Create on a plan stores seats and trial from the plan table; explicit maxAgents is a seatOverride; Custom without seats and unknown plans an
expected: Create on a plan stores seats and trial from the plan table; explicit maxAgents is a seatOverride; Custom without seats and unknown plans answer 422
result: pass
source: automated
coverage_id: 88-01-D1

### 10. 88-01 D2: After the Free trial ends a new machine is held Pending trial_ended while the enrolled machine re-registers 200 and keeps its seat; platform
expected: After the Free trial ends a new machine is held Pending trial_ended while the enrolled machine re-registers 200 and keeps its seat; platform-admin and missing data are never held
result: pass
source: automated
coverage_id: 88-01-D2

### 11. 88-01 D3: Licence view carries plan, planSeats, seatOverride, partnerManaged, exempt, trial and projected allowedNetworks; daysLeft rounds up and neve
expected: Licence view carries plan, planSeats, seatOverride, partnerManaged, exempt, trial and projected allowedNetworks; daysLeft rounds up and never goes below 0
result: pass
source: automated
coverage_id: 88-01-D3

### 12. 88-02 D1: A plan's seat number reaches direct tenants without an override at once and never a partner customer, the platform or an override; overrides
expected: A plan's seat number reaches direct tenants without an override at once and never a partner customer, the platform or an override; overrides (including one equal to the plan's number) survive plan edits; seat numbers are strict whole numbers 0..1,000,000
result: pass
source: automated
coverage_id: 88-02-D1

### 13. 88-02 D2: Lowering a plan keeps running agents and holds only new machines; the seat boundary at enrollment; platform-admin has no limit; 20 racing cl
expected: Lowering a plan keeps running agents and holds only new machines; the seat boundary at enrollment; platform-admin has no limit; 20 racing claims against a plan edit stay within 5..8
result: pass
source: automated
coverage_id: 88-02-D2

### 14. 88-02 D3: Approve-and-raise on a direct tenant stores the override and announces seats.changed (ledger plus admin notice); a partner customer still go
expected: Approve-and-raise on a direct tenant stores the override and announces seats.changed (ledger plus admin notice); a partner customer still goes through the pool; moves between direct and partner set or drop the override
result: pass
source: automated
coverage_id: 88-02-D3

### 15. 88-03 D1: The D-29 seed is generated by a committed script, ships as shared/plan-screen-seed.json with 19/88/208 keys, nested Free within Pro within E
expected: The D-29 seed is generated by a committed script, ships as shared/plan-screen-seed.json with 19/88/208 keys, nested Free within Pro within Enterprise, and the committed file equals the script output byte for byte
result: pass
source: automated
coverage_id: 88-03-D1

### 16. 88-03 D2: final_screens refuses a screen outside any limit with its code, 'all'/unknown with invalid_screen, a missing parent with missing_parent; kee
expected: final_screens refuses a screen outside any limit with its code, 'all'/unknown with invalid_screen, a missing parent with missing_parent; keeps screens already on; sticky screens stay; order is submitted, sticky, missing start
result: pass
source: automated
coverage_id: 88-03-D2

### 17. 88-03 D3: plan_allowed follows the stored plans document at once, falls back to the seed, and Custom or the platform organization allow every switch
expected: plan_allowed follows the stored plans document at once, falls back to the seed, and Custom or the platform organization allow every switch
result: pass
source: automated
coverage_id: 88-03-D3

### 18. 88-03 D4: A partner's customer gets only screens inside both the partner ceiling and its plan; the features answer carries plan and planScreens
expected: A partner's customer gets only screens inside both the partner ceiling and its plan; the features answer carries plan and planScreens
result: pass
source: automated
coverage_id: 88-03-D4

### 19. 88-04 D1: change_plan: one compare-and-set, seat rule (direct tenant without override takes the plan's seats; override and partner allotment kept; Cus
expected: change_plan: one compare-and-set, seat rule (direct tenant without override takes the plan's seats; override and partner allotment kept; Custom keeps the number as override), consumed trial only when no trial record, plan.changed audit and admin notice (and seats.changed when the number moved), platform refused 409, unknown plan 422, same plan in any case writes nothing, concurrent changes end with one winner and one 409 plan_changed
result: pass
source: automated
coverage_id: 88-04-D1

### 20. 88-04 D2: change_plan with a partner: only that partner's customer (404 otherwise), plan inside partner.planCeiling (absent: Free only, 422 plan_outsi
expected: change_plan with a partner: only that partner's customer (404 otherwise), plan inside partner.planCeiling (absent: Free only, 422 plan_outside_ceiling), partner.customer_plan_changed audit
result: pass
source: automated
coverage_id: 88-04-D2

### 21. 88-04 D3: Super Admin PATCH and create: a plan goes through change_plan, screens are checked against the new plan only (422 screen_outside_plan, nothi
expected: Super Admin PATCH and create: a plan goes through change_plan, screens are checked against the new plan only (422 screen_outside_plan, nothing stored, plan unchanged), screens already on may stay, billable service: add-ons pass through, platform organization and Custom allow every switch, a partner's ceiling does not limit the Super Admin, a tenant admin still gets 403
result: pass
source: automated
coverage_id: 88-04-D3

### 22. 88-04 D4: Payment route: subscribe validates the plan (Free, Pro, Enterprise in any case; Custom, unknown, over-long answer 422 before the gateway), s
expected: Payment route: subscribe validates the plan (Free, Pro, Enterprise in any case; Custom, unknown, over-long answer 422 before the gateway), stores the canonical name and leaves the tenant's plan; cancel leaves the plan
result: pass
source: automated
coverage_id: 88-04-D4

### 23. 88-04 D5: Only plan_service.py writes subscriptionTier (AST scan over backend/ top level, with a self-test for $set, $setOnInsert, subscript assignmen
expected: Only plan_service.py writes subscriptionTier (AST scan over backend/ top level, with a self-test for $set, $setOnInsert, subscript assignment versus insert literal, filter and projection)
result: pass
source: automated
coverage_id: 88-04-D5

### 24. 88-05 D1: The network decision uses only the server-observed address: uvicorn's trusted-proxy handling resolves the appended address for 127.0.0.1 and
expected: The network decision uses only the server-observed address: uvicorn's trusted-proxy handling resolves the appended address for 127.0.0.1 and ::1 peers and ignores the header from others; the rule modules hold no header name and never the agent's own address claim
result: pass
source: automated
coverage_id: 88-05-D1

### 25. 88-05 D2: The first machine teaches the tenant a /32 (/128) learned network, a new machine from another address is held new_network with its sourceIp 
expected: The first machine teaches the tenant a /32 (/128) learned network, a new machine from another address is held new_network with its sourceIp and a readable tenant notice, enrolled agents are never re-checked, the platform is exempt, a missing address is held and never learned, IPv4-mapped addresses compare as IPv4, concurrent first enrollments leave one network
result: pass
source: automated
coverage_id: 88-05-D2

### 26. 88-05 D3: A platform decider approving a new_network hold allows the observed address or a validated widenTo (at most /24 or /48, containing the addre
expected: A platform decider approving a new_network hold allows the observed address or a validated widenTo (at most /24 or /48, containing the address, same version, no private range for a public address); bad ranges answer 422 and change nothing; a tenant admin gets 403; no free seat adds no network; bulk approve allows the exact address; duplicates and the 100-entry cap add nothing
result: pass
source: automated
coverage_id: 88-05-D3

### 27. 88-06 D1: Trial extension from the licence PATCH: later of now and the old end plus N days (1..365), reminders cleared, extension recorded with at/by/
expected: Trial extension from the licence PATCH: later of now and the old end plus N days (1..365), reminders cleared, extension recorded with at/by/days/from/to, trial.extended in the ledger, ended trial reopens from now, no trial record starts one; refused 422 not_on_trial for a paid plan or the platform organization with nothing written; concurrent extensions never lose one silently; a Tenant Admin gets 403
result: pass
source: automated
coverage_id: 88-06-D1

### 28. 88-06 D2: clearSeatOverride returns a direct tenant to its plan's seats (override removed, license and legacy maxAgents written, seats.changed announc
expected: clearSeatOverride returns a direct tenant to its plan's seats (override removed, license and legacy maxAgents written, seats.changed announced); refused 409 for a partner customer and 422 for Custom; a maxAgents set on a direct tenant is stored as the override and announced as seats.changed; a PATCH that moves no seats announces nothing
result: pass
source: automated
coverage_id: 88-06-D2

### 29. 88-06 D3: Approving a self sign-up starts its Free trial (plan's trialDays) and sets its seats from the Free plan; calling again changes nothing; a fa
expected: Approving a self sign-up starts its Free trial (plan's trialDays) and sets its seats from the Free plan; calling again changes nothing; a failing start never undoes the approval; paid plans and tenants that already have a trial are left alone
result: pass
source: automated
coverage_id: 88-06-D3

### 30. 88-06 D4: Hourly reminders at 7 and 1 days, once per threshold, to the platform feed and the tenant's admins (audience tag), and for a partner's custo
expected: Hourly reminders at 7 and 1 days, once per threshold, to the platform feed and the tenant's admins (audience tag), and for a partner's customer also to the partner's own feed without an audience tag, which notification_audience.reader_filter lets a partner_admin read; none for paid, consumed, ended, platform or far-off trials; re-armed by an extension; license_seat_tick runs the step even when an earlier step raises
result: pass
source: automated
coverage_id: 88-06-D4

### 31. 88-06 D5: D-20/D-21/D-22: a trial_ended hold is approved like any hold and the trial stays ended; an ended trial changes no agent status and no enable
expected: D-20/D-21/D-22: a trial_ended hold is approved like any hold and the trial stays ended; an ended trial changes no agent status and no enabledFeatures; a tenant back on Free after a paid plan has its next new machine held trial_ended
result: pass
source: automated
coverage_id: 88-06-D5

### 32. 88-07 D1: A machine whose serial or SMBIOS UUID belongs to a seat-holding agent in another tenant seen in the last 24 hours is held Pending cross_tena
expected: A machine whose serial or SMBIOS UUID belongs to a seat-holding agent in another tenant seen in the last 24 hours is held Pending cross_tenant_duplicate (new machine and returning agent needing a seat, platform organization included); old builds get a 403 starting cross_tenant_duplicate:
result: pass
source: automated
coverage_id: 88-07-D1

### 33. 88-07 D2: A silent copy (30 h), a seat-less copy, a same-tenant copy, a MAC alone, nothing, and OEM placeholder serials never cause the hold; serial a
expected: A silent copy (30 h), a seat-less copy, a same-tenant copy, a MAC alone, nothing, and OEM placeholder serials never cause the hold; serial and UUID are compared after normalization
result: pass
source: automated
coverage_id: 88-07-D2

### 34. 88-07 D3: While held, tenant A gets no notice and no change; B's feed and refusal text carry the fixed unnamed sentence with neither A's name, id, age
expected: While held, tenant A gets no notice and no change; B's feed and refusal text carry the fixed unnamed sentence with neither A's name, id, agent id nor hostname; the platform feed alert and the crossTenant field name both
result: pass
source: automated
coverage_id: 88-07-D3

### 35. 88-07 D4: A silent copy elsewhere is retired by the new enrollment: Replaced, replacedReason moved_silent, no replacedBy, seat released, tokens revoke
expected: A silent copy elsewhere is retired by the new enrollment: Replaced, replacedReason moved_silent, no replacedBy, seat released, tokens revoked, platform notice and platform-ledger entry naming both, and an old-tenant ledger entry naming neither; a second retirement changes nothing
result: pass
source: automated
coverage_id: 88-07-D4

### 36. 88-07 D5: The hold runs before the allowlist and network rules, so a duplicate on a new network teaches no network; two sparse indexes serve the looku
expected: The hold runs before the allowlist and network rules, so a duplicate on a new network teaches no network; two sparse indexes serve the lookup (explain shows IXSCAN, no COLLSCAN)
result: pass
source: automated
coverage_id: 88-07-D5

### 37. 88-08 D1: list_plans: Free, Pro, Enterprise, Custom in order with seats, trialDays, screens (stored list, the seed, or 'all' for Custom), tenantCount 
expected: list_plans: Free, Pro, Enterprise, Custom in order with seats, trialDays, screens (stored list, the seed, or 'all' for Custom), tenantCount (missing plan counts as Free; platform and partner organizations excluded), updatedAt, updatedBy
result: pass
source: automated
coverage_id: 88-08-D1

### 38. 88-08 D2: update_plan seats: stored, applied at once through licensing.apply_plan_seats to direct tenants without an override (override, partner custo
expected: update_plan seats: stored, applied at once through licensing.apply_plan_seats to direct tenants without an override (override, partner customer and platform untouched), one seats.changed notice per changed tenant via plan_edit, one plan.updated ledger entry with before and after; the same edit again writes, notifies and records nothing; bounds 0 and 1,000,000 accepted, -1, 1,000,001, float, bool, string refused with nothing stored
result: pass
source: automated
coverage_id: 88-08-D2

### 39. 88-08 D3: Screens and trial days shape only the future: a trialDays edit leaves a running trial's endsAt and applies to the next new_tenant_terms; scr
expected: Screens and trial days shape only the future: a trialDays edit leaves a running trial's endsAt and applies to the next new_tenant_terms; screens are stored in submitted order de-duplicated, an empty list is kept, 'all' and unknown keys refused, no tenant's enabledFeatures changes; Custom 422 custom_is_per_tenant, trialDays outside Free 422, empty body 422 nothing_to_update
result: pass
source: automated
coverage_id: 88-08-D3

### 40. 88-08 D4: Plans API: only the Super Admin reads or edits (platform support and tenant admin get 403 in the handler); the body refuses unknown fields a
expected: Plans API: only the Super Admin reads or edits (platform support and tenant admin get 403 in the handler); the body refuses unknown fields and non-integer or out-of-range numbers; PlanError becomes a JSON body with the status; the real mounted app lists both routes tagged tenantManagement, authenticated as user
result: pass
source: automated
coverage_id: 88-08-D4

### 41. 88-09 D1: Approving a cross_tenant_duplicate hold admits the machine in the new tenant first and then retires every seat-holding copy elsewhere (Repla
expected: Approving a cross_tenant_duplicate hold admits the machine in the new tenant first and then retires every seat-holding copy elsewhere (Replaced, moved, seat released, tokens revoked, no replacedBy); with no free seat the answer is 409 no_free_seat and the old copy is untouched
result: pass
source: automated
coverage_id: 88-09-D1

### 42. 88-09 D2: Approving a hold for any other reason re-checks the machine: live elsewhere turns it into cross_tenant_duplicate with its platform-only deta
expected: Approving a hold for any other reason re-checks the machine: live elsewhere turns it into cross_tenant_duplicate with its platform-only detail and answers 409 reason_changed, admitting nothing and raising no limit; otherwise silent copies elsewhere are retired as moved_silent
result: pass
source: automated
coverage_id: 88-09-D2

### 43. 88-09 D3: Rejecting a cross_tenant_duplicate hold denylists nothing; the tenant's Pending list never carries crossTenant, the other organization's nam
expected: Rejecting a cross_tenant_duplicate hold denylists nothing; the tenant's Pending list never carries crossTenant, the other organization's name, id, agent id or hostname, and the platform list does
result: pass
source: automated
coverage_id: 88-09-D3

### 44. 88-09 D4: A heartbeat from an agent retired because its computer moved answers 403 agent_replaced and claims no seat; a returning agent whose computer
expected: A heartbeat from an agent retired because its computer moved answers 403 agent_replaced and claims no seat; a returning agent whose computer is live elsewhere is held cross_tenant_duplicate instead of taking a seat
result: pass
source: automated
coverage_id: 88-09-D4

### 45. 88-09 D5: The Super Admin lists moved agents and restores one to Inactive, recorded in the platform ledger and the agent's own tenant ledger without t
expected: The Super Admin lists moved agents and restores one to Inactive, recorded in the platform ledger and the agent's own tenant ledger without the other organization's name; non-moved, unknown and tenant-admin requests are refused (409, 404, 403); the two routes are recorded as exempt platform routes (ratchet 31)
result: pass
source: automated
coverage_id: 88-09-D5

### 46. 88-09 D6: The hourly licence tick posts one platform notice per serial or SMBIOS UUID held by seat-holding agents seen in the last 24 hours in two or 
expected: The hourly licence tick posts one platform notice per serial or SMBIOS UUID held by seat-holding agents seen in the last 24 hours in two or more tenants, once per key per day, and still runs when an earlier step raises
result: pass
source: automated
coverage_id: 88-09-D6

### 47. 88-10 D1: Super Admin sets partner.planCeiling on appoint and edit: canonical keys de-duplicated in order, default ['Free'], 422 invalid_plan with not
expected: Super Admin sets partner.planCeiling on appoint and edit: canonical keys de-duplicated in order, default ['Free'], 422 invalid_plan with nothing written, change recorded on partner and platform ledgers, same list records nothing, empty list allowed, partner_summary.planCeiling (Free for an old document)
result: pass
source: automated
coverage_id: 88-10-D1

### 48. 88-10 D2: Partner customer creation: starts on Free with a 14-day trial and the allotment as seats (no override), or on another plan inside the ceilin
expected: Partner customer creation: starts on Free with a 14-day trial and the allotment as seats (no override), or on another plan inside the ceiling with a consumed trial; outside the ceiling 422 plan_outside_ceiling before the pool claim; unknown plan 422; old partner without a ceiling sells Free only; rows are exactly CUSTOMER_FIELDS ending plan, trialEndsAt; overview planCeiling
result: pass
source: automated
coverage_id: 88-10-D2

### 49. 88-10 D3: Partner admin changes its customer's plan inside the ceiling (seats unchanged, plan.changed and partner.customer_plan_changed on both ledger
expected: Partner admin changes its customer's plan inside the ceiling (seats unchanged, plan.changed and partner.customer_plan_changed on both ledgers); outside ceiling 422, empty ceiling 422, another partner's customer 404, viewer 403
result: pass
source: automated
coverage_id: 88-10-D3

### 50. 88-10 D4: Partner admin extends a Free customer's trial 1..365 days (trial.extended on the customer, partner.customer_trial_extended on the partner); 
expected: Partner admin extends a Free customer's trial 1..365 days (trial.extended on the customer, partner.customer_trial_extended on the partner); Pro customer 422 not_on_trial; 0 and 366 refused by the request model; foreign customer 404; viewer 403
result: pass
source: automated
coverage_id: 88-10-D4

### 51. 88-11 D1: Migration 034 stores the four plans (Free 5/14 days/Free seed, Pro 50, Enterprise 500, Custom no seats and screens 'all'); a plan document a
expected: Migration 034 stores the four plans (Free 5/14 days/Free seed, Pro 50, Enterprise 500, Custom no seats and screens 'all'); a plan document an administrator edited is never overwritten
result: pass
source: automated
coverage_id: 88-11-D1

### 52. 88-11 D2: Direct tenants take their plan's seats with the old number recorded first (license.maxAgentsBeforePlans) and one plan.seats_adopted entry ea
expected: Direct tenants take their plan's seats with the old number recorded first (license.maxAgentsBeforePlans) and one plan.seats_adopted entry each; the platform, partner customers and partner organizations keep their seats; a hand-set number or a Custom tenant keeps its number as license.seatOverride
result: pass
source: automated
coverage_id: 88-11-D2

### 53. 88-11 D3: Every tenant without a trial gets one (14-day Free trial from go-live, otherwise consumed); every tenant without allowed networks gets the p
expected: Every tenant without a trial gets one (14-day Free trial from go-live, otherwise consumed); every tenant without allowed networks gets the public addresses of its admitted agents; the platform and partner organizations are skipped; no tenant's enabledFeatures changes
result: pass
source: automated
coverage_id: 88-11-D3

### 54. 88-11 D4: The sparse hardware indexes exist after the migration and a second run changes no document and records no audit entry
expected: The sparse hardware indexes exist after the migration and a second run changes no document and records no audit entry
result: pass
source: automated
coverage_id: 88-11-D4

### 55. 88-12 D1: Plans dialog from Tenant Management lists Free, Pro, Enterprise and Custom with seats and tenant counts; saving sends PUT /api/platform/plan
expected: Plans dialog from Tenant Management lists Free, Pro, Enterprise and Custom with seats and tenant counts; saving sends PUT /api/platform/plans/{key} with only the changed fields and shows 'Saved. N tenants updated.'
result: pass
source: automated
coverage_id: 88-12-D1

### 56. 88-12 D2: Trial days editable on Free only; Custom read-only 'Set per tenant by contract'; effect-timing note (seats at once, screens future only, tri
expected: Trial days editable on Free only; Custom read-only 'Set per tenant by contract'; effect-timing note (seats at once, screens future only, trial days new trials only); 422 text shown and edits kept; non-whole seats not sent
result: pass
source: automated
coverage_id: 88-12-D2

### 57. 88-12 D3: Manage Tenant: choosing a plan ticks nothing; boxes outside the plan are disabled with 'Not part of the <plan> plan'; kept screens stay tick
expected: Manage Tenant: choosing a plan ticks nothing; boxes outside the plan are disabled with 'Not part of the <plan> plan'; kept screens stay ticked, marked 'outside plan', untickable; select all ticks only allowed switches; save still sends features and tier
result: pass
source: automated
coverage_id: 88-12-D3

### 58. 88-12 D4: Add Tenant opens on Free; Custom shows a required seats input and sends maxAgents; apiService.addTenant posts Free by default and forwards m
expected: Add Tenant opens on Free; Custom shows a required seats input and sends maxAgents; apiService.addTenant posts Free by default and forwards maxAgents
result: pass
source: automated
coverage_id: 88-12-D4

### 59. 88-13 D1: Tenant admin's Agents screen shows a read-only 'Your plan' card: plan, seats used of the limit with 'override' or 'set by your partner', day
expected: Tenant admin's Agents screen shows a read-only 'Your plan' card: plan, seats used of the limit with 'override' or 'set by your partner', days left on an open Free trial, the allowed networks with their source and an empty-state line; no input or button
result: pass
source: automated
coverage_id: 88-13-D1

### 60. 88-13 D2: After a Free trial ends the card says the trial has ended, new computers wait for approval and running agents and screens keep working
expected: After a Free trial ends the card says the trial has ended, new computers wait for approval and running agents and screens keep working
result: pass
source: automated
coverage_id: 88-13-D2

### 61. 88-13 D4: Manage Tenant licence panel shows 'Plan X: N seats' beside 'Limit N (override)', and 'Use plan number' sends PATCH {clearSeatOverride: true}
expected: Manage Tenant licence panel shows 'Plan X: N seats' beside 'Limit N (override)', and 'Use plan number' sends PATCH {clearSeatOverride: true} for a direct tenant with an override and then shows the plan number; absent for a partner customer
result: pass
source: automated
coverage_id: 88-13-D4

### 62. 88-13 D5: The licence panel shows the Free trial end and days left and extends by a whole number of days 1..365 through PATCH {trialExtendDays}; 0, 36
expected: The licence panel shows the Free trial end and days left and extends by a whole number of days 1..365 through PATCH {trialExtendDays}; 0, 366, 2.5 and empty disable Extend; a server refusal is shown
result: pass
source: automated
coverage_id: 88-13-D5

### 63. 88-15 D1: Super Admin's partner form has 'Plans this partner can sell' (Free ticked for a new partner, saved planCeiling shown on edit, Free when abse
expected: Super Admin's partner form has 'Plans this partner can sell' (Free ticked for a new partner, saved planCeiling shown on edit, Free when absent), sent as planCeiling on appoint and only when changed on edit; amber status when none is ticked; invalid_plan shows the stale-page sentence
result: pass
source: automated
coverage_id: 88-15-D1

### 64. 88-15 D3: PartnerPlanModal changes a customer's plan among the ceiling (current plan always listed), extends a Free trial 1..365 days, and words plan_
expected: PartnerPlanModal changes a customer's plan among the ceiling (current plan always listed), extends a Free trial 1..365 days, and words plan_outside_ceiling, unknown_plan, plan_changed, invalid_days, not_on_trial, trial_changed; refetches on any server answer
result: pass
source: automated
coverage_id: 88-15-D3

### 65. 88-15 D4: Create customer offers the partner's plans with Free selected (first plan when Free is outside the ceiling), sends plan, shows the empty-cei
expected: Create customer offers the partner's plans with Free selected (first plan when Free is outside the ceiling), sends plan, shows the empty-ceiling message with submit disabled, helper that screens outside the plan are refused
result: pass
source: automated
coverage_id: 88-15-D4

## Notes

- Run by Claude at the user's choice ("You run them"), headless Chromium on the live published build with temporary accounts uat88-super / uat88-abcadmin (MFA through the real flow), every change reverted and the accounts removed; evidence in ~/omni-archives/uat88/.
- Coverage blocks needing repair (their entries became human checks, never dropped): 88-13 D3/D6 (verification status not pass/fail/unknown), 88-14 (all six entries lack id/description and use kind: test).
- 88-16-SUMMARY.md has no plan_head_before (legacy commit claim; warning only). All other summaries reconcile.
- No browser MCP in this session: UI checkpoints: 0 auto-verified, 8 queued for manual review.

## Summary

total: 65
passed: 63
issues: 1
pending: 0
skipped: 0
blocked: 1

## Gaps

- gap_id: G-88-5
  truth: "A refused network range tells the decider in plain words why (at most a /24 for IPv4, /48 for IPv6; must contain the observed address), without API field names"
  status: failed
  reason: "Claude (headless run, at the user's choice): 'Couldn't allow this network: widenTo may be at most a /24 (IPv4). Try again.' shows the API field name widenTo"
  severity: minor
  test: 5
  root_cause: "backend/network_rules.py validate_widen() words its five refusals for the API caller, each starting with the request field name widenTo; pending_agents turns them into the 422 detail and the UI shows it verbatim (88-UI-SPEC line 360)"
  artifacts:
    - path: "backend/network_rules.py"
      issue: "EntryError messages at lines 91, 93, 96, 98, 100 begin with 'widenTo'"
  missing:
    - "Plain-word refusals naming the limit (/24 IPv4, /48 IPv6) or the observed address, never the field name"
    - "A test asserting no refusal contains 'widenTo'"
  debug_session: ".planning/debug/88-uat-range-refusal-wording.md"
