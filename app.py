"""Streamlit chat UI. Run with:  streamlit run app.py"""
import os

import streamlit as st

from chain import answer_stream, source_label
from interaction_log import log_answer, log_feedback
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

if "messages" not in st.session_state:  # FR-03
    st.session_state.messages = []


def on_feedback(interaction_id: str, key: str) -> None:  # FR-05a
    value = st.session_state.get(key)
    rating = {1: "up", 0: "down"}.get(value, "cleared")  # None = user un-selected the thumb
    log_feedback(interaction_id, rating)


def render_sources(sources: list[dict]) -> None:  # FR-13a
    with st.expander(f"Sources ({len(sources)})"):
        for s in sources:
            st.markdown(f"**{s['label']}**")
            st.caption(s["excerpt"])


def render_assistant_extras(msg: dict) -> None:
    render_sources(msg["sources"])
    key = f"fb_{msg['id']}"
    st.feedback("thumbs", key=key, on_change=on_feedback, args=(msg["id"], key))


with st.sidebar:
    st.header("Sample questions")
    for q in SAMPLE_QUESTIONS:
        if st.button(q, width="stretch"):
            st.session_state.pending_question = q
    st.divider()
    if st.button("Clear conversation", type="primary", width="stretch"):  # FR-04
        st.session_state.messages = []
        st.rerun()
    st.caption("Answers come only from the FAQ, resolved tickets and the telecom guide. "
               "This assistant can't see your account.")

st.title("📶 Telecom Support Assistant")
st.caption("Ask about data, billing, SIM/eSIM, roaming, calls or the MyTelecom app.")

if not os.getenv("GROQ_API_KEY"):
    st.error("GROQ_API_KEY is not set. Copy .env.example to .env, add your key and restart.")
    st.stop()

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant":
            render_assistant_extras(msg)

question = st.chat_input("Type your question…") or st.session_state.pop("pending_question", None)

if question:
    history = [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages]
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        try:
            docs, stream = answer_stream(question, history)
            answer = st.write_stream(stream)  # FR-05: token-by-token
        except StoreNotBuiltError as e:
            st.error(str(e))
            st.stop()
        except Exception as e:  # network / auth / rate-limit errors from Groq
            st.error(f"Sorry, something went wrong reaching the language model: {e}")
            st.stop()

    sources = [{"label": source_label(d), "excerpt": d.page_content[:300]} for d in docs]
    interaction_id = log_answer(question, answer, [d.metadata["doc_id"] for d in docs], "web")
    st.session_state.messages.append(
        {"role": "assistant", "content": answer, "sources": sources, "id": interaction_id}
    )
    st.rerun()  # redraw so the new answer gets its Sources and feedback controls
