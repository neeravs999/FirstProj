"""Router shared by app.py and main.py: intent detection -> RAG or Refund Agent."""
import logging
from collections.abc import Iterator
from dataclasses import dataclass, field

from langchain_core.documents import Document

from chain import answer_stream
from config import setup_logging
from intent import REFUND_REQUEST, REQUIREMENT_INQUIRY, classify_intent
from refund_agent import RefundAgent

setup_logging()
log = logging.getLogger("telecom_chatbot.intent")


@dataclass
class Reply:
    intent: str
    docs: list[Document] = field(default_factory=list)
    stream: Iterator[str] | None = None   # RAG answers stream
    text: str | None = None               # Refund Agent answers arrive whole
    awaiting_confirmation: bool = False


def respond(question: str, history: list[dict], agent: RefundAgent) -> Reply:
    if agent.awaiting_confirmation:
        # A pending refund owns the next message, so "Yes, proceed" can't be misrouted.
        intent = REFUND_REQUEST
        log.info("[Intent] refund_request (pending confirmation)")
    else:
        intent = classify_intent(question, history)

    if intent == REFUND_REQUEST:                     # FR-03
        reply = agent.handle(question, history)
        return Reply(intent, text=reply.text, awaiting_confirmation=reply.awaiting_confirmation)

    if agent.in_progress:                            # customer moved on; drop the half-finished refund
        agent.reset()
    docs, stream = answer_stream(question, history)  # FR-02: unchanged RAG pipeline
    return Reply(REQUIREMENT_INQUIRY, docs=docs, stream=stream)
