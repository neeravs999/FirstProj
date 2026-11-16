# Telecom Support RAG Chatbot

A RAG chatbot built to `PRD.md`. It answers Tier-1 telecom questions only from
`data/faq.csv`, `data/tickets.db` and `data/telecom_guide.pdf`.

**Stack:** LangChain · ChromaDB · `all-MiniLM-L6-v2` (local embeddings) · `qwen/qwen3.8-27b` on Groq (PRD.md names qwen3.6-27b, which Groq has retired) · Streamlit

## Setup (Windows, PowerShell)

Requires Python 3.11–3.13. ChromaDB's `onnxruntime` dependency has no Python 3.15 wheels yet.

```powershell
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env      # then put your GROQ_API_KEY in .env
.venv\Scripts\python ingest_all.py   # builds chroma_store/ (first run downloads the ~90 MB model)
```

## Run

```powershell
.venv\Scripts\streamlit run app.py   # web UI
.venv\Scripts\python main.py         # CLI; type quit to exit
```

## Updating knowledge

Edit the files in `data/`, then re-run `ingest_all.py` (or just `ingest_faq.py`,
`ingest_tickets.py` or `ingest_guides.py`). Re-runs replace a collection; they never duplicate it.
To add a new source, write an `ingest_<name>.py` that calls `write_collection("<name>", ...)` and add
`"<name>"` to `COLLECTIONS` in `retriever.py`.

## Files

| File | Purpose |
| --- | --- |
| `config.py` | Paths, model names, top-k, chunk sizes, embeddings |
| `ingest_*.py` | Build the `faq`, `tickets` and `guides` collections |
| `retriever.py` | Top-3 per collection, queried in parallel (9 docs) |
| `chain.py` | Source-labelled prompt → Groq Qwen (temperature 0) → streamed answer |
| `app.py` | Streamlit UI: samples, clear, streaming, sources, 👍/👎 |
| `main.py` | CLI REPL |
| `interaction_log.py` | Answers and feedback → `logs/interactions.jsonl` |
