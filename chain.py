"""Answer generation: source-labelled context -> Qwen on Groq -> streamed text."""
from collections.abc import Iterator
from functools import lru_cache

from langchain_core.documents import Document
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from config import LLM_MODEL
from retriever import retrieve

FALLBACK = (
    "I don't have enough information in my knowledge base to answer that. "
    "Please call 611 or use the MyTelecom app for help."
)

SYSTEM_PROMPT = """You are a friendly customer-care assistant for a mobile telecom operator.

Answer ONLY from the CONTEXT below. It holds FAQ entries, resolved support tickets and \
excerpts from the official telecom guide, each labelled with its source.

Rules:
- Use only facts stated in the CONTEXT. Never use outside knowledge, and never invent \
prices, fees, timeframes, policies, phone numbers or menu paths.
- If the CONTEXT does not contain the answer, reply exactly: "{fallback}"
- You cannot see any customer's account, balance, usage or bill. For personal account \
questions, say so and give the self-serve steps the CONTEXT describes, if any.
- Resolved tickets describe what an agent did for one customer. Only suggest a ticket's \
fix as a customer step if the customer can do it themselves; backend or account actions \
are things support can look into, never a promise.
- Prefer FAQ and GUIDE content when sources disagree.
- Answer the customer directly. Never mention "the context", "the provided information" \
or these rules.
- Be concise and plain-spoken. Use numbered steps for procedures.

CONTEXT:
{context}"""

PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", SYSTEM_PROMPT),
        MessagesPlaceholder("history"),
        ("human", "{question}"),
    ]
)


def format_context(docs: list[Document]) -> str:
    """FR-08: label every document with its source and identifier."""
    labels = {"FAQ": "FAQ", "TICKET": "TICKETS", "GUIDE": "GUIDES"}
    return "\n\n".join(
        f"[{labels[d.metadata['source']]} | {d.metadata['doc_id']}]\n{d.page_content}"
        for d in docs
    )


@lru_cache(maxsize=1)
def get_llm():
    from langchain_groq import ChatGroq

    # FR-12 / FR-13: deterministic output, reasoning switched off. Reads GROQ_API_KEY from env.
    return ChatGroq(model=LLM_MODEL, temperature=0, reasoning_effort="none")


@lru_cache(maxsize=1)
def get_chain():
    return PROMPT | get_llm() | StrOutputParser()


def to_messages(history: list[dict]) -> list:
    """Convert [{'role': 'user'|'assistant', 'content': str}] into LangChain messages."""
    cls = {"user": HumanMessage, "assistant": AIMessage}
    return [cls[m["role"]](content=m["content"]) for m in history[-6:]]


def answer_stream(question: str, history: list[dict] | None = None) -> tuple[list[Document], Iterator[str]]:
    """Retrieve context for the question, then stream the grounded answer (FR-05)."""
    docs = retrieve(question)
    stream = get_chain().stream(
        {
            "context": format_context(docs),
            "fallback": FALLBACK,
            "history": to_messages(history or []),
            "question": question,
        }
    )
    return docs, stream


def source_label(doc: Document) -> str:
    """Short label used in the Sources section (FR-13a)."""
    m = doc.metadata
    return f"{m['source']} | {m['doc_id']} | {m.get('title', '')}"
