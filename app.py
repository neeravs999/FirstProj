"""Streamlit chat UI. Run with:  streamlit run app.py"""
import os

import streamlit as st

from assistant import respond
from chain import friendly_error, source_label
from interaction_log import log_answer, log_feedback
from refund_agent import RefundAgent
from refund_tools import rupees
from retriever import StoreNotBuiltError

st.set_page_config(page_title="Telecom Support Assistant", page_icon="📶")

SAMPLE_QUESTIONS = [  # FR-02
    "Why is my mobile internet so slow?",
    "Why is my bill higher than usual?",
    "How do I activate international roaming?",
    "My eSIM won't activate. What should I do?",
    "My calls keep dropping. What should I do?",
    "I can't log in to the MyTelecom app.",
]
SAMPLE_REFUNDS = [  # agent_PRD section 8
    "I want a refund of ₹499.",
    "I want a refund of ₹999.",
    "Give me a refund of ₹2,000.",
    "I want a refund.",
]

if "messages" not in st.session_state:  # FR-03 / agent_PRD FR-45
    st.session_state.messages = []
if "agent" not in st.session_state:     # one Refund Agent (and demo account copy) per session
    st.session_state.agent = RefundAgent()
agent: RefundAgent = st.session_state.agent


def on_feedback(interaction_id: str, key: str) -> None:  # FR-05a
    value = st.session_state.get(key)
    rating = {1: "up", 0: "down"}.get(value, "cleared")  # None = user un-selected the thumb
    log_feedback(interaction_id, rating)


def render_sources(sources: list[dict]) -> None:  # FR-13a
    with st.expander(f"Sources ({len(sources)})"):
        for s in sources:
            st.markdown(f"**{s['label']}**")
            st.caption(s["excerpt"])


def render_assistant_extras(msg: dict, is_last: bool) -> None:
    if msg.get("sources"):
        render_sources(msg["sources"])
    if is_last and msg.get("confirm") and agent.awaiting_confirmation:  # agent_PRD section 11
        c1, c2, _ = st.columns([1, 1, 2])
        if c1.button("Confirm Refund", type="primary", key=f"yes_{msg['id']}"):
            st.session_state.pending_question = "Yes, proceed"
        if c2.button("Cancel", key=f"no_{msg['id']}"):
            st.session_state.pending_question = "Cancel"
    key = f"fb_{msg['id']}"
    st.feedback("thumbs", key=key, on_change=on_feedback, args=(msg["id"], key))


with st.sidebar:
    st.header("Sample questions")
    for q in SAMPLE_QUESTIONS:
        if st.button(q, width="stretch"):
            st.session_state.pending_question = q
    st.subheader("Try a refund")
    for q in SAMPLE_REFUNDS:
        if st.button(q, width="stretch"):
            st.session_state.pending_question = q
    st.divider()
    if st.button("Clear conversation", type="primary", width="stretch"):  # FR-04 / FR-48
        st.session_state.messages = []
        agent.reset()  # also drops any pending refund
        st.rerun()
    account = agent.tools.get_user_account(agent.user_id)
    st.caption(f"Demo account: {account['name']} ({account['plan']} plan). Recharges: "
               + ", ".join(f"{rupees(r['recharge_amount'])} {r['recharge_age_days']}d ago "
                           f"({r['refund_status'].replace('_', ' ')})"
                           for r in account["recharges"]))
    st.caption("Answers come only from the FAQ, resolved tickets and the telecom guide. "
               "Refunds are simulated; no real money moves.")

st.title("📶 Telecom Support Assistant")
st.caption("Ask about data, billing, SIM/eSIM, roaming, calls or the MyTelecom app, "
           "or request a refund of a recent recharge.")

if not os.getenv("GROQ_API_KEY"):
    st.error("GROQ_API_KEY is not set. Copy .env.example to .env, add your key and restart.")
    st.stop()

for i, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant":
            render_assistant_extras(msg, is_last=i == len(st.session_state.messages) - 1)

question = st.chat_input("Type your question…") or st.session_state.pop("pending_question", None)

if question:
    history = [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages]
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        try:
            with st.spinner("Thinking…"):
                reply = respond(question, history, agent)
            if reply.stream is not None:
                answer = st.write_stream(reply.stream)  # FR-05: token-by-token
            else:
                answer = reply.text
                st.markdown(answer)
        except StoreNotBuiltError as e:
            st.error(str(e))
            st.stop()
        except Exception as e:  # network / auth / rate-limit errors from Groq
            st.error(friendly_error(e))  # details go to the server log only
            st.session_state.messages.pop()  # drop the unanswered question so a retry is clean
            st.stop()

    sources = [{"label": source_label(d), "excerpt": d.page_content[:300]} for d in reply.docs]
    interaction_id = log_answer(question, answer, [d.metadata["doc_id"] for d in reply.docs],
                                "web", reply.intent)
    st.session_state.messages.append(
        {"role": "assistant", "content": answer, "sources": sources, "id": interaction_id,
         "confirm": reply.awaiting_confirmation}
    )
    st.rerun()  # redraw so the new answer gets its Sources, buttons and feedback controls
