No external API integration: exports use local libraries only (reportlab, openpyxl, recharts); endpoints are first-party (/api/itam/reports*, /api/itam/kpis). No outbound calls to a third-party API/SDK.

<!--
Detector context: `api-coverage.cjs --json` reported `detected: false` at plan
time (see 72-01-PLAN.md's Excluded-gaps note). The `true` reading seen at
verify:pre is a false positive — the detector's verb+noun proximity heuristic
matched the phrase "no external API/SDK integration" inside that same plan
note. This declaration line is the sanctioned dismissal path for exactly that
class of false positive per api-coverage.cjs's documented design.
-->
