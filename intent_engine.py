"""Auditable prototype rules, consent gate, backtest, and cross-intent arbitration.

No LLM or predictive model is involved. All customers and statistics are synthetic.
"""
import csv
from collections import Counter
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).parent / "data"
TIER = {"service": 0, "guidance": 1, "offers": 2}
# Only these signals can be read by a rule. Childcare is an explicit customer opt-in,
# never inferred from purchases, marital status, or other sensitive proxies.
CATALOGUE = {
    "age": {"type": "number", "sensitivity": "low", "min_tier": "service", "description": "You are an adult"},
    "monthly_surplus_avg_3m": {"type": "number", "sensitivity": "medium", "min_tier": "guidance", "description": "Your estimated monthly surplus is below the selected threshold"},
    "savings_balance": {"type": "number", "sensitivity": "medium", "min_tier": "guidance", "description": "Your savings balance is below the selected threshold"},
    "cashflow_squeeze_30d_forecast": {"type": "bool", "sensitivity": "medium", "min_tier": "guidance", "description": "Your recurring payments may leave a smaller buffer this month"},
    "rent_payment_detected": {"type": "bool", "sensitivity": "low", "min_tier": "guidance", "description": "A regular rent payment appears on your account"},
    "moved_recently_likely": {"type": "bool", "sensitivity": "medium", "min_tier": "guidance", "description": "Your address was recently updated"},
    "childcare_planning_opt_in": {"type": "bool", "sensitivity": "medium", "min_tier": "guidance", "description": "You asked for childcare planning tips"},
}
FORBIDDEN = {"new_child_likely", "health_spend_level", "religious_affiliation", "political_affiliation", "marital", "term_deposit"}
# Templates and their compliance class are FIXED; free text selects a template, it
# never changes conditions or releases new signal names/marketing messages.
TEMPLATES = {
    "childcare": dict(intent_id="childcare", title="Childcare planning", description="Support customers who explicitly asked for childcare planning tips.",
        conditions=[{"signal": "age", "op": ">=", "value": 18}, {"signal": "childcare_planning_opt_in", "op": "=", "value": True}, {"signal": "monthly_surplus_avg_3m", "op": "<", "value": 300}],
        priority=4, cooldown_days=30, compliance_class="guidance", min_consent_tier="guidance", channels=["app", "email"],
        message="Planning for childcare, {name}? Explore a simple budget plan for the coming months.",
        explanation="You opted in to childcare planning tips and your estimated monthly buffer is below €300."),
    "buffer": dict(intent_id="buffer", title="Build a savings buffer", description="Offer a simple way to plan for variable expenses.",
        conditions=[{"signal": "age", "op": ">=", "value": 18}, {"signal": "monthly_surplus_avg_3m", "op": "<", "value": 350}, {"signal": "savings_balance", "op": "<", "value": 1200}],
        priority=3, cooldown_days=30, compliance_class="guidance", min_consent_tier="guidance", channels=["app", "email"],
        message="Want a little more breathing room, {name}? See a practical buffer-building checklist.",
        explanation="Your estimated monthly buffer and savings balance are below the thresholds for this tip."),
    "cashflow": dict(intent_id="cashflow", title="Upcoming cash-flow check", description="Offer a no-pressure overview of recurring outflows.",
        conditions=[{"signal": "age", "op": ">=", "value": 18}, {"signal": "cashflow_squeeze_30d_forecast", "op": "=", "value": True}],
        priority=5, cooldown_days=30, compliance_class="guidance", min_consent_tier="guidance", channels=["app", "email"],
        message="A few payments are coming up, {name}. Review your upcoming balance in one place.",
        explanation="Your recurring payments may leave a smaller buffer this month."),
    "moving": dict(intent_id="moving", title="Moving checklist", description="Offer customers who recently updated their address a practical checklist.",
        conditions=[{"signal": "age", "op": ">=", "value": 18}, {"signal": "moved_recently_likely", "op": "=", "value": True}, {"signal": "rent_payment_detected", "op": "=", "value": True}],
        priority=2, cooldown_days=30, compliance_class="guidance", min_consent_tier="guidance", channels=["app", "email"],
        message="Settling in, {name}? Here is a handy checklist for your new address.",
        explanation="You recently updated your address and a recurring rent payment appears on your account."),
}
KEYWORDS = {"childcare": ("childcare", "child care", "creche", "crèche", "nursery"),
            "buffer": ("savings", "saving", "buffer", "emergency fund"),
            "cashflow": ("cash flow", "cashflow", "upcoming bill", "upcoming payment"),
            "moving": ("moving", "move", "new address", "rent")}


@lru_cache(maxsize=1)
def population():
    with (DATA / "signals.csv").open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@lru_cache(maxsize=1)
def profiles():
    with (DATA / "customers.csv").open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def compile_intent(text):
    text = text.lower().strip()
    if not text:
        raise ValueError("Enter an intent before preparing a draft.")
    if any(term in text for term in ("health", "religion", "politic", "pregnan", "new parent", "baby", "birth", "under 18", "minor", "investment", "insurance", "loan offer")):
        raise ValueError("Unsupported or sensitive targeting request. Try a consent-based budgeting, childcare, cash-flow or moving tip.")
    found = [key for key, words in KEYWORDS.items() if any(word in text for word in words)]
    if len(found) != 1:
        raise ValueError("This guided demo supports one intent at a time: childcare, savings buffer, cash-flow or moving. Please be specific.")
    return {**TEMPLATES[found[0]], "source_text": text, "status": "draft"}


def validate(spec):
    """Rebuild from trusted template; reject mutated fields, unknown signals and forbidden classes."""
    key = spec.get("intent_id")
    if key not in TEMPLATES:
        raise ValueError("Unrecognised intent.")
    template = TEMPLATES[key]
    for field in ("conditions", "priority", "cooldown_days", "channels", "message", "explanation", "compliance_class", "min_consent_tier"):
        if spec.get(field) != template[field]:
            raise ValueError("Unreviewed rule, compliance class, or message. Approval denied.")
    for cond in spec["conditions"]:
        signal = cond["signal"]
        if signal in FORBIDDEN or signal not in CATALOGUE:
            raise ValueError("Forbidden or unknown signal.")
        if TIER[CATALOGUE[signal]["min_tier"]] > TIER[spec["min_consent_tier"]]:
            raise ValueError("Intent consent tier is too low for this signal.")
    if spec["compliance_class"] != "guidance" or not any(c == {"signal": "age", "op": ">=", "value": 18} for c in spec["conditions"]):
        raise ValueError("Only adult-facing guidance is supported.")
    return True


def satisfies(row, condition):
    signal, op, value = condition["signal"], condition["op"], condition["value"]
    if signal not in CATALOGUE:
        raise ValueError("Rule reads a non-catalogue signal")
    raw = row[signal]
    actual = int(raw) if CATALOGUE[signal]["type"] in ("number", "bool") else raw
    expected = int(value) if isinstance(value, bool) else value
    if op == "=":
        return actual == expected
    if op == "<":
        return actual < expected
    if op == ">=":
        return actual >= expected
    raise ValueError("Unsupported operator")


def matches(row, spec):
    return all(satisfies(row, c) for c in spec["conditions"])


def eligible(row, spec):
    if int(row["age"]) < 18:
        return False
    if TIER[row["consent_tier"]] < TIER[spec["min_consent_tier"]]:
        return False
    if not int(row["active"]):
        return False
    if not (set(spec["channels"]) & set(row["channels_allowed"].split("|"))):
        return False
    return True


def decide(row, intents, optouts=frozenset(), not_relevant=frozenset()):
    """Returns decisions, not delivered events. Budget = 1 nudge/30 days across all intents/channels."""
    candidates = []
    suppressed = []
    for spec in intents:
        validate(spec)
        if not matches(row, spec):
            continue
        item = {"intent_id": spec["intent_id"], "title": spec["title"]}
        if row["customer_id"] in optouts:
            suppressed.append({**item, "reason": "Personalisation opted out (session)"})
        elif row["customer_id"] in not_relevant:
            suppressed.append({**item, "reason": "Not relevant feedback (session)"})
        elif not eligible(row, spec):
            suppressed.append({**item, "reason": "Consent, age or channel gate"})
        elif int(row["contacted_last_30d"]):
            suppressed.append({**item, "reason": "30-day contact budget"})
        else:
            candidates.append(spec)
    candidates.sort(key=lambda s: (-s["priority"], s["intent_id"]))
    winner = candidates[0] if candidates else None
    for spec in candidates[1:]:
        suppressed.append({"intent_id": spec["intent_id"], "title": spec["title"], "reason": "Higher-priority nudge won the one-per-30-days budget"})
    return winner, suppressed


def backtest(draft, existing=()):
    validate(draft)
    for spec in existing:
        validate(spec)
    stats = Counter()
    age_reach = Counter()
    channel_reach = Counter()
    for row in population():
        if not matches(row, draft):
            continue
        stats["matched"] += 1
        if any(matches(row, spec) for spec in existing):
            stats["overlap"] += 1
        if eligible(row, draft):
            stats["consented"] += 1
        winner, suppressed = decide(row, [*existing, draft])
        if winner and winner["intent_id"] == draft["intent_id"]:
            stats["selected"] += 1
            age_reach[row["age_band"]] += 1
            channel = row["channel_preference"] if row["channel_preference"] in row["channels_allowed"].split("|") else "app"
            channel_reach[channel] += 1
        elif suppressed:
            stats["suppressed"] += 1
    return {**{k: stats[k] for k in ("matched", "consented", "overlap", "selected", "suppressed")},
            "ages": dict(age_reach), "channels": dict(channel_reach), "population": len(population()),
            "signals": [c["signal"] for c in draft["conditions"]]}


def customer_decision(profile, intents, optouts=frozenset(), not_relevant=frozenset()):
    row = next((r for r in population()[:len(profiles())] if r["customer_id"] == profile["customer_id"]), None)
    if row is None:
        raise ValueError("Profile not found")
    winner, suppressed = decide(row, intents, optouts, not_relevant)
    channel = row["channel_preference"] if row["channel_preference"] in row["channels_allowed"].split("|") else "app"
    return {"name": profile["first_name"], "age": int(row["age"]), "city": row["city"], "consent": row["consent_tier"],
            "channel": channel, "title": winner["title"] if winner else "No nudge sent",
            "message": winner["message"].format(name=profile["first_name"]) if winner else "Quiet is a valid outcome. There is no eligible nudge for this customer now.",
            "explanation": winner["explanation"] if winner else "Consent, recent contact, or targeting rules can prevent a suggestion.",
            "signals": [CATALOGUE[c["signal"]]["description"] for c in winner["conditions"] if c["signal"] != "age"] if winner else [],
            "suppressed": suppressed, "sent": bool(winner), "intent_id": winner["intent_id"] if winner else ""}
