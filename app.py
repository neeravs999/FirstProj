"""Streamlit chat UI. Run with:  streamlit run app.py"""
import os

import streamlit as st

from assistant import respond
from chain import friendly_error, source_label
from intent import REFUND_REQUEST
from interaction_log import log_answer, log_feedback
from refund_agent import RefundAgent
from refund_tools import is_refundable, rupees
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
AVATARS = {"user": ":material/person:", "assistant": ":material/support_agent:"}

st.html("""
<style>
  .hero { display:flex; align-items:center; gap:14px; margin:4px 0 2px; }
  .hero-icon { width:48px; height:48px; border-radius:14px; display:grid; place-items:center;
               font-size:26px; background:linear-gradient(135deg,#4F46E5,#06B6D4); }
  .hero h1 { font-size:1.75rem; line-height:1.2; margin:0; padding:0; }
  .hero p  { margin:2px 0 0; opacity:.7; font-size:.95rem; }
  .welcome { opacity:.75; margin:8px 0 4px; }
  [data-testid="stSidebar"] .stButton button { justify-content:flex-start; text-align:left; }
  [data-testid="stChatMessage"] { padding:.6rem .4rem; }
</style>
""")

if "messages" not in st.session_state:  # FR-03 / agent_PRD FR-45
    st.session_state.messages = []
if "agent" not in st.session_state:     # one Refund Agent (and demo account copy) per session
    st.session_state.agent = RefundAgent()
agent: RefundAgent = st.session_state.agent


def ask(question: str) -> None:
    st.session_state.pending_question = question


def on_feedback(interaction_id: str, key: str) -> None:  # FR-05a
    value = st.session_state.get(key)
    rating = {1: "up", 0: "down"}.get(value, "cleared")  # None = user un-selected the thumb
    log_feedback(interaction_id, rating)


def render_sources(sources: list[dict]) -> None:  # FR-13a
    with st.expander(f"Sources ({len(sources)})", icon=":material/library_books:"):
        for s in sources:
            st.markdown(f"**{s['label']}**")
            st.caption(s["excerpt"])


def render_assistant(msg: dict, is_last: bool) -> None:
    pending = is_last and msg.get("confirm") and agent.awaiting_confirmation
    if pending:                                           # agent_PRD section 11
        with st.container(border=True):
            st.markdown(msg["content"])
            c1, c2, _ = st.columns([1.3, 1, 1.5])
            c1.button("Confirm Refund", type="primary", icon=":material/check_circle:",
                      key=f"yes_{msg['id']}", on_click=ask, args=("Yes, proceed",),
                      width="stretch")
            c2.button("Cancel", icon=":material/close:", key=f"no_{msg['id']}",
                      on_click=ask, args=("Cancel",), width="stretch")
    else:
        st.markdown(msg["content"])
    if msg.get("sources"):
        render_sources(msg["sources"])
    meta, fb = st.columns([4, 1])
    if msg.get("intent") == REFUND_REQUEST:
        meta.caption(":material/currency_rupee: Refund assistant")
    elif msg.get("intent"):
        meta.caption(":material/menu_book: Answered from the knowledge base")
    key = f"fb_{msg['id']}"
    with fb:
        st.feedback("thumbs", key=key, on_change=on_feedback, args=(msg["id"], key))


def render_account() -> None:
    account = agent.tools.get_user_account(agent.user_id)
    with st.container(border=True):
        st.markdown(f"**:material/account_circle: {account['name']}** · {account['plan']} plan")
        for r in account["recharges"]:
            left, right = st.columns([1, 1.3], vertical_alignment="center")
            left.markdown(f"**{rupees(r['recharge_amount'])}**  \n"
                          f":small[{r['recharge_age_days']} day(s) ago]")
            with right:
                if r["refund_status"] == "refunded":
                    st.badge("Refunded", icon=":material/done_all:", color="gray")
                elif is_refundable(r):
                    st.badge("Refundable", icon=":material/check:", color="green")
                else:
                    st.badge("Not refundable", icon=":material/block:", color="orange")
        st.caption("Demo account · refunds are simulated")


with st.sidebar:
    st.subheader("Your account")
    render_account()
    with st.expander("Sample questions", icon=":material/help:"):
        for q in SAMPLE_QUESTIONS:
            st.button(q, width="stretch", on_click=ask, args=(q,), type="tertiary")
    with st.expander("Try a refund", icon=":material/currency_rupee:"):
        for q in SAMPLE_REFUNDS:
            st.button(q, width="stretch", on_click=ask, args=(q,), type="tertiary")
    st.divider()

    def clear() -> None:                               # FR-04 / agent_PRD FR-48
        st.session_state.messages = []
        agent.reset()                                  # also drops any pending refund

    st.button("Clear conversation", icon=":material/restart_alt:", width="stretch",
              on_click=clear)
    st.caption("Answers come only from the FAQ, resolved tickets and the telecom guide.")

st.html("""
<div class="hero">
  <div class="hero-icon">📶</div>
  <div><h1>Telecom Support Assistant</h1>
  <p>Data · Billing · SIM &amp; eSIM · Roaming · Calls · Refunds</p></div>
</div>
""")

if not os.getenv("GROQ_API_KEY"):
    st.error("GROQ_API_KEY is not set. Copy .env.example to .env, add your key and restart.")
    st.stop()

if not st.session_state.messages and "pending_question" not in st.session_state:
    st.html('<p class="welcome">Hi! Ask me anything about your mobile service, or ask '
            'for a refund of a recent recharge. Try one of these:</p>')
    left, right = st.columns(2)
    with left.container(border=True):
        st.markdown("**:material/menu_book: Get help**")
        for q in SAMPLE_QUESTIONS[:3]:
            st.button(q, key=f"w_{q}", on_click=ask, args=(q,), type="tertiary")
    with right.container(border=True):
        st.markdown("**:material/currency_rupee: Request a refund**")
        for q in SAMPLE_REFUNDS[:3]:
            st.button(q, key=f"w_{q}", on_click=ask, args=(q,), type="tertiary")

for i, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"], avatar=AVATARS[msg["role"]]):
        if msg["role"] == "assistant":
            render_assistant(msg, is_last=i == len(st.session_state.messages) - 1)
        else:
            st.markdown(msg["content"])

question = (st.chat_input("Ask a question or request a refund…")
            or st.session_state.pop("pending_question", None))

if question:
    history = [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages]
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user", avatar=AVATARS["user"]):
        st.markdown(question)

    with st.chat_message("assistant", avatar=AVATARS["assistant"]):
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
            st.error(friendly_error(e), icon=":material/error:")  # details go to the log only
            st.session_state.messages.pop()  # drop the unanswered question so a retry is clean
            st.stop()

    sources = [{"label": source_label(d), "excerpt": d.page_content[:300]} for d in reply.docs]
    interaction_id = log_answer(question, answer, [d.metadata["doc_id"] for d in reply.docs],
                                "web", reply.intent)
    st.session_state.messages.append(
        {"role": "assistant", "content": answer, "sources": sources, "id": interaction_id,
         "confirm": reply.awaiting_confirmation, "intent": reply.intent}
    )
    st.rerun()  # redraw so the new answer gets its Sources, buttons and feedback controls
