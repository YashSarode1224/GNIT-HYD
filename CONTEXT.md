# Blackout Mesh — implementation context

## GNITC synthetic district demo — 2026-10-10

Delivered `/grid` with shared SHIFT, Energy, Self-healing and Transformers views backed by the Python-owned district API. All tabs use one run, revision and graph. The map is an attributed OpenStreetMap snapshot (retrieved 2026-10-10, ODbL-1.0); building centroids act as virtual group centers. No electrical network, asset location, demand or rating is sourced from physical campus data.

The topology generator was run with SHIFT PRSG from pinned BSD-3-Clause commit `995004c84c16df7c8ebfd3ddddf3e723a0938a99`, offline, for both secondary strategies with six clusters. It builds geometric primary/secondary graphs, then completes `BalancedPhaseMapper`, `TransformerVoltageMapper`, the synthetic-catalog `EdgeEquipmentMapper`, and `DistributionSystemBuilder`; the outputs are validated as trees before serialization. `RadialStrategy` produced 35 nodes / 35 edges (35 phase nodes, 35 voltage nodes, 34 edge-equipment items); `MeshSteinerStrategy` produced 31 / 31 (31, 31, 30). The catalog's 11 kV/400 V, 100 kVA transformer, 100 A branch and load ratings are explicit demo assumptions. SHIFT network generation and mapping completed; there was **no SHIFT electrical simulation or export**. The separately checked-in topology has a declared synthetic tie.

CityLearn's pinned MIT source was run over 24 hours using synthetic district-shaped demand, PV and battery inputs. The trace totals are 141,800 Wh demand, 64,000 Wh PV generated (63,900 Wh used, 100 Wh curtailed), 4,800 Wh battery charging, 4,320 Wh discharge, 480 Wh battery loss, 82,700 Wh baseline import scheduled and 78,380 Wh dispatch import scheduled. For example, at hour 12: 7,400 W demand, 9,000 W PV, 8,900 W PV used and 1,500 W battery charging; at hour 17: 7,600 W demand, 1,800 W PV, 1,500 W battery discharge and 4,300 W import. These are a real engine run on synthetic inputs; scheduled import is not measured grid delivery or demonstrated savings.

Browser acceptance on an isolated frontend/backend at hour 20 showed 6,200 W requested, 6,000 W grid served and 200 W unmet. TX1 selection stayed synchronized between map and transformer view; a map tie-overlap rendering issue was fixed. Overload, cooling failure, missing-sensor and cleared-scenario cases showed the configured observation diagnosis or `UNKNOWN` when evidence was absent/cleared. A radial-path fault produced a restoration proposal after two evidence intervals; the modeled shortfall changed from 1,077 W to 0 W after applying it. The line fault cleared only after two further fresh evidence intervals. Requested power reconciled to served plus unmet and line flows stayed within declared limits. 375, 768 and 1440 px browser layouts had no horizontal overflow. All numbers and states are simulated.

Verification: the full backend suite completed with **411 passed, 2 skipped in 56.07 s**. The full relevant district test set passed **16 tests** (`PYTHONPATH=backend .venv-city/bin/python -m pytest backend/tests/test_district*.py -q`). Focused DistrictMap/DistrictDemo tests after the clear gate: **4 passed**; the whole frontend suite: **38 passed across 10 files**. `npm run check-client`, `npm run test:contract`, and `npm run build` passed; the build retains its large-chunk advisory. Both SHIFT strategy generation commands completed. Held-out evaluation and hardware/physical acceptance were not run; no held-out split was unsealed. Risks/deferred work: synthetic catalog/network and energy inputs, no electrical simulation/export, no physical measurements or hardware integration; OpenStreetMap source data are ODbL. Next: keep physical A/B acceptance paused until hardware work is scheduled and record it separately from this simulation evidence.

## Selective licensed benchmark reuse — 2026-10-10

Reused CityLearn's original NumPy equity-distribution method at pinned commit `834575c1a0194c8ae9d648ae858376a94dfceb78`, with its complete MIT notice under `backend/benchmarks/licenses/`. Allocation benchmark v2026-10-10.3 reports per-room occupied requested/served seconds, nullable service fractions and service Gini, including defined-run denominators in JSON/Markdown. This is offline evaluation; policy inputs and decisions are unchanged. No new dependencies or API/schema changes.

Verification: full backend suite **201 passed**; final focused allocation suite **9 passed** after report-denominator changes. Allocation benchmark **385 runs, 0 constraint violations**; every pre-existing outcome field matches the frozen report exactly. Extracted method and license were checked against pinned source. New reports are local under `local-only/reuse-2026-10-10/verification/`; checked-in historical results were preserved.

Five repository clones, pinned manifest and individual subagent reuse maps remain ignored under `sources/` and `local-only/reuse-2026-10-10/`. Broader assimilation is mapped, not delivered: geographic feeders require catalog/topology reconciliation, live RL lacks local hard constraints, and two source repositories lack project licenses. Next step is selecting those larger experiments and resolving their input/license gates. No upstream applications, frontend, held-out evaluation or physical hardware were run in this task; no push.

## Appliance-level allocation and the new `/demo` — 2026-10-10

- **One appliance-level decision.** CP-SAT decides all 31 appliances (lexicographic priority classes, then fewest switches); every plan is validated, a validated conservative fallback covers a non-optimal solve, and an exhaustive oracle checks it in tests. Campus, classroom and hospital views are projections of that one decision. This supersedes the feeder B leaf budget from #33 below.
- **`/demo` is the power-system page** (Overview, Floor Plan, Electrical Network, Fault Detection, Electrical Laws) driven by `GET /api/v1/power-system`; the city page moved to `/city`. Details, verified outage/overload states and limitations: `docs/APPLIANCE_ALLOCATION.md`.

## One-authority migration follow-up (#33) — 2026-10-10

- **One feeder B decision.** The campus allocator decides feeder A and grants feeder B a budget; the classroom leaf allocation is the only decision inside it. L3–L5 now publish `requested_w`/`served_w` from their leaves (partial service), and every total reconciles from leaves through feeders to the source on `/demo`, `/classrooms` and `/hospital`. Frontend totals use `served_w`.
- **Named teaching scenarios.** `GET /api/v1/site/scenarios`, `POST /api/v1/site/scenario` (`normal`, `source_shortage`, `feeder_b_trip`, `classroom_overload`, `hospital_overload`), derived from the active site profile (#26). The identity's `scenario` shows the active one or `custom`.
- Sessions (#21/#45), hospital mapping (#48) and per-app lifecycle (#11) had already landed. Details and what is left: `docs/CATALOG_MIGRATION.md`.

Verification: backend suite **224 passed, 2 skipped**; frontend `npm run build`, `npm test` (18) and `npm run test:contract` pass; generated client in sync. No browser or hardware run.

## Issue #15 cleanup — 2026-10-10

Removed three empty `.gitkeep` placeholders, pinned backend runtime/test dependencies from a clean Python 3.14 install (195 passed, 2 skipped) and fixed the stale `--with httpx` test command in `AGENTS.md`. Every other script and both firmware trees have callers and stay. Inventory and evidence: [docs/ISSUE_15_DELIVERY.md](docs/ISSUE_15_DELIVERY.md).

## Person A sprint: evidence and backend — 2026-10-10

Answers to the adversarial review, in five commits on `claude/peaceful-volta-r0k5cd`:

- **One facility model (A3).** Hospital equipment are the leaves of campus feeder A: L0 2,000 W and L1 1,000 W (all essential), L2 3,000 W (optional; renamed Water Pump & HVAC). `reconcile_catalog()` checks sums and tiers at startup. The hospital view allocates within the feeder A watts the campus served, so a shortage or feeder A trip reaches `/hospital` in the same revision. The hospital limit is now 0–6,000 W (4,000 W overload preset).
- **Fault injection (A4).** `inject_fault` / `clear_fault` on `POST /api/v1/visualizers/hospital` keep an overload, cooling failure, both, upstream loss, sensor dropout or stuck sensor until cleared or reset; the old `scenario` field aliases it. Diagnosis still reads only telemetry produced by `sensors.apply_fault`.
- **Stuck sensors (A2).** A current reading repeated exactly on 3 readings while temperature moves ≥ 3 °C with cooling OK latches `SUSPECTED_STUCK_SENSOR` until the reading changes; with no other hypothesis the result abstains instead of NORMAL. Live hospital telemetry has small deterministic noise. Diagnosis benchmark stuck_sensor: dev 0/4 → 4/4 (85 → 0 safety-violation steps), calibration 0/4 → 4/4 (73 → 0). Held-out has been unsealed twice (`UNSEALED.log`): at 00:57 UTC on main (#45) with the earlier detector (stuck_sensor 2/4, 63 violation steps), and at 01:09 UTC with this frozen detector, written without seeing the earlier held-out result. Committed results are the second run: every family detected; stuck_sensor 4/4 with 0 violations; 59 violation steps remain in near-threshold overload/temperature, delay and chatter cases (`backend/benchmarks/diagnosis/results/diagnosis_heldout.md`). No retuning after unsealing.
- **ML switching (A1).** `RankDwell` holds a room's ranking state until a changed state repeats on 3 readings (value fixed before measuring). Allocation benchmark `alloc-bench-2026-10-10.2`, 385 runs, 0 constraint violations. 6 kW shortage with validation-rate classifier errors: switches 20.6 → 15.0 (no-ML 6.6), occupied service 85.4% → 85.2% (no-ML 84.9%, oracle 85.8%), essential unmet 221.9 Wh vs 205.1 Wh without ML. Heavy errors: switches 59 → 21, service 81.3% → 83.0%. Recovery chatter: 94.9% vs 91.0% without ML, 51.6 vs 48.4 switches. Interpretation: in this benchmark even perfect occupancy adds < 1 point in a steady shortage, so the pitch should lead with protected, explained allocation and treat ML as optional ranking.
- **CI (A5).** The workflow now runs the whole backend suite, not only the fixture contract test.

Verification: `PYTHONPATH=backend uv run --no-project --python 3.14 --with-requirements backend/requirements-test.txt --with-requirements backend/requirements-ml.txt python -m pytest backend/tests -q` — **173 passed, 2 skipped** (electrical engine not installed). Frontend `npm run build` and `npm test` (15 tests) pass. No browser, Playwright e2e or hardware run in this sprint. Person B's UI work (fault buttons, one-story page, simple-vs-ours panel) is not part of these commits.

## PR #38 conflict resolution — 2026-10-10

Merged current main (`6b2feaf`) into `feature/bm-fixes`. Preserved the evaluated logistic artifact and ML requirements, telemetry-derived diagnosis, protected allocation policies, read-only projections, background control loop, electrical-study boundary and evidence-backed classroom/hospital drawings. Integrated per-application lifecycle/storage, configurable inventory, generated OpenAPI/TypeScript contracts and the shared TanStack/Zustand WebSocket connection. Publication ordering uses `published_revision`; duplicate heartbeats remain fresh and older HTTP snapshots cannot replace newer same-run cached data.

SQLModel 0.0.22 failed on the project's Python 3.14 runtime; installed and tested 0.0.48. Each app owns its SQLite engine and shuts down its control/replay tasks. Simulation ACKs are saved without confirming physical LEDs; physical ACKs remain rejected until a validated command/session protocol is provisioned.

Verification: **133 backend tests passed**, including independent app instances, main route/WS envelope checks, SQLite audit records surviving restart and simulated ACK separation. Frontend production build passed; generated API schema/types are synchronized. Existing large-bundle warning remains. No browser interaction or physical hardware acceptance was run. Incident lifecycle/history replay and complete generated typing/runtime validation remain follow-up work; the PR does not establish production or hardware readiness.


Updated 2026-10-09. Remote application/Board B work and local ESP32 A work are merged. See [progress report](PROGRESS_REPORT.md) for current evidence, blockers and next actions; [ESP32 A handoff](ESP32_A_STATUS.md) retains its original build/physical limits.

## Current state

UI: the original light graph-paper theme remains. `/classrooms` now presents one compact tiled game-style campus map with three classrooms, small equipment sprites and a prominent shared current-flow overlay; `/hospital` independently shows three transformers, sensors and likely-cause evidence. The original `/demo` React Flow nodes now have explicit dimensions and render visibly. Model/replay presentation remains available through the API. Frontend production build passes with its existing large-bundle warning.

Software work is active and hardware work is paused. A trained four-feature local occupancy proxy, observation/model/replay APIs, exact 64-mask allocator, restoration gate and responsive command center are now integrated. The software freezes the existing six-service 14-kW catalog; the historical nine-load catalog remains deferred. No paid keys are required.

BM-17 (Issue #19) delivered and pushed to `origin/main`: modular telemetry-derived diagnosis subsystem (`backend/app/diagnostics/`) supporting simultaneous fault coexistence (overload + cooling failure co-occur), transparent deterministic ranking by severity tier and uncalibrated heuristic evidence score, physical contradiction detection (`CONTRADICTORY_EVIDENCE`), scoped missing data handling (`INSUFFICIENT_TELEMETRY`), and observational ambiguity (`INDISTINGUISHABLE_CAUSES`) with required inspection instructions (`next_check_needed`). Hospital visualizer and campus `GridState` now emit structured candidate hypotheses. Frontend displays multi-hypothesis badges and abstention cards. Rebased cleanly onto latest `origin/main` (incorporating Unified Site Authority #3, Safety Limits #22, and Control Loop #9/#10). 64 backend tests pass and frontend build passes cleanly.


The selected logistic pipeline beat Random Forest on validation; the tested CPU TabICL configuration was too slow for live inference. Later-day exploratory performance is much weaker than validation; do not claim real campus accuracy or untouched test results. Full measurements and data attribution are in `backend/models/MODEL_REPORT.md` and `evaluation.json`.

Hardware is not integrated: A/B serial/radio contracts differ, physical ACK fields stay null and the link stays NOT_CONNECTED. No device flashing or fresh physical testing occurred during this software delivery.

## Scope and authority

- Remote current application plan: [remaining plan v2.0](docs/planning/PRIORITYGRID_HACKATHON_REMAINING_PLAN.md) and [blueprint](docs/planning/PRIORITYGRID_FINAL_IMPLEMENTATION_BLUEPRINT.md).
- [Required ML plan](docs/planning/LAB_ACTIVITY_ML_PLAN.md) preserves the user's explicit trained-classifier requirement. Its nine-load catalog differs from the web app's six-load catalog; resolve this explicitly, keeping all values labeled by configuration.
- Physical first milestone: two ESP32s, one RFID reader, three cards, three classroom LEDs and four buttons. Full two-person plan is local-only in `/home/bread/blackout-mesh-local/`. Phase 0 stays complete.
- Simulated power; real radio/LEDs only after verified. No real occupancy accuracy, power delivery, savings or multi-hop mesh claim.
- Approximately 24-hour hackathon and ₹1,500 ceiling; no Arduino/displays. Unknown 12 V/amp/motor modules stay outside baseline.
- Reuse recommendations unchanged and local-only; keep keys, UIDs, device backups and raw local logs out of Git. Graphify/Security Auditor are explicit on-demand only.

## Next action

Rehearse the software demo, gather independently labeled local room observations, and evaluate on new sessions before making accuracy claims. Use `/classrooms`: reset, scan CR1, then overload (3,400 W). CR1 retains 2,000 W; CR2 and CR3 each retain 700 W essential computers/lighting. This separate 8,000-W classroom catalog does not change the six-service campus catalog. Use `/hospital` for overload, cooling failure, upstream loss and missing-sensor scenarios. Diagnosis reads sensor values, uses transparent demonstration thresholds and is not a trained transformer model. Use `/demo` for original shortage and feeder-fault controls; inspect the API at port 8000 `/docs`. Train only when updating evidence/model, not on every start. Detailed current checks are in PROGRESS_REPORT.md.

When hardware resumes, agree one A/B transport and physical mapping before linking the backend. Phase 0 remains complete; physical detailed plans stay local under `/home/bread/blackout-mesh-local/`.

## Pending-work planning — 2026-10-10

[docs/planning/PENDING_IMPLEMENTATION_PLAN.md](docs/planning/PENDING_IMPLEMENTATION_PLAN.md) defines all 24 requested backlog items against `d1c58d7`, with six phases, dependencies, acceptance/verification criteria and scoped library choices. This is planning, not implementation completion. Hardware remains paused and existing reuse recommendations are unchanged. Runtime code and dependencies were not changed or tested in this planning task; plan structure and dependency graph were checked. GitHub issue links are recorded in the plan index.

## Issue #5 delivered locally — 2026-10-10

Added a frozen exploratory temporal-audit protocol, reproducible rolling-day evaluator, leakage/gate tests and a report with split hashes, class counts, confusion matrices, selective risk, per-day variation, latency and memory. Shipped model/manifest/replay unchanged. Four-sensor candidates fail temporal coverage/safety gates; Light is an offline experiment only. Campus generalization remains unvalidated until independently labeled new-room sessions exist. See backend/benchmarks/occupancy/REPORT.md. Temporal tests and existing model tests pass; no hardware work. Code is local until an explicit push.

## Issue #6 delivered locally — 2026-10-10

Versioned activity_first/water_first campus policies, bounded within-tier fairness and switching preferences are configurable through GET/PUT /api/v1/allocation/policy. Hard T1/feeder/source constraints and restoration dwell stay fixed. Snapshot explanations include per-load reasons/score terms, immutable optimization inputs and exact applied-gate replay. Policy/schema/TypeScript/test changes are coordinated. Idle ticks preserve the trace. See docs/ALLOCATION_POLICIES.md. Six services profile at 1.59-ms median; experimental 19 leaves take 11.95 s, so that path stays offline and no unused solver was installed. Safety/control-loop/policy tests pass. Durable persistence and a shared 19-leaf dispatch engine remain outside this issue.

## Issue #7 delivered locally — 2026-10-10

Optional POST /api/v1/studies/electrical runs a balanced 400-V radial AC study on a worker thread; the campus source explicitly labels watt_budget limitations. Power Grid Model 1.13.193 is selected; NetworkX is connectivity-only and pandapower 3.5.6 is offline comparison-only. Result contracts include units, provenance, engine/version, convergence, independent I²R power-balance residual, null islands/failures and no restoration authorization. Observations pass through existing diagnosis validation; no thermal values are fabricated. Busy/timeout/stale-run-or-revision paths are covered, including keeping timed-out work serialized. Engine installed and tested in both the main Python 3.14.7 ML environment and isolated Python 3.12.15 benchmark environment. Detailed assumptions, licenses, matched cases, compatibility and latency evidence are in docs/ELECTRICAL_SIMULATION.md and backend/benchmarks/results/electrical_report.json. No hardware work or field-validation claim. Publication awaits explicit push.

## Issue #25 integration

Integrated PR #36 with current `main`, preserving the app-scoped state, shared WebSocket store, controller and hardware/UI work. SQLite history now drives chart data and read-only timeline playback; fault incidents are stored and emit durable open/resolve events. Current verification: 151 backend tests passed and the frontend production build passed. The history DOM suite is committed but could not run here because jsdom is absent and package downloads are blocked; the browser dashboard showed the updated controls, while the existing backend on port 8000 predates the new API. Keep #25 open pending its #12/#14 contract gates and history DOM check. Details: [docs/ISSUE_25_DELIVERY.md](docs/ISSUE_25_DELIVERY.md).

### Final verification for issues #5–#7

- `PYTHONPATH=backend .venv-ml/bin/python -m pytest backend/tests -q` — **119 passed**, including optional PGM in the Python 3.14.7 ML runtime.
- `PYTHONPATH=backend .venv-electrical/bin/python -m pytest backend/tests/test_electrical.py -q` — **16 passed**, Python 3.12.15; only a dependency TestClient deprecation warning.
- `cd frontend && npm run build` — passed; existing large-bundle warning remains. No interface redesign.
- Temporal evaluator rerun from `/tmp/occupancy.zip`; benchmark scripts produced checked-in evidence. Original model binary/manifest/replay diff is empty. No physical hardware tested, no campus labels invented, no GitHub reuse files uploaded.
- GitHub issues #5/#6/#7 were already marked closed (without linked closing PRs or implementation comments) when inspected. This delivery adds actual local implementation/evidence; it does not rely on those status labels. Commits remain local pending an explicit push.

## Prior art and claim boundaries

Added [docs/NOVELTY_AND_PRIOR_ART.md](docs/NOVELTY_AND_PRIOR_ART.md) to compare the demonstrated prototype with established occupancy, allocation, diagnosis and educational tools. The document explicitly limits the "mesh" name, campus ML generalization, physical switching and energy-savings claims. Novelty here is a prototype integration claim; independent field validation remains future work.

## Issue #14 generated API contract — 2026-10-10

Implemented on `codex/remaining-open-issues`: typed every HTTP route, exported stable method/path operation IDs and a version marker, added documented API errors and the named WebSocket envelope, generated frontend contracts, and added runtime validation before WebSocket snapshots enter cache. Added route/schema determinism tests, malformed-envelope tests, and an API-contract GitHub Actions workflow. Snapshot site identity is validated as a typed model throughout the history recorder. See [docs/ISSUE_14_DELIVERY.md](docs/ISSUE_14_DELIVERY.md); verification is recorded there.

## Issue #12 SQLite audit completion — 2026-10-10

On `codex/remaining-open-issues`, completed durable command/event/decision/incident/ACK history: site command UUIDs are stored and returned in receipts, decisions reference the command, ACK keys deduplicate retries, and run-linked records reject orphan writes. Added v1 SQLite migration tracking, visibly degraded health, verified online backups for both databases, and restart/backup/retention coverage. Raw RFID UIDs stay out of audit payloads. Physical ACKs remain rejected until a verified protocol exists. See [docs/ISSUE_12_DELIVERY.md](docs/ISSUE_12_DELIVERY.md).

## Current backlog follow-up — 2026-10-10

Issue #21 software session semantics now use `GridState.active_sessions` across the campus, classroom visualizer, RFID API and fake-board gateway adapter. Requests bind to the current run and support bounded event-ID replay protection; stale/out-of-order times reject, and new runs clear active sessions. See [docs/ISSUE_21_DELIVERY.md](docs/ISSUE_21_DELIVERY.md). Focused checks passed 53; full backend checks passed 163. ESP32 A/B interoperability remains unverified.

Issue #19's frozen developer-held-out diagnostic split was unsealed and reported once. Results are in `backend/benchmarks/diagnosis/results/diagnosis_heldout.{md,json}`; rank/top-k metrics from the actual multi-hypothesis outputs are not yet captured, so keep #19 open and do not tune against that revealed split.

## Issue #16 frontend tests — in progress

Kept the shared live-state socket and server-history flow from `main`; integrated useful WIP fixtures and component tests without duplicating the socket implementation. Added tests for both facility visualizers and power-edge states, automated accessibility scans, API-shape fixture checks, and Playwright route navigation. Local tests pass; the issue remains open pending CI and any remaining acceptance gaps.

## Person B city demo and predictive demand — 2026-10-10

Added a causal 10–60-second Ridge demand forecast trained on reproducible synthetic sessions (80 train / 20 calibration / 20 test); inputs are previous requested watts, never post-shedding power. Synthetic 60-second MAE is 149.49 W versus 469.59 W persistence. Live forecasting waits for four 10-second readings and abstains on stale/gapped observations or abrupt demand changes. Rehearsal samples remain explicitly synthetic and cannot alter the grid. The API exposes one revision for source, hospital and classroom panels, candidate fixed-priority comparison, forecast and gateway-reported hardware status. The landing page now reads measured inference/allocation results from checked-in JSON rather than placeholder percentages.

The new `/demo` city view preserves the six-service 14 kW electrical catalog and guides shortages, feeder trips, repair and staged recovery. `/console` retains history and engineering controls; facility drill-downs remain available. Hardware LED display now requires a fresh connected confirmation, including after stale links. B5 flashing, pairing, physical acceptance and hardware backup video remain deferred by the user's explicit request.

Checks so far: 9 new backend forecasting/city tests pass; frontend production build passes with the existing bundle-size warning; 17 component tests pass. The real-backend browser smoke check exposed and fixed a feeder-toggle error, then a mobile hardware-input overflow; final rerun is pending. The concurrent full backend suite had two diagnosis failures during separate in-progress diagnosis edits; no passing full-suite result is claimed here. Final verification and remaining Person B work will be recorded below.

### City demo verification and gateway lock ordering

Final real-controller browser journey passed: shortage, shared revisions, forecast warning, feeder A trip, critical shortfall, repair, dwell and full requested-service recovery. The existing facility-navigation browser check also passed (2 browser tests total). All 18 frontend component tests and the production build pass; four history checks and the runtime contract check pass. Current backend suite: 179 passed. City reads now release the site lock before reading the gateway, preventing a site/gateway lock inversion; a regression check verifies that order. No physical hardware was queried, connected or flashed.

### Hospital diagnostic rehearsal

Added hospital drill-down controls for normal, overload, cooling failure, combined overload/cooling, upstream loss, dropout and stuck-sensor examples. They show ordered hypotheses, supporting evidence, uncalibrated evidence scores and explicit inspection instructions. The stuck-sensor example supplies three causal observations and returns ABSTAINED; its card says sensor evidence is untrusted. These are clearly labeled, read-only diagnostic rehearsals using the existing separate 100 A fixtures; they do not claim persistent fault injection into the city. A4 stateful injection and A3 reconciliation of the legacy 7 kW hospital equipment drill-down remain backend handoffs. Generated request types, example fixtures, API/shape checks and the UI regression test were updated together. Current full backend suite (179 tests), frontend component suite (18 tests), and production build pass.

### Demo naming and copy cleanup

Blackout Mesh now names the landing page, header, browser title and engineering console consistently. Removed the unused hidden duplicate hero. The visible hero advertises the implemented demand forecast and city recovery guide with synthetic-training and hardware-verification qualifications. Frontend production build and component checks pass; no hardware work.

### Person B presentation handoff

README now opens with the recorded software demo GIF, states real/simulated boundaries, reproduces the measured 6 kW comparison (including switches and unmet Wh), and gives local startup instructions. Planning documents moved to `docs/planning/`; AGENTS/context/progress references and new Markdown links were checked. See `docs/DEMO_GUIDE.md` for the city/forecast/recovery script, evidence provenance, test setup and B1–B7 status. Generated-client check and the final two browser checks pass after all UI changes. No push by this task. B5 remains on hold; A1/A3/A4 backend dependencies remain explicit rather than being presented as completed results.

### Local preview refreshed

Restarted this project's existing localhost backend with its original environment and hardware auto-connect disabled; the new city API is available at port 8000 and the frontend preview at `http://127.0.0.1:5173/demo`. No demo commands or physical connection were sent to the user's live instance. Added ignore rules for SQLite WAL/shared-memory sidecars created by normal application startup; existing local evidence files were preserved. `git check-ignore` confirms both sidecars are excluded.

### PR integration with main — 2026-10-10

Integrated main's A1 rank-dwell benchmark, A3 shared 6 kW hospital catalog and A4 persistent fault controls. Read-only diagnostic buttons now send an explicit `rehearsal` field; mixed rehearsal/live requests reject. Removed the duplicate stuck-sensor rule in favor of main's latched uncertainty and cooling-aware detection. Frozen ranked manifests/results retain their original detector identity; regression checks verify changed rules refuse unsealing rather than rewriting that provenance. No new held-out run was performed. README/demo guide now include the 385-run allocation evidence and rank-dwell comparison. Earlier pending A1/A3/A4 notes above are superseded by this integration. B5 remains on hold.

Validation: 197 backend tests passed against temporary databases; 18 frontend component tests, 4 history tests, runtime contract check, production build and 2 real-browser checks passed. Dependency audit found zero vulnerabilities. The existing frontend bundle-size warning remains. Publication requested by the user; no merge or hardware operation authorized by this update.


### #19 ranked held-out v3 — 2026-10-10

Ranked v2 could not be unsealed (frozen against a detector that changed before it ran). Froze `diag-bench-ranked-v3` (seeds 5000–5007) against the current detector, committed it, then unsealed it once. All fault families detected 8/8 with zero safety violations; top-1/top-3/MRR 1.0 on all 80 ranked cases; dropout and stuck-sensor abstention precision/recall 1.0 (8/8 each). Results in `backend/benchmarks/diagnosis/results/diagnosis_ranked_v3_heldout.{md,json}`; details in `docs/ISSUE_19_DELIVERY.md`. This supersedes the earlier "keep #19 open" notes. Synthetic, developer-held-out only.

## Issue #26 configurable site profiles — 2026-10-10

The active site is one validated JSON profile (`SITE_PROFILE`, default `backend/sites/default_campus.json`); `app/core/active_site.py` loads it once and every module derives its catalog from `CATALOG` (services, classrooms and appliances, hospital zones and equipment, LED bits, board A room letters, presets, protected T1 services). Validation is strict and lists every problem by asset before startup. `backend/sites/small_test_site.json` (4 services, 2 classrooms, 2 hospital zones) runs with no source edits. Snapshots, view identities and persisted decisions carry the profile's config hash. Real RFID UIDs go in the ignored `backend/sites/rfid_enrollment.local.json`. Details and limits: `docs/SITE_PROFILES.md`.

## Main sync on issue #19 branch — 2026-10-10

Merged `origin/main` into `codex/issue-19-ranked-evaluation` after the ranked v3 evaluation. The merge brings the configurable site profiles, appliance-level allocator and power-system `/demo` into the same branch as the held-out results. No unresolved paths or conflict markers remain; `git diff --check` passes. Full backend tests pass with a temporary `PRIORITYGRID_HISTORY_DB`: **395 passed, 2 skipped**. Frontend build and component tests passed during merge verification. No hardware checks or physical acceptance were run. Next: review the combined app in a browser, then continue the pending hardware A/B transport and catalog reconciliation work.

### Issue #63: Make SHIFT/GDM district topology generation reproducible
Added 	ools/setup_shift_and_generate.py script to automate obtaining the exact licensed SHIFT commit from https://github.com/NLR-Distribution-Suite/shift.git, setting up an isolated .venv-city runtime, and regenerating the GNITC topology deterministically without manual edits. The script avoids polluting the normal backend install with GIS/GDM dependencies. 
Verified by running python tools/setup_shift_and_generate.py, which checked out commit 995004c, generated 31 nodes and 31 edges identically to the checked-in topology, and then passed 	est_district_topology_generator.py locally within .venv-city. No physical grid model or runtime network calls are used.
