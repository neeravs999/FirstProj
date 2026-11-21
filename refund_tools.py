"""Simulated account data and the refund tools (agent_PRD 6.3-6.7).

Every eligibility and approval decision is made here, in plain code (FR-29/30, GR-05).
Nothing in this file calls a real billing, CRM or payment system (FR-35, GR-07).
"""
import copy
import logging
import uuid

from config import REFUND_APPROVAL_LIMIT, REFUND_WINDOW_DAYS

log = logging.getLogger("telecom_chatbot.refund")

# FR-15/16: stands in for the user ID an authenticated session would supply.
DEMO_USER_ID = "user_123"

# FR-14/18/18a: hard-coded demo data. Each chat session works on its own copy.
USERS = {
    "user_123": {
        "name": "Rahul",
        "plan": "Pro",
        "plan_amount": 999,
        "recharges": [
            {
                "recharge_id": "rch_456",
                "recharge_amount": 999,
                "recharge_status": "completed",
                "recharge_age_days": 2,
                "refund_status": "not_refunded",
            },
            {
                "recharge_id": "rch_457",
                "recharge_amount": 499,
                "recharge_status": "completed",
                "recharge_age_days": 1,
                "refund_status": "not_refunded",
            },
        ],
    }
}


def rupees(amount: float) -> str:
    return f"₹{amount:,.0f}" if float(amount).is_integer() else f"₹{amount:,.2f}"


def _clean(amount: float) -> float | int:
    return int(amount) if float(amount).is_integer() else float(amount)


def is_refundable(recharge: dict) -> bool:
    return (
        recharge["recharge_status"] == "completed"
        and recharge["recharge_age_days"] <= REFUND_WINDOW_DAYS
        and recharge["refund_status"] != "refunded"
    )


class RefundTools:
    """The four tools. Only get_user_account and validate_refund are ever shown to the
    LLM; process_refund and submit_to_support are called by application code (FR-23a)."""

    def __init__(self, users: dict | None = None):
        self.users = copy.deepcopy(USERS if users is None else users)
        self.support_queue: list[dict] = []   # simulated hand-off to the Support Team

    # ---- FR-19 ---------------------------------------------------------------
    def get_user_account(self, user_id: str) -> dict:
        user = self.users.get(user_id)
        if user is None:
            return {"found": False, "user_id": user_id}
        return {"found": True, "user_id": user_id, **copy.deepcopy(user)}

    def refundable_recharges(self, user_id: str) -> list[dict]:
        return [r for r in self.users.get(user_id, {}).get("recharges", []) if is_refundable(r)]

    def select_recharge(self, user_id: str, amount: float) -> dict | None:
        """FR-27a: pick the recharge a refund applies to, deterministically.

        1. A recharge whose amount matches exactly (even if already refunded).
        2. Otherwise the most recent refundable recharge that covers the amount.
        3. Otherwise the largest refundable recharge (so the "exceeds" reason is fair).
        4. Otherwise the most recent recharge (so the rejection names a real reason).
        """
        recharges = self.users.get(user_id, {}).get("recharges", [])
        if not recharges:
            return None
        exact = [r for r in recharges if r["recharge_amount"] == amount]
        if exact:
            return min(exact, key=lambda r: (not is_refundable(r), r["recharge_age_days"]))
        open_ = [r for r in recharges if is_refundable(r)]
        covering = [r for r in open_ if r["recharge_amount"] >= amount]
        if covering:
            return min(covering, key=lambda r: (r["recharge_age_days"], r["recharge_amount"]))
        if open_:
            return max(open_, key=lambda r: r["recharge_amount"])
        return min(recharges, key=lambda r: r["recharge_age_days"])

    # ---- FR-20, FR-24..30 ----------------------------------------------------
    def validate_refund(self, user_id: str, amount: float) -> dict:
        result = {
            "eligible": False,
            "reason": "",
            "requested_amount": _clean(amount) if amount is not None else None,
            "recharge_amount": None,
            "recharge_id": None,
        }

        def reject(reason: str) -> dict:
            result["reason"] = reason
            log.info("[Validation] eligible=False reason=%s", reason)
            return result

        if user_id not in self.users:
            return reject("Account not found.")
        if amount is None or amount <= 0:                                        # FR-26
            return reject("The refund amount must be greater than zero.")
        recharge = self.select_recharge(user_id, amount)
        if recharge is None:
            return reject("There are no recharges on this account to refund.")
        result["recharge_id"] = recharge["recharge_id"]
        result["recharge_amount"] = recharge["recharge_amount"]
        paid = rupees(recharge["recharge_amount"])
        if recharge["recharge_status"] != "completed":                           # FR-24
            return reject(f"Your {paid} recharge has not completed, so it can't be refunded.")
        if recharge["refund_status"] == "refunded":                              # FR-28, GR-06
            return reject(f"Your {paid} recharge has already been refunded.")
        if recharge["recharge_age_days"] > REFUND_WINDOW_DAYS:                   # FR-25
            return reject(
                f"Your {paid} recharge was made {recharge['recharge_age_days']} days ago, "
                f"which is outside the {REFUND_WINDOW_DAYS}-day refund window."
            )
        if amount > recharge["recharge_amount"]:                                 # FR-27, GR-04
            return reject(
                f"The requested amount of {rupees(amount)} exceeds the recharge amount of {paid}."
            )
        result["eligible"] = True
        result["reason"] = "Refund is eligible."
        log.info("[Validation] eligible=True recharge_id=%s", recharge["recharge_id"])
        return result

    # ---- FR-21, FR-31..35 (never exposed to the LLM) -------------------------
    def process_refund(self, user_id: str, amount: float) -> dict:
        """Simulated refund. Re-validates and re-checks the approval limit itself, so it
        can never refund something invalid or above the limit, whoever calls it."""
        log.info("[Agent] process_refund(amount=%s)", _clean(amount))
        check = self.validate_refund(user_id, amount)                            # GR-01
        if not check["eligible"]:
            log.info("[Refund] failed: %s", check["reason"])
            return {"success": False, "reason": check["reason"], "amount": _clean(amount),
                    "status": "not_refunded"}
        if amount > REFUND_APPROVAL_LIMIT:                                       # GR-08
            reason = f"Refunds above {rupees(REFUND_APPROVAL_LIMIT)} need Support Team review."
            log.info("[Refund] blocked: %s", reason)
            return {"success": False, "reason": reason, "amount": _clean(amount),
                    "status": "not_refunded"}
        recharge = next(r for r in self.users[user_id]["recharges"]
                        if r["recharge_id"] == check["recharge_id"])
        refund_id = f"ref_{uuid.uuid4().hex[:8]}"
        recharge["refund_status"] = "refunded"                                   # FR-33, FR-28a
        recharge["refund_id"] = refund_id
        log.info("[Refund] success refund_id=%s", refund_id)
        return {"success": True, "refund_id": refund_id, "amount": _clean(amount),
                "recharge_id": recharge["recharge_id"], "status": "refunded"}     # FR-34

    # ---- FR-21a, FR-38 (never exposed to the LLM) ----------------------------
    def submit_to_support(self, user_id: str, amount: float) -> dict:
        """Queue the request for the Support Team. Refund status is left unchanged, and
        the team's review is out of scope, so nothing here decides an outcome (GR-09)."""
        log.info("[Agent] submit_to_support(amount=%s)", _clean(amount))
        check = self.validate_refund(user_id, amount)
        request = {
            "submitted": True,
            "request_id": f"sup_{uuid.uuid4().hex[:8]}",
            "amount": _clean(amount),
            "recharge_id": check["recharge_id"],
            "status": "submitted_for_review",
        }
        self.support_queue.append(request)
        log.info("[Support] submitted request_id=%s", request["request_id"])
        return request
