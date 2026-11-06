"""PodoBank persona planner v0.1: creates plans, never executes banking APIs."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import random
import uuid

ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT / "config" / "personas.json"
PERIODS = {"morning": (7, 11), "daytime": (11, 17), "evening": (17, 23)}
PERIOD_NAMES = list(PERIODS)
FINANCIAL_ACTIONS = {"deposit", "withdrawal", "transfer", "card_payment"}
KST = timezone(timedelta(hours=9))


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def make_rng(seed, *context):
    token = json.dumps([seed, *context], ensure_ascii=True, separators=(",", ":"))
    value = int.from_bytes(sha256(token.encode()).digest()[:16], "big")
    return random.Random(value)


def chance(rng, probability):
    return rng.random() < probability


def weighted_choice(rng, weights):
    names = list(weights)
    return rng.choices(names, weights=[weights[k] for k in names], k=1)[0]


def draw_count(rng, weight_map):
    return int(weighted_choice(rng, weight_map))


def in_range(rng, bounds, step=1000):
    low, high = bounds
    if high < low or low <= 0:
        raise ValueError(f"Invalid positive range: {bounds}")
    return rng.randint((low + step - 1) // step, high // step) * step


def validate_config(cfg):
    if set(cfg["pool_sizes"]) != set(cfg["daily_active"]):
        raise ValueError("Pool and active persona keys must match")
    for persona, capacity in cfg["pool_sizes"].items():
        target = cfg["daily_active"][persona]
        if not 0 < target <= capacity:
            raise ValueError(f"Invalid active count for {persona}")
        spec = cfg["personas"][persona]
        for key in ("balance_view", "card", "transfer", "deposit", "withdrawal"):
            if not 0 <= spec[key] <= 1:
                raise ValueError(f"Invalid probability {persona}.{key}")
        for key in ("balance_repeats", "card_repeats", "transfer_repeats"):
            total = sum(spec[key].values())
            if abs(total - 1) > 0.000001:
                raise ValueError(f"Distribution must total 1: {persona}.{key}")
        if abs(sum(spec["time_weights"]) - 1) > 0.000001:
            raise ValueError(f"Time weights must total 1 for {persona}")
    if cfg["timezone"] != "Asia/Seoul":
        raise ValueError("v0.1 supports Asia/Seoul only")


def init_pool(cfg):
    """Create a repeatable 600-person synthetic pool; no real banking IDs."""
    validate_config(cfg)
    ids = []
    n = 1
    for persona, count in cfg["pool_sizes"].items():
        for _ in range(count):
            ids.append((f"sim-{n:04d}", persona))
            n += 1
    all_ids = [user_id for user_id, _ in ids]

    loan_stages = []
    for stage, weight in cfg["loan"]["initial_stage_weights"].items():
        loan_stages.extend([stage] * int(round(cfg["pool_sizes"]["P04"] * weight)))
    if len(loan_stages) > cfg["pool_sizes"]["P04"]:
        loan_stages = loan_stages[:cfg["pool_sizes"]["P04"]]
    while len(loan_stages) < cfg["pool_sizes"]["P04"]:
        loan_stages.append("exploring")
    make_rng(cfg["seed"], "loan-stages").shuffle(loan_stages)

    users = []
    loan_index = 0
    for user_id, persona in ids:
        rng = make_rng(cfg["seed"], "profile", user_id)
        spec = cfg["personas"][persona]
        other_ids = [item for item in all_ids if item != user_id]
        count_known = rng.randint(*spec["known_recipients"])
        known = rng.sample(other_ids, count_known)
        categories = rng.sample(cfg["merchant_categories"], 2)
        stage = None
        if persona == "P04":
            stage = loan_stages[loan_index]
            loan_index += 1
        users.append({
            "sim_user_id": user_id,
            "persona_type": persona,
            "age_band": rng.choice(["20s", "30s", "40s", "50s"]),
            "is_employed": chance(rng, 0.75),
            "opening_balance_krw": in_range(rng, spec["opening_balance"], step=10000),
            "monthly_income_krw": in_range(rng, spec["monthly_income"], step=10000),
            "salary_day": rng.randint(1, 28),
            "primary_device_id": f"device-{user_id}",
            "preferred_merchant_categories": categories,
            "known_recipient_sim_ids": known,
            "initial_loan_stage": stage,
            "backend_user_id": None
        })
    return users


def choose_slot(rng, spec):
    return rng.choices(PERIOD_NAMES, weights=spec["time_weights"], k=1)[0]


def choose_other_slot(rng, spec, exclude):
    options = [x for x in PERIOD_NAMES if x != exclude]
    weights = [spec["time_weights"][PERIOD_NAMES.index(x)] for x in options]
    return rng.choices(options, weights=weights, k=1)[0]


def choose_recipient(rng, user, all_users, spec):
    me = user["sim_user_id"]
    known = user["known_recipient_sim_ids"]
    if known and chance(rng, spec["existing_recipient_probability"]):
        return rng.choice(known), False
    options = [v["sim_user_id"] for v in all_users
               if v["sim_user_id"] != me and v["sim_user_id"] not in known]
    return rng.choice(options), True


def choose_category(rng, user, cfg, spec):
    preferred = user["preferred_merchant_categories"]
    if chance(rng, spec.get("preferred_merchant_probability", 0.55)):
        return rng.choice(preferred)
    others = [x for x in cfg["merchant_categories"] if x not in preferred]
    return rng.choice(others)


def make_operation(slot, rank, action, params=None, reason="", requires=None):
    return {"slot": slot, "rank": rank, "action": action,
            "params": params or {}, "reason": reason,
            "requires": requires or ["authenticated"]}


def user_operations(user, all_users, cfg, sim_date):
    """Generate attempted actions only; do not invent execution outcomes."""
    persona = user["persona_type"]
    spec = cfg["personas"][persona]
    rng = make_rng(cfg["seed"], "user-day", sim_date.isoformat(), user["sim_user_id"])
    base_slot = choose_slot(rng, spec)
    ops = []

    has_balance = chance(rng, spec["balance_view"])
    n_balance = draw_count(rng, spec["balance_repeats"]) if has_balance else 0
    if has_balance:
        ops.append(make_operation(base_slot, 10, "account_view", reason="routine_balance"))
    history_prob = (spec["history_if_balance"] if has_balance else spec["history_if_no_balance"]) \
        if persona == "P01" else spec["history"]
    if chance(rng, history_prob):
        history_slot = base_slot if has_balance else choose_slot(rng, spec)
        ops.append(make_operation(history_slot, 20, "history_view", reason="transaction_history"))

    if chance(rng, spec["card"]):
        for index in range(draw_count(rng, spec["card_repeats"])):
            ops.append(make_operation(
                choose_slot(rng, spec), 45 + index / 10, "card_payment",
                {"merchant_category": choose_category(rng, user, cfg, spec),
                 "amount_krw": in_range(rng, spec["card_amount"])},
                "daily_spend", ["authenticated", "merchant_available", "sufficient_balance"]
            ))

    if chance(rng, spec["transfer"]):
        for index in range(draw_count(rng, spec["transfer_repeats"])):
            recipient, new_recipient = choose_recipient(rng, user, all_users, spec)
            ops.append(make_operation(
                choose_slot(rng, spec), 40 + index / 10, "transfer",
                {"recipient_sim_user_id": recipient,
                 "is_new_recipient": new_recipient,
                 "amount_krw": in_range(rng, spec["transfer_amount"])},
                "daily_transfer", ["authenticated", "recipient_registered", "sufficient_balance"]
            ))

    # Salary-day deposits model a monthly inflow. Other deposits are optional.
    if sim_date.day == user["salary_day"]:
        ops.append(make_operation(
            choose_slot(rng, spec), 30, "deposit",
            {"amount_krw": user["monthly_income_krw"]}, "monthly_income"
        ))
    elif chance(rng, spec["deposit"]):
        ops.append(make_operation(
            choose_slot(rng, spec), 30, "deposit",
            {"amount_krw": in_range(rng, [10000, 150000])}, "occasional_inflow"
        ))

    if chance(rng, spec["withdrawal"]):
        ops.append(make_operation(
            choose_slot(rng, spec), 35, "withdrawal",
            {"amount_krw": in_range(rng, [10000, 150000])},
            "cash_withdrawal", ["authenticated", "sufficient_balance"]
        ))

    if persona == "P04":
        loan = cfg["loan"]
        stage = user["initial_loan_stage"]
        if stage in {"exploring", "ready"}:
            loan_slot = choose_slot(rng, spec)
            if chance(rng, loan["product_view_if_eligible"]):
                ops.append(make_operation(
                    loan_slot, 50, "loan_products", reason="loan_product_research"
                ))
            if stage == "ready" and chance(rng, loan["application_if_ready"]):
                ops.append(make_operation(
                    loan_slot, 60, "loan_apply",
                    {"selection_strategy": "choose_from_live_loan_products",
                     "requested_amount_krw": in_range(rng, [1000000, 30000000], 1000000),
                     "preferred_term_months": rng.choice([12, 24, 36, 48, 60])},
                    "loan_application_candidate",
                    ["authenticated", "eligible_no_active_loan", "product_terms_valid"]
                ))
        elif chance(rng, loan["loan_view_if_pending_or_repaying"]):
            ops.append(make_operation(
                choose_slot(rng, spec), 55, "loan_view",
                reason="loan_status_check", requires=["authenticated", "existing_loan"]
            ))
    elif chance(rng, spec["loan_products"]):
        ops.append(make_operation(choose_slot(rng, spec), 50, "loan_products",
                                  reason="occasional_loan_interest"))

    # Repeated balance views follow real planned transactions when possible.
    money_ops = [op for op in ops if op["action"] in FINANCIAL_ACTIONS]
    used_slots = {base_slot}
    for repeat in range(max(n_balance - 1, 0)):
        if money_ops and chance(rng, 0.75):
            slot = rng.choice(money_ops)["slot"]
            ops.append(make_operation(slot, 80 + repeat / 10, "account_view",
                                      reason="post_transaction_balance"))
        else:
            slot = choose_other_slot(rng, spec, base_slot)
            if slot in used_slots and len(used_slots) < len(PERIOD_NAMES):
                available = [x for x in PERIOD_NAMES if x not in used_slots]
                slot = rng.choice(available)
            ops.append(make_operation(slot, 15 + repeat / 10, "account_view",
                                      reason="repeat_balance_check"))
            used_slots.add(slot)
    return ops, base_slot


def stamp_for_slot(sim_date, slot, rng):
    start_hour, end_hour = PERIODS[slot]
    # Start early enough to finish a full session within its time period.
    hour = rng.randint(start_hour, end_hour - 2)
    minute = rng.randint(0, 39)
    return datetime.combine(sim_date, time(hour, minute), KST)


def to_plan_rows(user, ops, base_slot, cfg, sim_date, fds=False):
    per_slot = defaultdict(list)
    for item in ops:
        per_slot[item["slot"]].append(item)
    if not per_slot:
        per_slot[base_slot] = []
    rows = []
    for session_index, slot in enumerate(PERIOD_NAMES, start=1):
        if slot not in per_slot:
            continue
        rng = make_rng(cfg["seed"], "session-time", sim_date.isoformat(),
                       user["sim_user_id"], slot)
        start = stamp_for_slot(sim_date, slot, rng)
        sess_key = f"{user['sim_user_id']}:{sim_date.isoformat()}:{slot}"
        device = f"new-device-{user['sim_user_id']}:{sim_date.isoformat()}" \
            if fds else user["primary_device_id"]
        ordered = [make_operation(slot, -1, "login", {"sim_device_id": device},
                                  "new_device_candidate" if fds else "begin_session", [])]
        ordered.extend(sorted(per_slot[slot], key=lambda op: op["rank"]))
        ordered.append(make_operation(slot, 999, "logout", reason="end_session"))
        now = start
        for pos, op in enumerate(ordered):
            if pos > 0:
                now += timedelta(minutes=rng.randint(1, 3))
            row_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{sess_key}:{pos}:{op['action']}"))
            rows.append({
                "plan_id": row_id,
                "sim_user_id": user["sim_user_id"],
                "persona_type": user["persona_type"],
                "session_key": sess_key,
                "planned_at": now.isoformat(),
                "action": op["action"],
                "params": op["params"],
                "reason": op["reason"],
                "requires": op["requires"],
                "scenario_tag": "new_device_transfer_candidate" if fds else None,
                "execution_status": "PLANNED"
            })
    return rows


def select_active_users(profiles, cfg, sim_date):
    by_type = defaultdict(list)
    for profile in profiles:
        by_type[profile["persona_type"]].append(profile)
    selected = []
    for persona, target in cfg["daily_active"].items():
        rng = make_rng(cfg["seed"], "activate", sim_date.isoformat(), persona)
        selected.extend(rng.sample(by_type[persona], target))
    return sorted(selected, key=lambda x: x["sim_user_id"])


def build_daily_plan(profiles, cfg, sim_date):
    validate_config(cfg)
    active = select_active_users(profiles, cfg, sim_date)
    staged = {}
    for user in active:
        staged[user["sim_user_id"]] = user_operations(user, profiles, cfg, sim_date)

    # FDS candidates are only plans, never fraud labels or success events.
    qualified = [u for u in active if u["persona_type"] == "P03"
                 and any(x["action"] == "transfer" for x in staged[u["sim_user_id"]][0])]
    wanted = min(cfg["fds"]["new_device_transfer_candidates_per_day"], len(qualified))
    flagged = make_rng(cfg["seed"], "fds-candidate", sim_date.isoformat()).sample(qualified, wanted)
    flagged_ids = {u["sim_user_id"] for u in flagged}
    for user in flagged:
        ops, _ = staged[user["sim_user_id"]]
        transfer = next(x for x in ops if x["action"] == "transfer")
        amount = transfer["params"]["amount_krw"]
        # Capped by synthetic balance; actual backend limits still prevail.
        balance_cap = (user["opening_balance_krw"] * 7 // 10 // 1000) * 1000
        transfer["params"]["amount_krw"] = min(10000000, balance_cap,
                                                  max(750000, amount * 5))
        transfer["reason"] = "fds_unusual_transfer_candidate"

    all_rows = []
    for user in active:
        ops, base_slot = staged[user["sim_user_id"]]
        all_rows.extend(to_plan_rows(user, ops, base_slot, cfg, sim_date,
                                     fds=user["sim_user_id"] in flagged_ids))
    all_rows.sort(key=lambda x: (x["planned_at"], x["sim_user_id"], x["plan_id"]))

    # Limit daily loan application candidates without fabricating an application result.
    loan_apps = [row for row in all_rows if row["action"] == "loan_apply"]
    limit = cfg["loan"]["max_daily_applications"]
    if len(loan_apps) > limit:
        to_drop = {row["plan_id"] for row in loan_apps[limit:]}
        all_rows = [row for row in all_rows if row["plan_id"] not in to_drop]
    summary = summarize(all_rows, active, cfg, sim_date)
    validate_plan(all_rows, cfg, sim_date)
    return all_rows, summary


def summarize(rows, active, cfg, sim_date):
    actions = Counter(row["action"] for row in rows)
    types = Counter(user["persona_type"] for user in active)
    participation = {}
    for persona in sorted(cfg["daily_active"]):
        denominator = cfg["daily_active"][persona]
        counts = {}
        for action in ("account_view", "history_view", "card_payment", "transfer",
                       "deposit", "withdrawal", "loan_products", "loan_apply", "loan_view"):
            participating = {row["sim_user_id"] for row in rows
                             if row["persona_type"] == persona and row["action"] == action}
            counts[action] = {"users": len(participating),
                              "percent": round(100 * len(participating) / denominator, 1)}
        participation[persona] = counts
    return {
        "date": sim_date.isoformat(),
        "timezone": cfg["timezone"],
        "mode": "PLAN_ONLY_NO_API_CALLS",
        "users_active": len(active),
        "active_by_persona": dict(sorted(types.items())),
        "planned_actions": len(rows),
        "planned_actions_by_type": dict(sorted(actions.items())),
        "participation_by_persona": participation,
        "fds_candidate_users": len({r["sim_user_id"] for r in rows if r["scenario_tag"]}),
        "notes": [
            "PLANNED actions are not API results or MongoDB events.",
            "A backend executor must validate current balances, loans and recipients.",
            "Virtual planned_at is not server occurred_at or collected_at."
        ]
    }


def validate_plan(rows, cfg, sim_date):
    if len({r["plan_id"] for r in rows}) != len(rows):
        raise ValueError("Duplicate plan IDs")
    active = {r["sim_user_id"] for r in rows}
    if len(active) != sum(cfg["daily_active"].values()):
        raise ValueError("Wrong number of daily distinct active users")
    by_persona = defaultdict(set)
    sessions = defaultdict(list)
    for row in rows:
        if row["execution_status"] != "PLANNED":
            raise ValueError("Planner must not claim execution results")
        if row["action"] not in {
            "login", "logout", "account_view", "history_view", "transfer",
            "card_payment", "deposit", "withdrawal", "loan_products", "loan_apply", "loan_view"
        }:
            raise ValueError(f"Unknown action: {row['action']}")
        if not row["planned_at"].startswith(sim_date.isoformat()):
            raise ValueError("Wrong planned date")
        by_persona[row["persona_type"]].add(row["sim_user_id"])
        sessions[row["session_key"]].append(row)
        if row["action"] == "transfer" and row["params"]["recipient_sim_user_id"] == row["sim_user_id"]:
            raise ValueError("Self transfer")
    for persona, expected in cfg["daily_active"].items():
        if len(by_persona[persona]) != expected:
            raise ValueError(f"Wrong active users for {persona}")
    for session, entries in sessions.items():
        seq = sorted(entries, key=lambda x: x["planned_at"])
        if seq[0]["action"] != "login" or seq[-1]["action"] != "logout":
            raise ValueError(f"Session not bracketed by login/logout: {session}")
        if len([x for x in seq if x["action"] == "login"]) != 1:
            raise ValueError(f"Session has multiple logins: {session}")
        if (datetime.fromisoformat(seq[-1]["planned_at"]) -
                datetime.fromisoformat(seq[0]["planned_at"])).total_seconds() >= 60 * 60:
            raise ValueError(f"Session exceeds 60 minutes: {session}")
    if sum(r["action"] == "loan_apply" for r in rows) > cfg["loan"]["max_daily_applications"]:
        raise ValueError("Too many loan applications")


def write_plan(rows, summary, outdir, sim_date):
    outdir.mkdir(parents=True, exist_ok=True)
    plan_path = outdir / f"plan_{sim_date.isoformat()}.jsonl"
    with plan_path.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    summary_path = outdir / f"summary_{sim_date.isoformat()}.json"
    save_json(summary_path, summary)
    return plan_path, summary_path


def main():
    parser = argparse.ArgumentParser(description="PodoBank simulator plan-only generator")
    parser.add_argument("command", choices=["init", "plan", "validate"])
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=ROOT / "data")
    parser.add_argument("--date", type=date.fromisoformat, default=date.today())
    parser.add_argument("--days", type=int, default=1)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    cfg = load_json(args.config)
    validate_config(cfg)
    profiles_path = args.output / "profiles.json"
    if args.command == "init":
        if profiles_path.exists() and not args.force:
            parser.error(f"{profiles_path} exists. Use --force to overwrite.")
        profiles = init_pool(cfg)
        save_json(profiles_path, profiles)
        print(f"Initialized {len(profiles)} synthetic profiles: {profiles_path}")
        return
    if not profiles_path.exists():
        parser.error("Profiles not found. Run 'init' first.")
    profiles = load_json(profiles_path)
    if len(profiles) != sum(cfg["pool_sizes"].values()):
        parser.error("Profile count does not match config; re-initialize separately.")
    if args.days < 1 or args.days > 365:
        parser.error("--days must be 1..365")
    for offset in range(args.days):
        day = args.date + timedelta(days=offset)
        rows, summary = build_daily_plan(profiles, cfg, day)
        if args.command == "plan":
            plan, report = write_plan(rows, summary, args.output, day)
            print(f"{day} | {summary['users_active']} users | {len(rows)} actions | {plan}")
            print(f"Summary: {report}")
        else:
            existing = args.output / f"plan_{day.isoformat()}.jsonl"
            if existing.exists():
                with existing.open("r", encoding="utf-8") as stream:
                    saved_rows = [json.loads(line) for line in stream if line.strip()]
                validate_plan(saved_rows, cfg, day)
                if rows != saved_rows:
                    raise SystemExit(f"Saved plan differs from reproducible plan: {existing}")
            print(f"Validated {day}: {summary['users_active']} users, {len(rows)} actions")


if __name__ == "__main__":
    main()
