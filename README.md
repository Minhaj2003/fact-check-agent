# Fact-Check Agent

A web app that automates marketing-claim verification. Upload a PDF, and the agent:

1. **Extracts** specific factual claims (stats, dates, financial/technical figures) using an LLM
2. **Verifies** each claim against live web search
3. **Reports** each claim as **Verified**, **Inaccurate**, or **False** — with the correct fact when available

Built for the GEO Product Management Trainee technical assessment ("The Fact-Check Agent").

---

## Live App

👉 **[Add your deployed Streamlit Cloud link here]**

## Demo Video

👉 **[Add your 30-second screen recording link here]**

---

## How It Works

```
PDF Upload
    │
    ▼
Extract text (PyMuPDF)
    │
    ▼
Extract claims (Gemini 2.5 Flash, structured JSON output)
    │
    ▼
For each claim: search the live web (DuckDuckGo, no API key needed)
    │
    ▼
Classify claim vs. evidence (Gemini): Verified / Inaccurate / False
    │
    ▼
Report with correction + sources, downloadable as Markdown
```

## Tech Stack

| Layer | Tool | Why |
|---|---|---|
| Frontend | Streamlit | Fastest path to a deployed, testable UI |
| PDF parsing | PyMuPDF (`fitz`) | Reliable text extraction, no OCR needed for text-based PDFs |
| Claim extraction & verdicts | Google Gemini (`gemini-2.5-flash`) | Free tier, fast, strong structured-JSON output |
| Web verification | `ddgs` (DuckDuckGo Search) | Free, no API key, no signup friction |

## Project Structure

```
.
├── app.py              # Main Streamlit app
├── requirements.txt     # Pinned dependencies
└── README.md
```

---

## Run Locally

```bash
git clone <your-repo-url>
cd <repo-folder>
pip install -r requirements.txt
streamlit run app.py
```

On first run, paste your Gemini API key into the sidebar (get a free one at
[aistudio.google.com/apikey](https://aistudio.google.com/apikey) — no card required).

## Deploy on Streamlit Community Cloud

1. Push this repo to GitHub.
2. Go to [share.streamlit.io](https://share.streamlit.io) → **New app** → select the repo → set main file to `app.py`.
3. Under **App settings → Secrets**, add:
   ```toml
   GEMINI_API_KEY = "your-key-here"
   ```
4. Deploy. The app will be live at `https://<your-app-name>.streamlit.app`.

---

## Features

- Upload any text-based PDF (marketing decks, reports, one-pagers)
- Extracts up to 12 of the most significant checkable claims per run (tuned to stay within free-tier rate limits)
- Each claim is independently searched and verified live — not from the model's training data alone
- Color-coded verdicts with the corrected fact and reasoning
- Expandable source list per claim, so results are auditable, not a black box
- Downloadable Markdown report

## Known Limitations

- Scanned/image-only PDFs won't extract text (no OCR yet) — works best on text-based PDFs
- Free-tier rate limits (Gemini + DuckDuckGo) mean very large documents are capped at the top 12 claims
- Web search quality depends on how well-indexed the claim's topic is online
