"""
Fact-Check Agent
----------------
Upload a PDF -> extract factual claims -> verify each claim against live
web search -> flag as Verified / Inaccurate / False with the correct fact.

Run locally:
    streamlit run app.py

Deploy:
    Push to GitHub, deploy on Streamlit Community Cloud, and add
    GROQ_API_KEY under App settings -> Secrets.
"""

import json
import re
import time

import fitz  # PyMuPDF
import streamlit as st
from openai import OpenAI
from ddgs import DDGS

# --------------------------------------------------------------------------
# Page setup
# --------------------------------------------------------------------------
st.set_page_config(page_title="Fact-Check Agent", page_icon="🔍", layout="wide")

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
MODEL_NAME = "llama-3.3-70b-versatile"
MAX_CLAIMS = 12  # keep within free-tier rate limits for a smooth demo


# --------------------------------------------------------------------------
# API key handling
# --------------------------------------------------------------------------
def get_api_key() -> str | None:
    """Prefer a deployed secret; fall back to a sidebar input for local runs."""
    try:
        if "GROQ_API_KEY" in st.secrets:
            return st.secrets["GROQ_API_KEY"]
    except Exception:
        pass
    return st.session_state.get("api_key_input", "").strip() or None


def get_client(api_key: str) -> OpenAI:
    return OpenAI(api_key=api_key, base_url=GROQ_BASE_URL)


def call_json(client: OpenAI, prompt: str) -> dict:
    """Call the model and parse a JSON object from its response, defensively."""
    resp = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    raw = resp.choices[0].message.content.strip()
    raw = re.sub(r"^```(json)?|```$", "", raw, flags=re.MULTILINE).strip()
    return json.loads(raw)


# --------------------------------------------------------------------------
# Step 1: PDF text extraction
# --------------------------------------------------------------------------
def extract_pdf_text(file_bytes: bytes) -> str:
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    pages = [page.get_text() for page in doc]
    doc.close()
    return "\n".join(pages)


# --------------------------------------------------------------------------
# Step 2: Claim extraction (LLM)
# --------------------------------------------------------------------------
CLAIM_EXTRACTION_PROMPT = """You are a fact-checking assistant. Read the document text below and \
extract every specific, checkable factual claim: statistics, percentages, dates, financial figures, \
counts, technical specifications, or named comparisons (e.g. "fastest", "largest", "first").

Ignore vague marketing language with no checkable number or fact (e.g. "industry-leading", "world-class").

Return ONLY a JSON object, no other text, no markdown fences, in this exact shape:
{{"claims": [{{"claim": "<the exact claim, self-contained and readable out of context>"}}, ...]}}

Include at most {max_claims} of the most significant claims.

DOCUMENT TEXT:
\"\"\"
{doc_text}
\"\"\"
"""


def extract_claims(client: OpenAI, doc_text: str, max_claims: int = MAX_CLAIMS) -> list[dict]:
    doc_text = doc_text[:15000]  # keep prompt within a safe size
    prompt = CLAIM_EXTRACTION_PROMPT.format(max_claims=max_claims, doc_text=doc_text)
    try:
        data = call_json(client, prompt)
        claims = data.get("claims", [])
    except (json.JSONDecodeError, KeyError, AttributeError):
        claims = []
    return claims[:max_claims]


# --------------------------------------------------------------------------
# Step 3: Live web search (free, no API key)
# --------------------------------------------------------------------------
def search_web(query: str, max_results: int = 5) -> list[dict]:
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        return [{"title": r.get("title", ""), "snippet": r.get("body", ""), "url": r.get("href", "")} for r in results]
    except Exception as e:
        return [{"title": "", "snippet": f"(search error: {e})", "url": ""}]


# --------------------------------------------------------------------------
# Step 4: Verdict (LLM, grounded on search evidence)
# --------------------------------------------------------------------------
VERIFICATION_PROMPT = """You are a fact-checking assistant. Decide whether the CLAIM below is supported \
by the EVIDENCE (live web search snippets). Evidence may be partial or noisy — use your judgement.

Classify as exactly one of:
- "Verified": evidence confirms the claim is accurate (or very close to current known figures)
- "Inaccurate": the claim is outdated, partially wrong, or doesn't match current evidence, but is in the right ballpark
- "False": evidence directly contradicts the claim, or no credible evidence supports it at all

Return ONLY a JSON object, no markdown fences:
{{"status": "Verified" | "Inaccurate" | "False", "correct_fact": "<the correct figure/fact if status is not Verified, else empty string>", "reasoning": "<one short sentence>"}}

CLAIM: {claim}

EVIDENCE:
{evidence}
"""


def verify_claim(client: OpenAI, claim: str, evidence: list[dict]) -> dict:
    evidence_text = "\n".join(
        f"- {e['title']}: {e['snippet']} ({e['url']})" for e in evidence
    ) or "No search results found."
    prompt = VERIFICATION_PROMPT.format(claim=claim, evidence=evidence_text)
    try:
        return call_json(client, prompt)
    except (json.JSONDecodeError, AttributeError):
        return {"status": "Inaccurate", "correct_fact": "", "reasoning": "Could not parse model output."}


# --------------------------------------------------------------------------
# UI
# --------------------------------------------------------------------------
STATUS_STYLE = {
    "Verified": ("✅", "#0F7B4D", "#E7F6EE"),
    "Inaccurate": ("⚠️", "#B07D1E", "#FDF3E0"),
    "False": ("❌", "#B0413E", "#FCEAEA"),
}

st.title("🔍 Fact-Check Agent")
st.caption("Upload a PDF. The agent extracts factual claims, checks them against live web search, and flags inaccuracies — a Truth Layer for marketing content.")

with st.sidebar:
    st.header("Setup")
    api_key = None
    try:
        has_secret = "GROQ_API_KEY" in st.secrets
    except Exception:
        has_secret = False

    if has_secret:
        st.success("Groq API key loaded from app secrets.")
    else:
        st.session_state["api_key_input"] = st.text_input(
            "Groq API key", type="password", help="Get one free at https://console.groq.com/keys"
        )
    st.markdown("---")
    st.caption("Free web search via DuckDuckGo — no extra API key needed.")
    st.caption(f"Model: `{MODEL_NAME}` (via Groq) · Max claims per run: {MAX_CLAIMS}")

uploaded = st.file_uploader("Upload a PDF to fact-check", type=["pdf"])
run = st.button("Run Fact-Check", type="primary", disabled=uploaded is None)

if run:
    api_key = get_api_key()
    if not api_key:
        st.error("Please add a Groq API key in the sidebar (or as a deployed secret) before running.")
        st.stop()

    client = get_client(api_key)

    with st.status("Reading PDF...", expanded=True) as status:
        text = extract_pdf_text(uploaded.read())
        if not text.strip():
            st.error("Could not extract any text from this PDF (it may be a scanned image).")
            st.stop()
        status.update(label=f"Extracted {len(text):,} characters. Extracting claims...")

        try:
            claims = extract_claims(client, text)
        except Exception as e:
            st.error(f"Claim extraction failed: {e}")
            st.stop()

        if not claims:
            status.update(label="No checkable claims found.", state="complete")
            st.warning("No specific, checkable factual claims were found in this document.")
            st.stop()

        status.update(label=f"Found {len(claims)} claims. Verifying against live web search...")

        results = []
        progress = st.progress(0.0)
        for i, c in enumerate(claims):
            claim_text = c.get("claim", "").strip()
            if not claim_text:
                continue
            evidence = search_web(claim_text)
            verdict = verify_claim(client, claim_text, evidence)
            results.append({
                "claim": claim_text,
                "status": verdict.get("status", "Inaccurate"),
                "correct_fact": verdict.get("correct_fact", ""),
                "reasoning": verdict.get("reasoning", ""),
                "sources": evidence,
            })
            progress.progress((i + 1) / len(claims))
            time.sleep(1)  # stay comfortably within free-tier rate limits

        status.update(label="Done.", state="complete")

    st.session_state["results"] = results

if "results" in st.session_state and st.session_state["results"]:
    results = st.session_state["results"]

    v = sum(1 for r in results if r["status"] == "Verified")
    i_ = sum(1 for r in results if r["status"] == "Inaccurate")
    f = sum(1 for r in results if r["status"] == "False")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Claims checked", len(results))
    c2.metric("✅ Verified", v)
    c3.metric("⚠️ Inaccurate", i_)
    c4.metric("❌ False", f)

    st.markdown("---")

    for r in results:
        emoji, color, bg = STATUS_STYLE.get(r["status"], ("⚠️", "#B07D1E", "#FDF3E0"))
        with st.container(border=True):
            cols = st.columns([0.08, 0.92])
            with cols[0]:
                st.markdown(
                    f"<div style='background:{bg};color:{color};border-radius:8px;padding:6px 0;"
                    f"text-align:center;font-weight:600;'>{emoji}<br>{r['status']}</div>",
                    unsafe_allow_html=True,
                )
            with cols[1]:
                st.markdown(f"**Claim:** {r['claim']}")
                if r["status"] != "Verified" and r["correct_fact"]:
                    st.markdown(f"**Correct fact:** {r['correct_fact']}")
                if r["reasoning"]:
                    st.caption(r["reasoning"])
                with st.expander("Sources checked"):
                    for s in r["sources"]:
                        if s["url"]:
                            st.markdown(f"- [{s['title']}]({s['url']}) — {s['snippet'][:160]}...")

    # Downloadable report
    report_lines = ["# Fact-Check Report\n"]
    for r in results:
        report_lines.append(f"## {r['status']}: {r['claim']}")
        if r["correct_fact"]:
            report_lines.append(f"**Correct fact:** {r['correct_fact']}")
        report_lines.append(f"{r['reasoning']}\n")
    st.download_button(
        "Download report (Markdown)",
        data="\n".join(report_lines),
        file_name="fact_check_report.md",
        mime="text/markdown",
    )
