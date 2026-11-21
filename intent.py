"""Intent detection (agent_PRD 6.1): requirement_inquiry or refund_request."""
import logging
from typing import Literal

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from pydantic import BaseModel, Field

from chain import get_llm, to_messages

log = logging.getLogger("telecom_chatbot.intent")

REQUIREMENT_INQUIRY = "requirement_inquiry"
REFUND_REQUEST = "refund_request"


class Intent(BaseModel):  # FR-05: structured result
    intent: Literal["requirement_inquiry", "refund_request"] = Field(
        description="The intent of the customer's latest message."
    )


INTENT_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system",
         "Classify the customer's LATEST message to a mobile telecom support assistant.\n\n"
         "refund_request: the customer wants money back, or wants a recharge cancelled or "
         "reversed now. This includes replies that continue a refund conversation, such as "
         "stating the amount after the assistant asked which amount to refund.\n"
         "requirement_inquiry: any other question or request, including questions ABOUT "
         "refunds or cancellations (e.g. 'How do I cancel a recharge?', 'What is the refund "
         "policy?'), and follow-up questions to an earlier answer.\n\n"
         "Examples:\n"
         "'Why is my internet slow?' -> requirement_inquiry\n"
         "'I want a refund of ₹999.' -> refund_request\n"
         "'Please reverse my last recharge' -> refund_request\n"
         "'How do I cancel a recharge?' -> requirement_inquiry"),
        MessagesPlaceholder("history"),
        ("human", "{question}"),
    ]
)


def classify_intent(question: str, history: list[dict] | None = None) -> str:
    """FR-01/04: uses the same Groq model as the RAG chain."""
    chain = INTENT_PROMPT | get_llm().with_structured_output(Intent)
    result = chain.invoke({"question": question, "history": to_messages(history or [])})
    intent = result.intent if result else REQUIREMENT_INQUIRY
    log.info("[Intent] %s", intent)
    return intent
