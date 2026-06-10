"""Transaction blocking rules engine.

Admins define rules in the `transaction_rules` collection. Before a transaction
is processed, every enabled rule is evaluated against it. The first matching
``block`` rule rejects the transaction; ``flag`` rules mark it for review but
let it through. Matched rules have their ``trigger_count`` incremented.

A transaction is a plain dict with (optionally) these keys:
    amount, merchant, category, tag, country, card_type, user_id

Rule config by ``rule_type``:
    merchant   → {"value": "amazon"} or {"values": ["amazon", "ebay"]}  (substring, case-insensitive)
    category   → {"value": "Travel"} or {"values": [...]}               (exact, case-insensitive)
    country    → {"value": "NG"} or {"values": [...]}                   (exact, case-insensitive)
    card_type  → {"value": "amex"} or {"values": [...]}                 (exact, case-insensitive)
    amount_range → {"min": 1000, "max": 5000}  (either bound optional)
    user       → {"user_id": "<id>"}
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from bson import ObjectId

from database import transaction_rules_collection


def _as_list(config: Dict[str, Any]) -> List[str]:
    vals = config.get("values")
    if isinstance(vals, list) and vals:
        return [str(v).strip().lower() for v in vals if str(v).strip()]
    single = config.get("value")
    if single is not None and str(single).strip():
        return [str(single).strip().lower()]
    return []


def _matches(rule: Dict[str, Any], txn: Dict[str, Any]) -> bool:
    rtype = rule.get("rule_type")
    cfg = rule.get("config") or {}

    if rtype == "merchant":
        merchant = str(txn.get("merchant") or "").lower()
        if not merchant:
            return False
        return any(v in merchant for v in _as_list(cfg))

    if rtype == "category":
        cat = str(txn.get("category") or txn.get("tag") or "").lower()
        return cat in _as_list(cfg) if cat else False

    if rtype == "country":
        country = str(txn.get("country") or "").lower()
        return country in _as_list(cfg) if country else False

    if rtype == "card_type":
        ct = str(txn.get("card_type") or "").lower()
        return ct in _as_list(cfg) if ct else False

    if rtype == "amount_range":
        try:
            amount = float(txn.get("amount", 0))
        except (TypeError, ValueError):
            return False
        lo = cfg.get("min")
        hi = cfg.get("max")
        if lo is not None and amount < float(lo):
            return False
        if hi is not None and amount > float(hi):
            return False
        # At least one bound must be set for the rule to be meaningful.
        return lo is not None or hi is not None

    if rtype == "user":
        return str(txn.get("user_id") or "") == str(cfg.get("user_id") or "")

    return False


def evaluate(txn: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate all enabled rules against a transaction.

    Returns a dict:
        {
          "blocked": bool,
          "block_rule": {id, name} | None,
          "flags": [ {id, name}, ... ],
          "reason": str | None,
        }
    Best-effort: any DB hiccup yields "not blocked" so a rules outage never
    halts legitimate transactions.
    """
    result = {"blocked": False, "block_rule": None, "flags": [], "reason": None}
    try:
        rules = list(transaction_rules_collection.find({"enabled": True}))
    except Exception:
        return result

    matched_ids: List[ObjectId] = []
    for rule in rules:
        if not _matches(rule, txn):
            continue
        matched_ids.append(rule["_id"])
        info = {"id": str(rule["_id"]), "name": rule.get("name", "")}
        if rule.get("action") == "block" and not result["blocked"]:
            result["blocked"] = True
            result["block_rule"] = info
            result["reason"] = f"Blocked by rule '{rule.get('name')}' ({rule.get('rule_type')})"
        elif rule.get("action") == "flag":
            result["flags"].append(info)

    # Increment trigger counts for matched rules (best effort).
    if matched_ids:
        try:
            transaction_rules_collection.update_many(
                {"_id": {"$in": matched_ids}}, {"$inc": {"trigger_count": 1}}
            )
        except Exception:
            pass

    return result
