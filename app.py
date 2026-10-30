"""Streamlit front end for AgriSenseAI.

Run from the repository root with: streamlit run app.py
The CLI entry point in main.py is intentionally left unchanged for the
AgentX judge contract: python main.py --json "your question".
"""

from __future__ import annotations

import os
from typing import Any

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# Reuse the existing ReAct agent and tool registry. Do not duplicate agent logic.
from main import run_agent  # noqa: E402
from tools import build_tools  # noqa: E402

st.set_page_config(
    page_title="AgriSenseAI | Smart Farming Assistant",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
      .block-container {padding-top: 1.6rem; padding-bottom: 2rem; max-width: 1180px;}
      .hero {padding: 1.25rem 1.4rem; border: 1px solid rgba(128,128,128,.25);
             border-radius: 18px; margin-bottom: 1.1rem;}
      .hero h1 {margin: 0 0 .25rem 0; font-size: 2rem;}
      .hero p {margin: 0; opacity: .78;}
      .small-muted {font-size: .85rem; opacity: .72;}
      div[data-testid="stChatMessage"] {border-radius: 14px;}
    </style>
    """,
    unsafe_allow_html=True,
)


def get_registered_tools() -> list[str]:
    try:
        return list(build_tools().keys())
    except Exception:
        return []


def build_agent_query(question: str, farm_location: str, history: list[dict[str, Any]]) -> str:
    """Pass a short recent chat context to the existing single-turn CLI agent."""
    recent = history[-6:]
    context_lines = []
    for item in recent:
        role = "Farmer" if item.get("role") == "user" else "AgriSenseAI"
        content = str(item.get("content", "")).strip().replace("\n", " ")
        if content:
            context_lines.append(f"{role}: {content[:700]}")

    sections = [
        "You are AgriSenseAI, an agriculture advisory agent. Use the registered tools when relevant. "
        "Base factual conclusions on tool observations; clearly say when data is unavailable. "
        "Do not invent sensor readings, forecast values, nutrient diagnoses, or fertilizer quantities.",
    ]
    if farm_location.strip():
        sections.append(f"Farmer's farm location (use for weather requests): {farm_location.strip()}")
    if context_lines:
        sections.append("Recent conversation for context:\n" + "\n".join(context_lines))
    sections.append("Current farmer question: " + question.strip())
    return "\n\n".join(sections)


# Session state: transcript and traces remain available while this browser session is open.
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

with st.sidebar:
    st.markdown("## 🌾 Farm workspace")
    st.caption("Your agriculture assistant")
    farm_location = st.text_input(
        "Farm location",
        value=st.session_state.get("farm_location", "Tiruchirappalli, Tamil Nadu, India"),
        help="Used as location context for weather and rainfall questions.",
    )
    st.session_state.farm_location = farm_location

    provider = os.getenv("AGENTX_PROVIDER", "not set").strip().upper()
    model = os.getenv("GROQ_MODEL" if provider == "GROQ" else "GEMINI_MODEL", "model configured in .env")
    st.markdown("---")
    st.markdown("**AI provider**")
    st.write(f"{provider} · `{model}`")
    st.markdown("**Connected tools**")
    registered_tools = get_registered_tools()
    if registered_tools:
        for tool_name in registered_tools:
            st.write(f"• `{tool_name}`")
    else:
        st.warning("Could not load the tool registry. Check tools/__init__.py.")

    st.markdown("---")
    if st.button("🗑️ Clear conversation", use_container_width=True):
        st.session_state.chat_history = []
        st.rerun()
    st.caption("API keys are read from your local .env file and are never displayed here.")

st.markdown(
    """
    <div class="hero">
      <h1>🌱 AgriSenseAI</h1>
      <p>Smart farming assistant · Crop stress · Soil & NPK · Irrigation · Weather · Fertilizer guidance</p>
    </div>
    """,
    unsafe_allow_html=True,
)

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("AI agent", "Ready", help="Uses the existing ReAct agent in main.py.")
with col2:
    st.metric("Registered tools", len(registered_tools))
with col3:
    st.metric("Interface", "Interactive chat")

st.markdown("### Ask your farming question")
st.caption("Choose an example or type your own question. Tool execution details appear below each answer.")

examples = [
    "Analyze the latest 7 planted days of tomato soil and NPK data.",
    "Analyze the latest 7 days of tomato irrigation sensor data.",
    "Check tomato crop stress at 38°C, 35% humidity and 18% soil moisture.",
    "Give the current weather and 7-day rainfall forecast for my farm.",
    "Explain fertilizer considerations for my tomato crop using the soil data.",
]
example_cols = st.columns(2)
for idx, example in enumerate(examples):
    with example_cols[idx % 2]:
        if st.button(example, key=f"example_{idx}", use_container_width=True):
            st.session_state.pending_question = example

# Render saved messages and their tool traces.
for idx, message in enumerate(st.session_state.chat_history):
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message.get("trace"):
            with st.expander("🔎 Agent execution trace"):
                st.json(message["trace"])

pending = st.session_state.pop("pending_question", None)
question = st.chat_input("Ask about your crop, soil, irrigation or weather...")
if pending and not question:
    question = pending

if question:
    st.session_state.chat_history.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("AgriSenseAI is analysing your question and selecting tools..."):
            try:
                agent_query = build_agent_query(
                    question,
                    st.session_state.farm_location,
                    st.session_state.chat_history[:-1],
                )
                answer, trace = run_agent(agent_query, dry_run=False, verbose=False)
                answer = str(answer)
                st.markdown(answer)
                if trace:
                    with st.expander("🔎 Agent execution trace", expanded=False):
                        st.json(trace)
                st.session_state.chat_history.append(
                    {"role": "assistant", "content": answer, "trace": trace}
                )
            except Exception as exc:
                error_text = f"The agent could not complete this request: {type(exc).__name__}: {exc}"
                st.error(error_text)
                st.session_state.chat_history.append(
                    {"role": "assistant", "content": error_text, "trace": []}
                )
