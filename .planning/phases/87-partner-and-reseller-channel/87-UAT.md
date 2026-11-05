---
status: testing
phase: 87-partner-and-reseller-channel
source: [87-01-SUMMARY.md, 87-02-SUMMARY.md, 87-03-SUMMARY.md, 87-04-SUMMARY.md, 87-05-SUMMARY.md, 87-06-SUMMARY.md, 87-07-SUMMARY.md, 87-08-SUMMARY.md, 87-09-SUMMARY.md, 87-10-SUMMARY.md, 87-11-SUMMARY.md, 87-12-SUMMARY.md, 87-13-SUMMARY.md, 87-14-SUMMARY.md, 87-15-SUMMARY.md]
started: 2026-11-04T07:11:12Z
updated: 2026-11-05T11:50:54Z
---

## Current Test
<!-- OVERWRITE each test - shows where we are -->

number: 5
name: Invite email and the Accept-invite page
expected: |
  Needs SMTP and FRONTEND_URL set, plus the UI published. The invited admin receives an email whose link opens /accept-invite; the token disappears from the address bar, the page names the organization, a password can be set, and the admin then signs in. A used or expired link says so instead of offering a form.
awaiting: user response

## Tests

### 1. Cold Start Smoke Test
expected: Restart the backend from scratch (sudo systemctl restart omni-backend), or confirm this morning's 07:04 restart. It is back within a minute, logs/backend.log shows no startup traceback, the migration ledger still ends at 029_partner_channel, /api/health returns 200, and signing in as Super Admin opens the Overview.
result: pass

### 2. Daily seat-pool repair runs in the live backend
expected: After the restart, logs/backend.log shows 'License seat maintenance loop started (reclaim hourly, reconcile daily)' with no 'License seat maintenance failed' line after it. Pool repair runs at startup and every 24 hours; once a partner exists, its handed-out count after a restart equals the total seats of its customers.
result: pass
note: "2026-11-05: after the 08:17 restart logs/backend.log shows the loop started at 08:17:50Z and no 'License seat maintenance failed' line since. No partner exists on live yet, so the handed-out count check waits for the first partner."
coverage_id: 87-03/D6

### 3. Appoint a partner from the Partners screen
expected: Needs the UI published. As Super Admin, Partners is in the sidebar. Appoint partner takes a name, seat pool, pool expiry, screen ceiling and first admin. The partner appears in the table with 0 handed out and the whole pool free. With email not configured on this VM, a 'Partner appointed' panel says the invite email couldn't be sent and tells you to set a password for the admin in User Management.
result: pass
note: "2026-11-05: passed on the release bundle, private copy: appointed QA Reseller (1,000,000 seats, all screens); the Partner appointed panel says the invite email could not be sent and to set a password in User Management; the table shows 0 of 1,000,000 handed out, 1,000,000 free. Found and fixed: the dialog opened with Enter a partner name. shown and focus on Close (shared Modal), and closing left focus on the page body."
coverage_id: 87-08/D8

### 4. Partners screen layout
expected: Needs the UI published. The Partners screen matches 87-UI-SPEC in light and dark: even spacing, stacked cards below 1024 px, the table scrolls sideways below 1280 px instead of squashing, and nothing overflows at 320 px.
result: pass
note: "2026-11-05: passed after a fix: light and dark at 1280, 1024, 640, 360 and 320 px with no page overflow; stacked cards below 1024. The table needed sideways scroll at 1280 px with the sidebar open (1,040 px of minimums in 922 px); minimums now sum to 900 px, so it fits open and closed."
coverage_id: 87-11/D5

### 5. Invite email and the Accept-invite page
expected: Needs SMTP and FRONTEND_URL set, plus the UI published. The invited admin receives an email whose link opens /accept-invite; the token disappears from the address bar, the page names the organization, a password can be set, and the admin then signs in. A used or expired link says so instead of offering a form.
result: [pending]
coverage_id: 87-06/D8

### 6. Accept-invite page with a long organization name
expected: Needs the UI published. On a phone-width window (360 px), a 100-character organization name wraps inside the card with no sideways scroll, and the card looks right in light and dark.
result: pass
note: "2026-11-05: passed on the release bundle: a 98-character organization name wraps inside the card at 360 px, page width 360 of 360, no sideways scroll. The page is always dark, like the sign-in page."
coverage_id: 87-13/D4

### 7. Partner admin creates a customer from the pool
expected: Needs the UI published. Signed in as a partner admin, the Partner portal shows the seat pool. Creating a customer with N seats lowers free seats by N, the customer appears in the list, and its first admin is invited (or the not-sent notice appears). The admin of that customer then signs in and runs it like a direct customer.
result: pass
note: "2026-11-05: passed on the release bundle, private copy: the partner admin (MFA set up) created QA Customer One with 5 seats; free went from 1,000,000 to 999,995, the customer is listed and the not-sent notice names the address; its admin then signed in (MFA set up) and used the screens ticked for it."
coverage_id: 87-09/D11

### 8. Partner portal layout
expected: Needs the UI published. A 1,000,000-seat tile fits at 1280 px and 360 px; at 1280 px the customer table needs no sideways scroll with the sidebar open or closed; cards stack below 1024 px; light and dark both look right.
result: pass
note: "2026-11-05: passed after a fix: the 1,000,000 tile fits at 1280 and 360 px; cards stack below 1024; light and dark read right. The customers table scrolled at 1280 px with the sidebar open (1,048 px in 922 px); minimums now sum to 900 px, so it fits open (922 of 922) and closed."
coverage_id: 87-12/D9

### 9. Screen chips and checklist
expected: Needs the UI published. The screen chips and the screen checklist (Appoint partner ceiling, customer screens) have even spacing, read correctly in dark theme and wrap cleanly at 320 px.
result: pass
note: "2026-11-05: passed on the release bundle: the Appoint partner screen checklist and the customer Choose screens checklist keep even spacing, read right in dark and wrap at 320 px with no overflow."
coverage_id: 87-07/D5

### 10. Seat and delete routes on the live backend
expected: Through the running app, not test calls. As Super Admin: raising a partner customer's seats past the pool is refused with how many are free and changes nothing; lowering returns seats to the pool; deleting a partner customer returns its seats; deleting a partner that still has customers is refused and deletes nothing; MSSP views never list a partner.
result: [pending]
coverage_id: 87-10/D8

### 11. No seats handed out after the pool expires
expected: With a test partner whose pool expiry has passed, creating a customer or raising seats is refused with the pool-expired message and the handed-out count does not move; lowering seats still works. (A hand-out already in flight at the exact moment of expiry may still commit; that edge was accepted in the plan.)
result: [pending]
coverage_id: 87-09/D10

### 12. A partner session receives nothing of a customer over sockets
expected: Signed in as a partner user with the browser's network tab open: the /api/stream/live socket is closed by the server (code 4403), and the Socket.IO connection delivers no customer alerts, logs, agent updates or security events.
result: [pending]
coverage_id: 87-05/D6

### 13. Live suspension, isolation and retailer trial
expected: With two partners (100 and 1,000 seats): every customer page or API opened with a partner's session is refused; suspending a partner signs its users out while its customers' agents keep reporting; installing agents into a partner customer up to its seats works and the next agent is held Pending; after a test pool expires, new agents are held and running ones keep working.
result: [pending]
coverage_id: 87-14/D6

### 14. Super Admin appoints a partner: tenants document type partner with pool, ceiling, no registrationKey, no seats of its own
expected: Super Admin appoints a partner: tenants document type partner with pool, ceiling, no registrationKey, no seats of its own
result: pass
source: automated
coverage_id: 87-01/D1

### 15. Partner admin creates a customer with seats drawn from the pool (partnerId, license.maxAgents N, allocated grows by N)
expected: Partner admin creates a customer with seats drawn from the pool (partnerId, license.maxAgents N, allocated grows by N)
result: pass
source: automated
coverage_id: 87-01/D2

### 16. A creation past the pool answers 409 pool_full with the free count and leaves no document and an unchanged counter; concurrent creations never exceed the pool
expected: A creation past the pool answers 409 pool_full with the free count and leaves no document and an unchanged counter; concurrent creations never exceed the pool
result: pass
source: automated
coverage_id: 87-01/D3

### 17. Overview carries the pool view and customer rows with exactly the D-01 keys; other partners' and direct customers never appear
expected: Overview carries the pool view and customer rows with exactly the D-01 keys; other partners' and direct customers never appear
result: pass
source: automated
coverage_id: 87-01/D4

### 18. Partner identity comes only from the token tenant confirmed type partner and active; Super Admin, non-partner roles, non-partner orgs, missing and suspended partners get 403
expected: Partner identity comes only from the token tenant confirmed type partner and active; Super Admin, non-partner roles, non-partner orgs, missing and suspended partners get 403
result: pass
source: automated
coverage_id: 87-01/D5

### 19. Mounted app: every /api/platform/partners route carries the partners guard and every /api/partner route the partnerPortal guard
expected: Mounted app: every /api/platform/partners route carries the partners guard and every /api/partner route the partnerPortal guard
result: pass
source: automated
coverage_id: 87-01/D6

### 20. Partner roles pass no platform check (can_read_all_tenants, has_platform_permission) in any tenant including platform-admin, and are in no super/platform/tenant-admin role set
expected: Partner roles pass no platform check (can_read_all_tenants, has_platform_permission) in any tenant including platform-admin, and are in no super/platform/tenant-admin role set
result: pass
source: automated
coverage_id: 87-02/D1

### 21. A partner role's effective permissions equal its table row whatever role documents say; the two partner permissions are dropped from every other role's documents
expected: A partner role's effective permissions equal its table row whatever role documents say; the two partner permissions are dropped from every other role's documents
result: pass
source: automated
coverage_id: 87-02/D2

### 22. partner_admin requires MFA enrollment (first session mfa_action enroll) and partner_viewer does not (D-20)
expected: partner_admin requires MFA enrollment (first session mfa_action enroll) and partner_viewer does not (D-20)
result: pass
source: automated
coverage_id: 87-02/D3

### 23. A partner role can be held only in a type partner organization and no other role there; create_user and update_user answer 400 and store nothing
expected: A partner role can be held only in a type partner organization and no other role there; create_user and update_user answer 400 and store nothing
result: pass
source: automated
coverage_id: 87-02/D4

### 24. Only the Super Admin assigns or manages a partner role through /api/users; an LDAP or SAML mapping to a partner role is refused with 400
expected: Only the Super Admin assigns or manages a partner role through /api/users; an LDAP or SAML mapping to a partner role is refused with 400
result: pass
source: automated
coverage_id: 87-02/D5

### 25. 20 concurrent claims fill a 90/100 pool exactly (10 succeed, allocated 100); 20 concurrent raises 10 to 11 change the customer once and the pool grows by 1
expected: 20 concurrent claims fill a 90/100 pool exactly (10 succeed, allocated 100); 20 concurrent raises 10 to 11 change the customer once and the pool grows by 1
result: pass
source: automated
coverage_id: 87-03/D1

### 26. Lowering stops exactly at seatsUsed; a refusal (below_used, pool_full, pool_below_handed_out, move_does_not_fit) changes neither document; a lost compare-and-set returns the claimed seats
expected: Lowering stops exactly at seatsUsed; a refusal (below_used, pool_full, pool_below_handed_out, move_does_not_fit) changes neither document; a lost compare-and-set returns the claimed seats
result: pass
source: automated
coverage_id: 87-03/D2

### 27. Pool resize to exactly allocated succeeds and to allocated - 1 is refused; moves succeed at exactly the free seats, refuse one short, move empty customers, and move to direct
expected: Pool resize to exactly allocated succeeds and to allocated - 1 is refused; moves succeed at exactly the free seats, refuse one short, move empty customers, and move to direct
result: pass
source: automated
coverage_id: 87-03/D3

### 28. Migration 029 adds indexes only (no partnerId/type backfill) and is idempotent; the licensing loops never read or invent seats for a partner organization
expected: Migration 029 adds indexes only (no partnerId/type backfill) and is idempotent; the licensing loops never read or invent seats for a partner organization
result: pass
source: automated
coverage_id: 87-03/D4

### 29. reconcile_pools sets allocated to the true sum with a compare-and-set and reports each drift; wired to the daily licensing tick
expected: reconcile_pools sets allocated to the true sum with a compare-and-set and reports each drift; wired to the daily licensing tick
result: pass
source: automated
coverage_id: 87-03/D5

### 30. A token issued before its partner was suspended gets 403 with X-Partner-Suspended and the stable message on its next request, including MFA-pending routes
expected: A token issued before its partner was suspended gets 403 with X-Partner-Suspended and the stable message on its next request, including MFA-pending routes
result: pass
source: automated
coverage_id: 87-04/D1

### 31. Login with the right password for a suspended partner's user answers 403 with the message and audit reason partner_suspended; a wrong password answers 401 Invalid credentials
expected: Login with the right password for a suspended partner's user answers 403 with the message and audit reason partner_suspended; a wrong password answers 401 Invalid credentials
result: pass
source: automated
coverage_id: 87-04/D2

### 32. Refresh for a suspended partner's user answers 403 with the header; reinstating the partner restores sign-in
expected: Refresh for a suspended partner's user answers 403 with the header; reinstating the partner restores sign-in
result: pass
source: automated
coverage_id: 87-04/D3

### 33. A failing status lookup answers 503 and never lets the request through; non-partner roles cause no lookup; sync verify_token refuses partner roles
expected: A failing status lookup answers 503 and never lets the request through; non-partner roles cause no lookup; sync verify_token refuses partner roles
result: pass
source: automated
coverage_id: 87-04/D4

### 34. A partner_admin is refused every mounted /api route except /api/partner, /api/auth, /api/mfa, /api/passkey and GET/HEAD /api/platform/features
expected: A partner_admin is refused every mounted /api route except /api/partner, /api/auth, /api/mfa, /api/passkey and GET/HEAD /api/platform/features
result: pass
source: automated
coverage_id: 87-05/D1

### 35. A partner_viewer is refused every write under /api/partner and keeps its own sign-in, MFA and passkey writes
expected: A partner_viewer is refused every write under /api/partner and keeps its own sign-in, MFA and passkey writes
result: pass
source: automated
coverage_id: 87-05/D2

### 36. Through the mounted middleware a partner token gets 403 JSON on tenants and MSSP, passes on its portal; Super Admin, other roles and no token are untouched
expected: Through the mounted middleware a partner token gets 403 JSON on tenants and MSSP, passes on its portal; Super Admin, other roles and no token are untouched
result: pass
source: automated
coverage_id: 87-05/D3

### 37. With no middleware, the real catalogue guards answer 403 to both partner roles on tenants, MSSP, assets, agents, users and the Partners screen
expected: With no middleware, the real catalogue guards answer 403 to both partner roles on tenants, MSSP, assets, agents, users and the Partners screen
result: pass
source: automated
coverage_id: 87-05/D4

### 38. Every route of partner_platform_endpoints and partner_endpoints carries its manifest guard (read and write strings equal) and is owned by partners or partnerPortal
expected: Every route of partner_platform_endpoints and partner_endpoints carries its manifest guard (read and write strings equal) and is owned by partners or partnerPortal
result: pass
source: automated
coverage_id: 87-05/D5

### 39. invite() stores an Active user with an unknown password hash, a 7-day token row with invite true and no creation-time field, and a hash-only invites record
expected: invite() stores an Active user with an unknown password hash, a 7-day token row with invite true and no creation-time field, and a hash-only invites record
result: pass
source: automated
coverage_id: 87-06/D1

### 40. invite() returns only {user: {id, name, email, role}, emailSent}; no token, link or password
expected: invite() returns only {user: {id, name, email, role}, emailSent}; no token, link or password
result: pass
source: automated
coverage_id: 87-06/D2

### 41. An address in use anywhere (any case) is refused 409 email_unavailable with the generic message and nothing is stored
expected: An address in use anywhere (any case) is refused 409 email_unavailable with the generic message and nothing is stored
result: pass
source: automated
coverage_id: 87-06/D3

### 42. The existing reset-password/confirm route accepts the invite token once, then the status is used; valid/expired/invalid/used all classified
expected: The existing reset-password/confirm route accepts the invite token once, then the status is used; valid/expired/invalid/used all classified
result: pass
source: automated
coverage_id: 87-06/D4

### 43. resend() supersedes the old link and issues a new one; refused 409 already_active after a password is set or for a never-invited user
expected: resend() supersedes the old link and issues a new one; refused 409 already_active after a password is set or for a never-invited user
result: pass
source: automated
coverage_id: 87-06/D5

### 44. send_invite_email sends nothing without an http(s) FRONTEND_URL or a mail configuration; with both, the link goes only to the invitee; no log line holds the token or link
expected: send_invite_email sends nothing without an http(s) FRONTEND_URL or a mail configuration; with both, the link goes only to the invitee; no log line holds the token or link
result: pass
source: automated
coverage_id: 87-06/D6

### 45. POST /api/auth/invite/status is public, body-only, limited to 10 a minute, mounted, and the only new reviewed-unauthenticated entry
expected: POST /api/auth/invite/status is public, body-only, limited to 10 a minute, mounted, and the only new reviewed-unauthenticated entry
result: pass
source: automated
coverage_id: 87-06/D7

### 46. Typed partner client: every route goes through authFetch and API_BASE, refusals throw PartnerApiError with the server text, code, status and numbers; the two invite-page calls use plain fetch with no Authorization header
expected: Typed partner client: every route goes through authFetch and API_BASE, refusals throw PartnerApiError with the server text, code, status and numbers; the two invite-page calls use plain fetch with no Authorization header
result: pass
source: automated
coverage_id: 87-07/D1

### 47. The Partner portal is visible to partner users only: denied to the Super Admin, star holders and every non-partner role, allowed to partner_admin and partner_viewer holding view:partner_portal; partner landing view is partnerPortal and the Super Admin landing is unchanged
expected: The Partner portal is visible to partner users only: denied to the Super Admin, star holders and every non-partner role, allowed to partner_admin and partner_viewer holding view:partner_portal; partner landing view is partnerPortal and the Super Admin landing is unchanged
result: pass
source: automated
coverage_id: 87-07/D2

### 48. A 403 carrying X-Partner-Suspended clears the session and goes to /login?error=partner_suspended; login surfaces body.error; LoginPage shows the suspended message
expected: A 403 carrying X-Partner-Suspended clears the session and goes to /login?error=partner_suspended; login surfaces body.error; LoginPage shows the suspended message
result: pass
source: automated
coverage_id: 87-07/D3

### 49. PartnerScreenPicker offers only ceiling switches as tickable, locks Overview and kept screens with the specified sentences, follows the parent rule, and shows the empty-ceiling message; chips render the specified labels and tones
expected: PartnerScreenPicker offers only ceiling switches as tickable, locks Overview and kept screens with the specified sentences, follows the parent rule, and shows the empty-ceiling message; chips render the specified labels and tones
result: pass
source: automated
coverage_id: 87-07/D4

### 50. Appoint creates the partner and invites its first partner_admin; a clashing email or name is refused before any write; a failed invite leaves nothing behind
expected: Appoint creates the partner and invites its first partner_admin; a clashing email or name is refused before any write; a failed invite leaves nothing behind
result: pass
source: automated
coverage_id: 87-08/D1

### 51. List is empty without partners, ordered by name ignoring case then id, with customerCount; an empty ceiling is valid
expected: List is empty without partners, ordered by name ignoring case then id, with customerCount; an empty ceiling is valid
result: pass
source: automated
coverage_id: 87-08/D2

### 52. Pool resize accepts the handed-out count and refuses one below with handedOut; expiry set, cleared and expired; ceiling validated and never touches a customer's screens
expected: Pool resize accepts the handed-out count and refuses one below with handedOut; expiry set, cleared and expired; ceiling validated and never touches a customer's screens
result: pass
source: automated
coverage_id: 87-08/D3

### 53. Suspend signs out every partner user and blocks selling while customers, agents and the pool counter stay byte-for-byte; a failed sign-out is a 503; both verbs are idempotent
expected: Suspend signs out every partner user and blocks selling while customers, agents and the pool counter stay byte-for-byte; a failed sign-out is a 503; both verbs are idempotent
result: pass
source: automated
coverage_id: 87-08/D4

### 54. Move keeps the seats and moves them between pools (exact fit succeeds, one short is move_does_not_fit), goes direct keeping the licence, comes in from direct, and both lists update at once
expected: Move keeps the seats and moves them between pools (exact fit succeeds, one short is move_does_not_fit), goes direct keeping the licence, comes in from direct, and both lists update at once
result: pass
source: automated
coverage_id: 87-08/D5

### 55. Direct customers exclude partner organizations, partner customers and platform-admin, ordered by name
expected: Direct customers exclude partner organizations, partner customers and platform-admin, ordered by name
result: pass
source: automated
coverage_id: 87-08/D6

### 56. Every change and move is audited under platform-admin and each partner involved with before/after or seats/from/to; every route refuses non-Super-Admin callers
expected: Every change and move is audited under platform-admin and each partner involved with before/after or seats/from/to; every route refuses non-Super-Admin callers
result: pass
source: automated
coverage_id: 87-08/D7

### 57. Create a customer from the pool with its first admin invited as Tenant Admin/customer_admin; answer is {customer, emailSent} with no token, link or registrationKey; a created customer carries no type
expected: Create a customer from the pool with its first admin invited as Tenant Admin/customer_admin; answer is {customer, emailSent} with no token, link or registrationKey; a created customer carries no type
result: pass
source: automated
coverage_id: 87-09/D1

### 58. A used or invalid admin email is refused before the pool is touched; a failure after the customer is stored deletes it and returns its seats
expected: A used or invalid admin email is refused before the pool is touched; a failure after the customer is stored deletes it and returns its seats
result: pass
source: automated
coverage_id: 87-09/D2

### 59. Names are unique across all organizations ignoring case and spaces with one generic refusal; stored names keep their letters, non-ASCII included
expected: Names are unique across all organizations ignoring case and spaces with one generic refusal; stored names keep their letters, non-ASCII included
result: pass
source: automated
coverage_id: 87-09/D3

### 60. An expired pool refuses creation and raising seats every time with the D-08 messages and never moves allocated; lowering stays allowed
expected: An expired pool refuses creation and raising seats every time with the D-08 messages and never moves allocated; lowering stays allowed
result: pass
source: automated
coverage_id: 87-09/D4

### 61. Seats lower to exactly the seats in use (below_used with used otherwise) and raise only within free seats (pool_full with free otherwise)
expected: Seats lower to exactly the seats in use (below_used with used otherwise) and raise only within free seats (pool_full with free otherwise)
result: pass
source: automated
coverage_id: 87-09/D5

### 62. Customer screens only within the ceiling plus start screens; one string beyond is refused naming the screen; kept screens survive; all, unknown strings and a missing parent are refused; order is submitted, kept, missing start
expected: Customer screens only within the ceiling plus start screens; one string beyond is refused naming the screen; kept screens survive; all, unknown strings and a missing parent are refused; order is submitted, kept, missing start
result: pass
source: automated
coverage_id: 87-09/D6

### 63. Viewer gets 403 on every write route and on GET /team, and may read /features; partner A using B's, a direct customer's or a partner's id answers the same 404 as an unknown id and changes nothing
expected: Viewer gets 403 on every write route and on GET /team, and may read /features; partner A using B's, a direct customer's or a partner's id answers the same 404 as an unknown id and changes nothing
result: pass
source: automated
coverage_id: 87-09/D7

### 64. Overview lists only the partner's customers with exactly the D-01 keys and no secret anywhere; an empty partner reads customers [] and its pool; pool, seats, agent counts, expiry and ordering follow the PART-08 rules
expected: Overview lists only the partner's customers with exactly the D-01 keys and no secret anywhere; an empty partner reads customers [] and its pool; pool, seats, agent counts, expiry and ordering follow the PART-08 rules
result: pass
source: automated
coverage_id: 87-09/D8

### 65. Team: lists only this partner's staff with active, invited or invite_expired; invites partner_admin or partner_viewer; resend only before a password is set and only inside the partner; never a token
expected: Team: lists only this partner's staff with active, invited or invite_expired; invites partner_admin or partner_viewer; resend only before a password is set and only inside the partner; never a token
result: pass
source: automated
coverage_id: 87-09/D9

### 66. create_tenant stores exactly the pre-change field set (no partnerId) through tenant_docs.build_tenant_doc
expected: create_tenant stores exactly the pre-change field set (no partnerId) through tenant_docs.build_tenant_doc
result: pass
source: automated
coverage_id: 87-10/D1

### 67. PATCH maxAgents on a partner customer claims or returns pool seats; past the pool answers 409 pool_full with free and changes nothing; below the seats used succeeds for the Super Admin; a raise ignores suspension and expiry but not the pool total; reclaim-window-only PATCH never touches the pool; direct customers unchanged
expected: PATCH maxAgents on a partner customer claims or returns pool seats; past the pool answers 409 pool_full with free and changes nothing; below the seats used succeeds for the Super Admin; a raise ignores suspension and expiry but not the pool total; reclaim-window-only PATCH never touches the pool; direct customers unchanged
result: pass
source: automated
coverage_id: 87-10/D2

### 68. Deleting a partner customer returns its seats; deleting a partner with customers answers 409 and deletes nothing; a partner without customers can be deleted
expected: Deleting a partner customer returns its seats; deleting a partner with customers answers 409 and deletes nothing; a partner without customers can be deleted
result: pass
source: automated
coverage_id: 87-10/D3

### 69. Approve-and-raise on a partner customer draws from the pool (409 no_free_seat with the licence when it lacks room, nothing changed); direct customers keep the $inc path
expected: Approve-and-raise on a partner customer draws from the pool (409 no_free_seat with the licence when it lacks room, nothing changed); direct customers keep the $inc path
result: pass
source: automated
coverage_id: 87-10/D4

### 70. hold_reason returns license_expired for a partner customer once the partner pool has expired (even when the customer's own licence has no expiry), None before, None for direct customers; already enrolled agents keep status and seats
expected: hold_reason returns license_expired for a partner customer once the partner pool has expired (even when the customer's own licence has no expiry), None before, None for direct customers; already enrolled agents keep status and seats
result: pass
source: automated
coverage_id: 87-10/D5

### 71. MSSP tenant list, overview and aggregated alerts never show a partner organization
expected: MSSP tenant list, overview and aggregated alerts never show a partner organization
result: pass
source: automated
coverage_id: 87-10/D6

### 72. A new module writing license.maxAgents outside the allowlist fails a test; the scanner is proved on scratch files and cannot go blind
expected: A new module writing license.maxAgents outside the allowlist fails a test; the scanner is proved on scratch files and cannot go blind
result: pass
source: automated
coverage_id: 87-10/D7

### 73. Partners table: loading skeleton, empty state, error with Try again, ordered rows with pool bar, expiry chips, screen count, status, pluralised counts, search above 10 and paging at 25 from 50
expected: Partners table: loading skeleton, empty state, error with Try again, ordered rows with pool bar, expiry chips, screen count, status, pluralised counts, search above 10 and paging at 25 from 50
result: pass
source: automated
coverage_id: 87-11/D1

### 74. Show customers disclosure with the D-01 columns only, one fetch per partner, empty and error states, Move customer and Add an existing organization buttons
expected: Show customers disclosure with the D-01 columns only, one fetch per partner, empty and error states, Move customer and Add an existing organization buttons
result: pass
source: automated
coverage_id: 87-11/D2

### 75. Appoint and Edit partner form: validation messages, request bodies, handed-out floor and verbatim 409, result view when the invite email was not sent, Esc and backdrop blocked in flight
expected: Appoint and Edit partner form: validation messages, request bodies, handed-out floor and verbatim 409, result view when the invite email was not sent, Esc and backdrop blocked in flight
result: pass
source: automated
coverage_id: 87-11/D3

### 76. Suspend, Reinstate and Move dialogs: red and accent confirms, pending labels, consequence line before submit, fit refusal disabling submit, add mode with direct customers only
expected: Suspend, Reinstate and Move dialogs: red and accent confirms, pending labels, consequence line before submit, fit refusal disabling submit, add mode with direct customers only
result: pass
source: automated
coverage_id: 87-11/D4

### 77. Seat pool summary: four tiles, handed-out bar, skeletons while loading, error block that hides the summary, expiry helper (1 day left / n days left), within-30-days info banner, expired amber banner
expected: Seat pool summary: four tiles, handed-out bar, skeletons while loading, error block that hides the summary, expiry helper (1 day left / n days left), within-30-days info banner, expired amber banner
result: pass
source: automated
coverage_id: 87-12/D1

### 78. Customers table with the D-01 columns only, plain-text names, mini seat bar, paging at 25, search above 10, empty states for admin and viewer, quiet refresh
expected: Customers table with the D-01 columns only, plain-text names, mini seat bar, paging at 25, search above 10, empty states for admin and viewer, quiet refresh
result: pass
source: automated
coverage_id: 87-12/D2

### 79. Viewer variant: no Create customer, no row actions, no Team section and no Invite colleague; Export CSV kept; the read-only line shown
expected: Viewer variant: no Create customer, no row actions, no Team section and no Invite colleague; Export CSV kept; the read-only line shown
result: pass
source: automated
coverage_id: 87-12/D3

### 80. Export CSV: six columns, every customer in name order regardless of the filter, formula-guarded and quoted, header-only for no customers, Exporting... state, red toast on failure, partner-usage-{slug}-{date}.csv
expected: Export CSV: six columns, every customer in name order regardless of the filter, formula-guarded and quoted, header-only for no customers, Exporting... state, red toast on failure, partner-usage-{slug}-{date}.csv
result: pass
source: automated
coverage_id: 87-12/D4

### 81. Create customer: fields, validation messages, verbatim 409 refusals, Dashboard-only default screens, result view when the email was not sent that shows no link, token or registration key, one request per double click
expected: Create customer: fields, validation messages, verbatim 409 refusals, Dashboard-only default screens, result view when the email was not sent that shows no link, token or registration key, one request per double click
result: pass
source: automated
coverage_id: 87-12/D5

### 82. Change seats: used floor and free ceiling in the contract words, plain-words change line, disabled with the amber line when the pool has expired
expected: Change seats: used floor and free ceiling in the contract words, plain-words change line, disabled with the amber line when the pool has expired
result: pass
source: automated
coverage_id: 87-12/D6

### 83. Choose screens: picker in customer mode, kept screens locked, empty-ceiling message, ceiling refusal shown verbatim then refetched
expected: Choose screens: picker in customer mode, kept screens locked, empty-ceiling message, ceiling refusal shown verbatim then refetched
result: pass
source: automated
coverage_id: 87-12/D7

### 84. Team list and Invite colleague: name, email, role and status chip, Resend invite only while pending, role helper text, 7-day toast, amber block when the email was not sent
expected: Team list and Invite colleague: name, email, role and status chip, Resend invite only while pending, role helper text, 7-day toast, amber block when the email was not sent
result: pass
source: automated
coverage_id: 87-12/D8

### 85. Link check: token removed from the address bar before the status request, Checking skeleton, valid welcome with read-only email, Expired, Used, Invalid (also for a missing token and unclassifiable state), network error with Try again, h1 focus on every state change, text-only rendering of long names
expected: Link check: token removed from the address bar before the status request, Checking skeleton, valid welcome with read-only email, Expired, Used, Invalid (also for a missing token and unclassifiable state), network error with Try again, h1 focus on every state change, text-only rendering of long names
result: pass
source: automated
coverage_id: 87-13/D1

### 86. Password form: two new-password fields, five live rules, polite live region only after touch, submit disabled until rules met and fields match, mismatch message, show/hide toggles with aria-pressed, paste allowed
expected: Password form: two new-password fields, five live rules, polite live region only after touch, submit disabled until rules met and fields match, mismatch message, show/hide toggles with aria-pressed, paste allowed
result: pass
source: automated
coverage_id: 87-13/D2

### 87. Submit and sign-in: Setting password... with fields disabled, one accept call per double click, one login with the invited email, window.location.replace('/'), Signing you in state, fallback Password set state, 400 to Used or Expired, verbatim complexity refusal, other refusals and network failure keep typed values, password and token never logged, stored or put in the URL
expected: Submit and sign-in: Setting password... with fields disabled, one accept call per double click, one login with the invited email, window.location.replace('/'), Signing you in state, fallback Password set state, 400 to Used or Expired, verbatim complexity refusal, other refusals and network failure keep typed values, password and token never logged, stored or put in the URL
result: pass
source: automated
coverage_id: 87-13/D3

### 88. /accept-invite renders AcceptInvitePage without a session, outside the shell, ahead of the MFA gate and the sign-in page
expected: /accept-invite renders AcceptInvitePage without a session, outside the shell, ahead of the MFA gate and the sign-in page
result: pass
source: automated
coverage_id: 87-14/D1

### 89. partners renders PartnersDashboard for the Super Admin and the Tenants screen receives no type partner organization
expected: partners renders PartnersDashboard for the Super Admin and the Tenants screen receives no type partner organization
result: pass
source: automated
coverage_id: 87-14/D2

### 90. A partner user lands on the Partner portal, makes no request outside /api/partner, auth, mfa, passkey, GET /api/platform/features (plus the liveness probe and sign-in provider list), and the palette and search keys do nothing
expected: A partner user lands on the Partner portal, makes no request outside /api/partner, auth, mfa, passkey, GET /api/platform/features (plus the liveness probe and sign-in provider list), and the palette and search keys do nothing
result: pass
source: automated
coverage_id: 87-14/D3

### 91. Header restricted drops palette, search, tour, help, notifications; the partner sidebar holds exactly one entry with no group heading and never polls support; the Super Admin sees Partners right after Tenants and never Partner portal
expected: Header restricted drops palette, search, tour, help, notifications; the partner sidebar holds exactly one entry with no group heading and never polls support; the Super Admin sees Partners right after Tenants and never Partner portal
result: pass
source: automated
coverage_id: 87-14/D4

### 92. Phase gates: partner and parity pytest set, full frontend suite, npm run build
expected: Phase gates: partner and parity pytest set, full frontend suite, npm run build
result: pass
source: automated
coverage_id: 87-14/D5

### 93. AppView carries partners and partnerPortal; sidebar presentation has an icon for each; manifest, union and sidebar agree on 206 views and 192 nav entries
expected: AppView carries partners and partnerPortal; sidebar presentation has an icon for each; manifest, union and sidebar agree on 206 views and 192 nav entries
result: pass
source: automated
coverage_id: 87-15/D1

### 94. GOLDEN pins partner_admin to manage:partner_customers + view:partner_portal and partner_viewer to view:partner_portal; manage:partners is super-admin-only (11)
expected: GOLDEN pins partner_admin to manage:partner_customers + view:partner_portal and partner_viewer to view:partner_portal; manage:partners is super-admin-only (11)
result: pass
source: automated
coverage_id: 87-15/D2

### 95. Partner roles are left out of TENANT_PERMS by role key, so the Partner portal is never a customer-tenant screen
expected: Partner roles are left out of TENANT_PERMS by role key, so the Partner portal is never a customer-tenant screen
result: pass
source: automated
coverage_id: 87-15/D3

## Summary

total: 95
passed: 90
issues: 0
pending: 5
skipped: 0
blocked: 0

## Gaps

[none yet]
