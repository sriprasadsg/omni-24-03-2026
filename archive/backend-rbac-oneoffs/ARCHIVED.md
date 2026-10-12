# Archived: one-off scripts that hand-wrote role permissions

`fix_rbac_integrations.py`, `update_sbom_roles.py`, `update_all_sbom_roles.py`,
`enable_compliance_for_admin.py` and `reset_db_fresh.py` each wrote role permission
lists straight into the `roles` collection. Nothing in tracked code referenced them.

Since Phase 75 the only role-to-permission table is `backend/rbac_defaults.py`, and every
backend start mirrors it into the shared role documents. Re-running any of these scripts
would re-create the drift that phase removed (`reset_db_fresh.py` additionally drops and
reseeds data). Do not run, edit or import them.

Related scripts deliberately kept in `backend/`: `fix_rbac.py` and `fix_all_rbac.py`
(rewrite source files, not role data), `unlock_enterprise_features.py` (tenant feature tiers;
run by `deploy-ubuntu.sh` and `run-on-ubuntu.sh`) and `diagnose_rbac.py` (read-only).

Moved from `backend/` with `git mv` on 2026-10-12 by Phase 75.
