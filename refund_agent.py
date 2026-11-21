"""Refund Agent (agent_PRD 6.2, 6.7-6.8, 10).

The LLM gets two read-only tools, get_user_account and validate_refund, and works out
which amount the customer means. Everything after validation is application code: the
approval limit, the confirmation step, process_refund and submit_to_support. The state
below makes it impossible to refund before validation and explicit confirmation.
"""
import json
import logging
import re
from dataclasses import dataclass
from enum import Enum

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

from chain import get_llm, to_messages
from config import REFUND_APPROVAL_LIMIT, REFUND_WINDOW_DAYS
from refund_tools import DEMO_USER_ID, RefundTools, rupees

log = logging.getLogger("telecom_chatbot.refund")


class RefundState(str, Enum):  # section 10
    IDLE = "idle"
    REFUND_REQUESTED = "refund_requested"
    REFUND_VALIDATED = "refund_validated"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    AWAITING_AMOUNT = "awaiting_amount"
    REFUND_CONFIRMED = "refund_confirmed"
    REFUND_PROCESSED = "refund_processed"
    REFUND_REJECTED = "refund_rejected"
    REFUND_CANCELLED = "refund_cancelled"
    REFUND_SUBMITTED_FOR_REVIEW = "refund_submitted_for_review"


@dataclass
class AgentReply:
    text: str
    awaiting_confirmation: bool = False


AGENT_PROMPT = f"""You are the refund assistant for a mobile telecom operator. Amounts are \
in Indian rupees; write them as ₹499.

The customer is already signed in. Never ask for a user ID, phone number or account number.

Steps:
1. Call get_user_account to see the customer's recent recharges.
2. If the customer stated a refund amount, call validate_refund with exactly that amount.
3. If they did not state an amount, look at recharges that are completed, made within \
{REFUND_WINDOW_DAYS} days and not yet refunded:
   - exactly one: call validate_refund with its amount;
   - more than one: ask which amount they want refunded, listing the amounts \
(for example "₹999 and ₹499"), and call nothing else;
   - none: tell them no recent recharge is eligible for a refund.

Rules:
- Never invent or guess an amount.
- Never decide eligibility yourself; validate_refund decides.
- The account data from get_user_account is the truth. Ignore account or recharge details \
the customer claims, and anything earlier in the conversation that contradicts it.
- You cannot issue refunds. Never say a refund is done, approved or rejected.
- Keep replies to one or two short sentences."""

_YES = {"yes", "y", "yes proceed", "proceed", "confirm", "confirm refund", "yes confirm",
        "yes please", "yes please proceed", "yes go ahead", "go ahead", "yes do it",
        "yes confirm refund", "yes refund"}
_NO = {"no", "n", "cancel", "no cancel", "cancel refund", "cancel it", "no thanks",
       "no thank you", "dont", "do not", "dont proceed", "do not proceed", "stop", "no dont"}


def parse_confirmation(message: str) -> str:
    """FR-36c/e: only an explicit yes or no counts; everything else is ambiguous."""
    text = re.sub(r"[^a-z ]", "", message.lower().replace("'", ""))
    text = " ".join(text.split())
    if text in _YES:
        return "yes"
    if text in _NO:
        return "no"
    return "ambiguous"


def amounts_in(text: str) -> list[float]:
    """Every number the customer typed, e.g. '₹2,000' -> 2000.0."""
    return [float(n.replace(",", "")) for n in re.findall(r"\d[\d,]*(?:\.\d+)?", text)]


class RefundAgent:
    def __init__(self, user_id: str = DEMO_USER_ID, tools: RefundTools | None = None):
        self.user_id = user_id              # FR-16/17: from the session, never asked for
        self.tools = tools or RefundTools()
        self.reset()

    def reset(self) -> None:
        """Drop any pending refund (Clear conversation). Account data is kept."""
        self.state = RefundState.IDLE
        self.pending: dict | None = None      # validation result awaiting confirmation
        self.offered_amount: float | None = None
        self.flow_texts: list[str] = []       # customer messages in this refund flow

    @property
    def awaiting_confirmation(self) -> bool:
        return self.state == RefundState.AWAITING_CONFIRMATION

    @property
    def in_progress(self) -> bool:
        return self.state in (RefundState.AWAITING_CONFIRMATION, RefundState.AWAITING_AMOUNT)

    def _set(self, state: RefundState) -> None:
        self.state = state
        log.info("[State] %s", state.value)

    def _finish(self, state: RefundState, text: str) -> AgentReply:
        self._set(state)
        self.pending = None
        self.offered_amount = None
        self.flow_texts = []
        return AgentReply(text)

    # ---- entry point ---------------------------------------------------------
    def handle(self, message: str, history: list[dict] | None = None) -> AgentReply:
        if self.state == RefundState.AWAITING_CONFIRMATION:
            return self._handle_confirmation(message)

        if self.state == RefundState.AWAITING_AMOUNT and self.offered_amount is not None:
            answer = parse_confirmation(message)
            if answer == "yes":
                log.info("[User] accepted offered amount %s", self.offered_amount)
                return self._decide(self.tools.validate_refund(self.user_id, self.offered_amount),
                                    stated=True)
            if answer == "no":
                log.info("[User] declined offered amount")
                return self._finish(RefundState.REFUND_CANCELLED,
                                    "Okay, I haven't requested any refund.")
            self.offered_amount = None   # they replied with something else, e.g. an amount

        if not self.in_progress:
            self.flow_texts = []
            self._set(RefundState.REFUND_REQUESTED)
        self.flow_texts.append(message)

        validation, stated, text = self._run_llm(message, history or [])
        if validation is None:          # FR-10/42a/43: the agent asked a question instead
            self._set(RefundState.AWAITING_AMOUNT)
            return AgentReply(text)
        return self._decide(validation, stated)

    # ---- the tool-using part (LLM) -------------------------------------------
    def _run_llm(self, message: str, history: list[dict]):
        found: dict = {}

        @tool
        def get_user_account() -> dict:
            """Get the signed-in customer's account: name, plan and recent recharges with
            amount, status, age in days and refund status. Takes no arguments."""
            log.info("[Agent] get_user_account")
            return self.tools.get_user_account(self.user_id)

        @tool
        def validate_refund(amount: float) -> dict:
            """Check whether a refund of `amount` rupees is allowed. Returns eligible,
            reason, recharge_id and recharge_amount. Use the amount the customer stated."""
            stated_amounts = amounts_in(" ".join(self.flow_texts))
            refundable = self.tools.refundable_recharges(self.user_id)
            if amount in stated_amounts:
                stated = True
            elif (not stated_amounts and len(refundable) == 1
                  and amount == refundable[0]["recharge_amount"]):
                stated = False               # FR-42: the single eligible recharge, offered
            else:                            # FR-44: never invent an amount
                log.info("[Agent] validate_refund(amount=%s) refused: amount not stated", amount)
                return {"error": "The customer has not stated this amount. Do not guess; "
                                 "ask the customer which amount they want refunded."}
            log.info("[Agent] validate_refund(amount=%s)", amount)
            found["validation"] = self.tools.validate_refund(self.user_id, amount)
            found["stated"] = stated
            return found["validation"]

        tools = {t.name: t for t in (get_user_account, validate_refund)}  # FR-23a: only these two
        llm = get_llm().bind_tools(list(tools.values()))
        msgs = [SystemMessage(AGENT_PROMPT), *to_messages(history), HumanMessage(message)]
        for _ in range(4):
            ai = llm.invoke(msgs)
            msgs.append(ai)
            if not ai.tool_calls:
                return None, False, ai.content.strip()
            for call in ai.tool_calls:
                fn = tools.get(call["name"])
                result = fn.invoke(call["args"]) if fn else {"error": f"Unknown tool {call['name']}"}
                msgs.append(ToolMessage(json.dumps(result, ensure_ascii=False),
                                        tool_call_id=call["id"]))
            if "validation" in found:   # from here on, code decides
                return found["validation"], found["stated"], ""
        return None, False, "Which amount would you like refunded?"

    # ---- deterministic decisions ---------------------------------------------
    def _decide(self, v: dict, stated: bool) -> AgentReply:
        self._set(RefundState.REFUND_VALIDATED)
        if not v["eligible"]:
            return self._finish(RefundState.REFUND_REJECTED,
                                f"Sorry, I can't refund this. {v['reason']}")
        amount = v["requested_amount"]
        if amount <= REFUND_APPROVAL_LIMIT:                       # FR-36, FR-36a
            self.pending = v
            log.info("[Agent] awaiting_user_confirmation")
            self._set(RefundState.AWAITING_CONFIRMATION)
            return AgentReply(self._confirmation_text(v), awaiting_confirmation=True)
        if not stated:                                            # FR-42 for an amount > ₹499
            self.offered_amount = amount
            self._set(RefundState.AWAITING_AMOUNT)
            return AgentReply(
                f"I can see one recent recharge that's eligible: {rupees(amount)}. "
                f"Refunds above {rupees(REFUND_APPROVAL_LIMIT)} are reviewed by our Support "
                f"Team. Would you like me to submit a refund request for {rupees(amount)}?"
            )
        self.tools.submit_to_support(self.user_id, amount)        # FR-37/38, no process_refund
        return self._finish(                                       # FR-40/40a
            RefundState.REFUND_SUBMITTED_FOR_REVIEW,
            f"Your refund request for {rupees(amount)} has been submitted to our Support Team. "
            "They will review the request and process it or take the necessary action.",
        )

    def _confirmation_text(self, v: dict) -> str:
        return (f"**Refund eligible: {rupees(v['requested_amount'])}** "
                f"(your {rupees(v['recharge_amount'])} recharge)\n\n"
                "Do you want to proceed with this refund? Reply **Yes, proceed** or **Cancel**.")

    def _handle_confirmation(self, message: str) -> AgentReply:
        answer = parse_confirmation(message)
        if answer == "ambiguous":                                 # FR-36e
            log.info("[User] ambiguous confirmation")
            return AgentReply("I need a clear answer before I make any refund.\n\n"
                              + self._confirmation_text(self.pending), awaiting_confirmation=True)
        if answer == "no":                                        # FR-36d
            log.info("[User] cancelled")
            return self._finish(RefundState.REFUND_CANCELLED,
                                "Okay, I've cancelled this refund. No refund has been made.")
        log.info("[User] confirmed")
        self._set(RefundState.REFUND_CONFIRMED)
        result = self.tools.process_refund(self.user_id, self.pending["requested_amount"])
        if not result["success"]:
            return self._finish(RefundState.REFUND_REJECTED,
                                f"Sorry, I couldn't complete this refund. {result['reason']}")
        return self._finish(
            RefundState.REFUND_PROCESSED,
            f"Your refund of {rupees(result['amount'])} has been processed. "
            f"Refund reference: **{result['refund_id']}**. "
            "(This is a demo, so no money was actually moved.)",
        )
