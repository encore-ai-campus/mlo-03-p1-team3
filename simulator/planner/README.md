# PodoBank Persona Planner v0.1

A Python standard-library-only, **plan-only** starter. No browser, FastAPI, MariaDB,
MongoDB or Alloy connection occurs when you run this package. No success/failure
banking events are fabricated by the planner.

## Requirements

- Python 3.10 or newer (works on Windows, including PyCharm, and Ubuntu)
- No pip packages required for this stage

## Quickstart (PowerShell or Ubuntu terminal)

Run from the folder that contains `persona_sim.py`:

```bash
python persona_sim.py init --output data
python persona_sim.py plan --date 2026-11-06 --output data
python persona_sim.py validate --date 2026-11-06 --output data
python -m unittest discover -s tests -v
```

To generate an offline 7-day *plan* (not real transaction histories):

```bash
python persona_sim.py plan --date 2026-11-06 --days 7 --output data
```

The `init` command refuses to overwrite existing profiles. `--force` can
explicitly regenerate them (avoid using it after real user IDs are mapped).

## Files

- `config/personas.json`: editable v1.0 recommendation values
- `persona_sim.py`: reproducible pool/plan generator and validator
- `tests/test_persona_sim.py`: built-in unittest suite
- `samples/profiles.json`: 600 synthetic personas; `backend_user_id` is null
- `samples/plan_2026-11-06.jsonl`: 400 distinct active users' planned actions
- `samples/summary_2026-11-06.json`: daily plan counts

## Output semantics

Every plan row has `sim_user_id`, `persona_type`, `planned_at` (+09:00),
`session_key`, `action`, `params`, `requires`, `scenario_tag`, and
`execution_status=PLANNED`. This is an **action request to be performed**, not
an application log or a MongoDB event. Only the backend can confirm success.

- `login`/`logout`: bracket each planned activity session, usually <60 min.
- `account_view`, `history_view`: read-only actions.
- `transfer`: the recipient is a **simulated user ID**, to be resolved to the
  **actual** seed-test account/phone by a future runner.
- `card_payment`: `merchant_category` must be resolved to a **live** merchant
  returned by the backend, not hardcoded as a fake merchant ID.
- `loan_apply`: `selection_strategy` requires a real loan product lookup and
  current eligibility check. A planned application is not proof of success.
- `scenario_tag=new_device_transfer_candidate`: only an experimental candidate.
  No claims of actual fraud or actual new-device detection are made.

`planned_at` is virtual simulation time. Real `occurred_at`, `collected_at`,
client/session information must be recorded by the backend and collection
pipeline after an API call.

## Deliberate limitations (integration to do)

1. No live API requests, Playwright browser execution, real login or signup.
2. No changing MariaDB balances or loan status. The `opening_balance_krw` and
   `initial_loan_stage` fields are **synthetic seed metadata**, not live state.
3. No daily state transitions from loan exploring -> applied -> approved ->
   repaying. A future executor must check the actual MariaDB/REST state before
   every financial action. Reusing the plan for several days does not imply
   that loans were granted or balances changed.
4. Plan rows can reference simulated recipients that have not yet been seeded
   into the backend. All 600 accounts should be created/mapped before execution.
5. The real Vue selectors and actual backend API responses must be inspected
   before authoring a browser-based Playwright runner. This package does not
   assume your team has already implemented those interfaces.
6. Login failures, controlled validation failures, admin approvals and
   actual loan repayment batches require separate scenario/state wiring.
7. The generator targets per-persona participation probabilities; it does not
   artificially force individual days to exactly match every probability.

## Integration contract

`sim_user_id` -> test account in MariaDB -> browser/API authenticated session.
For each plan row, an executor should:

1. Sort by `planned_at` and group by `session_key`.
2. Login with the mapped seeded account (keep credentials out of JSONL).
3. Fetch real balance, merchants, available loan products and loan state.
4. Execute only valid actions against documented Vue/API behavior; use real
   responses for success/failure, never invent them.
5. Record an execution report with `plan_id`, `request_id` if returned,
   actual response status, and timestamps; do not alter/overwrite source logs.
6. Compare backend output to MariaDB ledger, MongoDB events and (if enabled)
   app.log / Alloy / Loki independently.

For safety, run against a disposable local/VM test environment only.
