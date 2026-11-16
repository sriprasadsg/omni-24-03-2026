# Phase 78: Organization & Endpoint Cost API - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-11-16
**Phase:** 78-organization-endpoint-cost-api
**Areas discussed:** Disposed & retired rule, Endpoint list contents, Missing or partial cost data, Super Admin & tile follow-through

---

## Disposed & retired rule

**Q: Besides Disposed and Retired, should any other status leave the current book value total?**

| Option | Description | Selected |
|--------|-------------|----------|
| Only Disposed + Retired | Exactly COST-06; Archived and Broken hardware is still owned | ✓ |
| Add Archived too | Shelved assets drop out; Broken stays | |
| Add Archived and Broken | Only Deployable and Deployed count | |

**Q: How should Disposed and Retired assets appear in the per-asset cost list?**

| Option | Description | Selected |
|--------|-------------|----------|
| Hidden by default, same filter shows them | One filter on summary and list; list rows add up to the summary | ✓ |
| Always listed, marked Disposed/Retired | Filter changes only the purchase total | |
| Never listed | Only in the historical purchase total | |

**Q: When the filter brings a Disposed or Retired asset back, what should its book value read?**

| Option | Description | Selected |
|--------|-------------|----------|
| Null, with reason disposed/retired | No current value; purchase cost still shown | ✓ |
| 0 (written off) | Accounting view; reads like a $0 asset | |
| Its depreciated value, as if still owned | Misleading next to a total that leaves it out | |

**Q: Should the Asset value pre-built report follow the same rule?**

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, same default as the cost list | Tile, report and cost view agree row for row; status pie chart keeps all statuses | ✓ |
| Keep the rows, book value blank, reason shown | Keeps history; purchase column then differs from summary | |
| You decide | Claude picks for parity-test simplicity | |

---

## Endpoint list contents

**Q: Which assets should /api/itam/costs/assets list by default?**

| Option | Description | Selected |
|--------|-------------|----------|
| Every asset, with an agent endpoints only filter | Count matches the Assets page; unpriced rows visible | ✓ |
| Only computers with an agent | Pure endpoint list | |
| Only priced assets | Shorter, hides the coverage gap | |

**Q: For an agent computer row, what agent details come with it?**

| Option | Description | Selected |
|--------|-------------|----------|
| Agent id, hostname, status and last seen | From the agents collection; the asset's stamped agentStatus never goes Offline | ✓ |
| Agent id and hostname only | Liveness stays on the Agents screen | |
| Nothing extra | Asset fields only | |

**Q: Agent record and hand-entered record for the same computer?**

| Option | Description | Selected |
|--------|-------------|----------|
| Flag possible duplicate, never merge | Serial match marks both rows; summary reports a duplicate count | ✓ |
| Merge into one row | Counts once; a wrong match moves cost silently | |
| Ignore it | Double counting stays invisible | |

**Q: Default order of the per-asset list?**

| Option | Description | Selected |
|--------|-------------|----------|
| Book value high to low, not tracked last | Same order as the Asset value report | ✓ |
| Asset tag / name A to Z | Predictable lookup | |
| You decide | Claude picks order and paging | |

---

## Missing or partial cost data

**Q: An asset has a purchase price and date but no depreciation policy?**

| Option | Description | Selected |
|--------|-------------|----------|
| Price counts, book value not tracked | Same as the tile and book-value route today | ✓ |
| Book value = purchase price | Overstates old hardware; changes the tile and route | |

**Q: How should coverage be reported?**

| Option | Description | Selected |
|--------|-------------|----------|
| Two counts plus a reason breakdown | Priced X of Y, Valued Z of Y, counts per reason | ✓ |
| One count: complete cost data | Simpler; hides known-but-undepreciated prices | |

**Q: Purchase date in the future?**

| Option | Description | Selected |
|--------|-------------|----------|
| Count it at full price, flag it | Keeps parity; adds a futurePurchaseDate flag and count | ✓ |
| Treat as not tracked | Changes the route and tile too | |
| Leave as is, no flag | Silent, as today | |

**Stated by Claude, not asked:** a $0 price counts as priced; the unused asset-level `useful_life_years` / `salvage_value` fields stay ignored (model-level policy only).

---

## Super Admin & tile follow-through

**Q: Should the KPI route and the Asset value report get the same real-tenant-or-400 rule?**

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, all three share one tenant rule | No blended totals; tile must send the selected tenant | ✓ |
| Cost routes only | Super Admin tile keeps blending every tenant | |

**Q: How much of the tile should this phase fix?**

| Option | Description | Selected |
|--------|-------------|----------|
| Small tile fix now | Not tracked, Valued X of Y, selected tenant sent, Select a tenant state | ✓ |
| Only what would break | Not tracked and the tenant header | |
| No UI change, all in Phase 80 | Tile can show $0.00 or an error until then | |

**Q: Platform Support/Billing always get 400 on cost routes?**

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, Owner only | Matches today's switcher rule | ✓ |
| Let Billing pick a tenant for costs | Widens the tenant-override rule | |

**Q: Should ITAM API keys be able to read the cost routes?**

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, with view:itam scope | Same as /book-value and /kpis; scope-narrowing test | ✓ |
| Session sign-in only | New session-only guard | |

---

## Claude's Discretion

- Shared computation location and refactor of KPI and report onto it.
- Response shape, field and reason-code names, filter parameter names.
- Pagination style (full-set sort, totals never paged).
- Serial normalisation for duplicate detection.
- Golden-value cases and the large-tenant timing test.
- Tile copy for the new states.

## Deferred Ideas

- Platform Billing/Support picking a tenant for cost reads (declined for this phase).
- Cleanup of the unused asset-level depreciation fields.
