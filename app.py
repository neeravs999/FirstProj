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
  [data-testid="stChatMessage"] { padding:.6rem .4rem; }

  /* ---- sidebar ---- */
  [data-testid="stSidebar"] {
    background: linear-gradient(180deg, rgba(79,70,229,.14) 0%, rgba(6,182,212,.07) 45%,
                rgba(79,70,229,.04) 100%); }
  [data-testid="stSidebar"] [data-testid="stBaseButton-tertiary"] { justify-content:flex-start;
    text-align:left; padding:6px 8px; border-radius:10px; }
  [data-testid="stSidebar"] [data-testid="stBaseButton-tertiary"] > div,
  [data-testid="stSidebar"] [data-testid="stBaseButton-tertiary"] > div > span {
    justify-content:flex-start !important; text-align:left; }
  [data-testid="stSidebar"] [data-testid="stBaseButton-tertiary"]:hover { background:rgba(79,70,229,.12); }
  [data-testid="stSidebar"] [data-testid="stExpander"] details {
    border-radius:14px; border:1px solid rgba(79,70,229,.25); background:rgba(127,127,127,.04); }
  .sb-brand { display:flex; align-items:center; gap:10px; margin:-8px 0 14px; }
  .sb-logo { width:38px; height:38px; border-radius:12px; display:grid; place-items:center;
             font-size:20px; background:linear-gradient(135deg,#4F46E5,#06B6D4);
             box-shadow:0 4px 14px rgba(79,70,229,.35); }
  .sb-brand b { font-size:1.05rem; display:block; line-height:1.2; }
  .sb-status { font-size:.78rem; opacity:.75; }
  .sb-dot { display:inline-block; width:7px; height:7px; border-radius:50%; background:#22C55E;
            margin-right:5px; box-shadow:0 0 0 3px rgba(34,197,94,.2); }
  .sb-label { font-size:.72rem; font-weight:700; letter-spacing:.08em; text-transform:uppercase;
              opacity:.6; margin:14px 0 6px; }
  .acct { border-radius:18px; padding:14px; color:#fff;
          background:linear-gradient(135deg,#4F46E5 0%,#7C3AED 60%,#06B6D4 130%);
          box-shadow:0 8px 24px rgba(79,70,229,.30); }
  .acct-head { display:flex; align-items:center; gap:10px; margin-bottom:12px; }
  .acct-av { width:40px; height:40px; border-radius:50%; display:grid; place-items:center;
             font-weight:700; font-size:1.1rem; background:rgba(255,255,255,.22);
             border:2px solid rgba(255,255,255,.45); }
  .acct-name { font-weight:700; font-size:1rem; line-height:1.2; }
  .acct-sub { font-size:.76rem; opacity:.85; }
  .acct-stats { display:flex; gap:8px; margin-bottom:10px; }
  .acct-stat { flex:1; background:rgba(255,255,255,.14); border-radius:12px; padding:6px 8px; }
  .acct-stat b { display:block; font-size:1.05rem; }
  .acct-stat span { font-size:.68rem; opacity:.85; text-transform:uppercase; letter-spacing:.05em; }
  .rc { display:flex; align-items:center; justify-content:space-between; gap:8px;
        background:rgba(255,255,255,.12); border-radius:12px; padding:8px 10px; margin-top:6px; }
  .rc-amt { font-weight:700; }
  .rc-meta { font-size:.72rem; opacity:.8; }
  .pill { font-size:.7rem; font-weight:700; padding:3px 9px; border-radius:999px; white-space:nowrap; }
  .pill.ok   { background:#DCFCE7; color:#166534; }
  .pill.done { background:rgba(255,255,255,.25); color:#fff; }
  .pill.no   { background:#FFEDD5; color:#9A3412; }
  .acct-foot { font-size:.7rem; opacity:.75; margin-top:10px; }
  .help { display:flex; gap:10px; align-items:center; border-radius:14px; padding:10px 12px;
          border:1px dashed rgba(127,127,127,.4); font-size:.82rem; margin-top:4px; }
  .help-ic { font-size:1.3rem; }
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
    a = agent.tools.get_user_account(agent.user_id)
    recharges = a["recharges"]
    refundable = sum(is_refundable(r) for r in recharges)
    rows = ""
    for r in sorted(recharges, key=lambda r: r["recharge_age_days"]):
        if r["refund_status"] == "refunded":
            pill = '<span class="pill done">✓ Refunded</span>'
        elif is_refundable(r):
            pill = '<span class="pill ok">● Refundable</span>'
        else:
            pill = '<span class="pill no">Not eligible</span>'
        days = r["recharge_age_days"]
        rows += (f'<div class="rc"><div><div class="rc-amt">{rupees(r["recharge_amount"])}</div>'
                 f'<div class="rc-meta">{days} day{"s" if days != 1 else ""} ago · '
                 f'{r["recharge_status"]}</div></div>{pill}</div>')
    st.html(f"""
    <div class="acct">
      <div class="acct-head">
        <div class="acct-av">{a['name'][0]}</div>
        <div><div class="acct-name">{a['name']}</div>
             <div class="acct-sub">{a['plan']} plan · {rupees(a['plan_amount'])}/month</div></div>
      </div>
      <div class="acct-stats">
        <div class="acct-stat"><b>{len(recharges)}</b><span>Recharges</span></div>
        <div class="acct-stat"><b>{refundable}</b><span>Refundable</span></div>
      </div>
      {rows}
      <div class="acct-foot">🔒 Signed in · demo account, refunds are simulated</div>
    </div>""")


def clear() -> None:                                   # FR-04 / agent_PRD FR-48
    st.session_state.messages = []
    agent.reset()                                      # also drops any pending refund


with st.sidebar:
    st.html("""
    <div class="sb-brand">
      <div class="sb-logo">📶</div>
      <div><b>Telecom Care</b>
           <span class="sb-status"><span class="sb-dot"></span>Assistant online · 24×7</span></div>
    </div>""")
    st.html('<div class="sb-label">Your account</div>')
    render_account()

    st.html('<div class="sb-label">Quick start</div>')
    with st.expander("Common questions", icon=":material/lightbulb:"):
        for q in SAMPLE_QUESTIONS:
            st.button(q, width="stretch", on_click=ask, args=(q,), type="tertiary",
                      icon=":material/chat_bubble:")
    with st.expander("Refund demos", icon=":material/currency_rupee:"):
        for q in SAMPLE_REFUNDS:
            st.button(q, width="stretch", on_click=ask, args=(q,), type="tertiary",
                      icon=":material/payments:")

    st.html('<div class="sb-label">Conversation</div>')
    st.button("Clear conversation", icon=":material/restart_alt:", width="stretch",
              on_click=clear, type="primary")
    st.html("""
    <div class="help"><span class="help-ic">☎️</span>
      <div><b>Need a person?</b><br>Call <b>611</b> or use the MyTelecom app.</div></div>""")
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
