# README — FF Confirmation Deploy Readiness

Artifacts for production deployment **audit + plan only** (no VPS deploy in this task).

| File | Purpose |
|------|---------|
| `DEPLOYMENT_READINESS_REPORT.md` | Full readiness report + verdict |
| `PRODUCTION_LINEAGE.md` | Git graph / ancestry |
| `FINAL_INTEGRATION_REF.json` | Exact deploy commit |
| `DATA_SAFETY.md` | Runtime path protections |
| `AUTOMATION_PROOF.md` | Timer → hook chain |
| `PREDEPLOY_TEST_GATE.json` | 62/62 local gate |
| `VPS_DEPLOY_RUNBOOK.md` | Copy/paste operator deploy |
| `ROLLBACK_RUNBOOK.md` | Code rollback, keep data |
| `FIRST_LIVE_ACCEPTANCE.md` | Post-deploy acceptance |

**Deploy ref:** `bc8152810` on `cursor/foreign-flow-confirmation-prod-integrate-aad2`
