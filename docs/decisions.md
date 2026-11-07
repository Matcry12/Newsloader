# Newsloader — design decisions

Daily personalized tech digest → Telegram. Also a CV project: deployment, eval in CI, tracing, cost control.

## D1. Product
Personalized digest: fetch → rank against interest profile → send top 5–7 (2-line summary, "why it matters", link).
v1 source: arXiv only. Sources pluggable (HN, GitHub trending, blogs later).

## D2. Ranking pipeline
- **Stage 0 ($0):** arXiv API (`export.arxiv.org/api/query`, 1 req/3s), RSS as fallback (can be empty; none on weekends).
  Fetch scope = union of all users' categories. Code keeps only universal rules: dedupe by ID (cross-lists), `v1` only.
  No keyword/content rules: keyword search misses relevant docs (Blair & Maron 1985, CACM: ~20% recall; Furnas et al. 1987,
  CACM: two people pick the same term <20% of the time). Relevance goes to embeddings, as in two-stage recommenders
  (Covington et al. 2016, RecSys) and paper recommenders (Scholar Inbox, arXiv:2504.08385; arxiv-sanity-lite). Recall cost measured by D10.
- **Embed once, score per user:** each paper is embedded once and shared; per-user scoring is a cheap cosine.
- **Stage 1 (embeddings):** embed title+abstract, cache by ID. Score = max cosine over interest vectors, minus 👎 penalty. Keep the top 5.
- **Summaries:** DeepSeek writes a summary and "why it matters" for the top 5 only, output capped.
- **No rerank in the baseline.** A rerank model only returns scores, so an LLM is needed for the text anyway. Add one (Vertex `semantic-ranker` or DeepSeek) only if the eval shows it clearly beats no rerank.
- Measure during development: precision@5 on labeled 👍/👎.

## D3. Interest profile (per user, multi-user)
Each user owns a profile: categories, topics, optional blocked words. Nothing user-specific in code.
v1 storage: `config/users/<name>.yaml` (later a DB table, editable via Telegram). Per topic: a name, a pseudo-abstract in paper vocabulary (HyDE-style; LLM drafts it, user edits), and optional seed arXiv IDs.
One-time LLM expansion into 5–10 technique phrasings per topic. Telegram 👍/👎 adds to it over time.

Example profile (first user) — topics:
1. LLM agents & tool use (function calling, MCP, coding agents)
2. RAG & retrieval techniques
3. Model releases / tech reports (DeepSeek, Qwen, Llama, Claude…)
4. LLM engineering in production (eval, serving, inference cost)
5. OCR / document understanding

Categories: cs.CL, cs.AI, cs.LG, cs.IR, cs.CV (no keyword gate; embeddings handle cs.CV volume).

## D4. Deployment
Google Cloud Run (one container: Telegram webhook + `/run-digest` endpoint) and Cloud Scheduler for the daily cron. Both fit the free tier.
GitHub Actions does CI only: tests, eval gate, build, deploy. Budget alert set on the billing account.

## D5. Storage
Neon Postgres (free tier) + pgvector holds papers, embeddings, sent log, feedback and run/cost logs.
Vector access goes through a `VectorStore` interface, so Qdrant Cloud (free 1GB) can be swapped in later if scale or features need it.
Not Qdrant self-hosted on Cloud Run: the container is stateless and its disk is wiped.

## D6. Embeddings
Gemini API `gemini-embedding-001`, reduced to 768 dims. Free tier: $0, but Google may use the data (fine: arXiv text and topic texts are public).
Limits seen in AI Studio (2026-11): 100 requests/min, 30k tokens/min, 1,000 requests/day. Usage suggests each text counts as one request, even in a batch.
So: 80 texts per request, wait and retry on 429, at most 900 new papers a run (extra papers are skipped with a warning). Measured volume for the 5 categories: 398–591 papers a day (2026-11-01 to 11-05), under the cap.
If it ever goes paid: $0.15/1M, or $0.075/1M with the batch API (~$1.50 or ~$0.75 a month at ~10M tokens).
Chosen over Voyage (user preference, stays in the Google ecosystem). A local model (`fastembed`) is the fallback if limits or quality disappoint.

## D7. LLM
DeepSeek `deepseek-v4-flash` (existing API key) for the summaries. JSON output; static prefix first so DeepSeek's context cache gets hits.
Sits behind an `LLMClient` interface, so another model (e.g. Haiku) can be compared on the eval set later. Not v4-pro: worse and pricier.

## D8. Stack
Python 3.12, uv, FastAPI, httpx (calling the Telegram Bot API directly, no framework), psycopg + pgvector, pytest, ruff, mypy.

## D9. Observability
Langfuse Cloud (free tier) traces each pipeline stage and LLM call, with tokens, cost and latency per digest, and stores eval scores next to them.
Structured JSON logs go to Cloud Logging. OpenTelemetry can be added later (Langfuse accepts OTel).

## D10. Eval in CI
- Golden set: one week of arXiv (~1,500 papers) frozen as a fixture. DeepSeek pre-labels it; the user checks ~100 labels in a `label` CLI (y/n). Telegram 👍/👎 add more labels over time.
- CI runs the pipeline on the fixture on every PR. It fails if precision@5 drops more than 5 points below the baseline stored in the repo, or if cost per run goes over budget.
- Metrics are posted as a PR comment.

## D11. Cost control (limits are config values, tune them later)
1. Per-run cap: estimate tokens before calling the LLM. If over the cap (default 50k), send titles and links without summaries, marked ⚠️.
2. Monthly budget (default $1): every call logs its cost to the DB. Over budget → LLM stages pause and the user gets a Telegram alert.
3. Backstop: a GCP budget alert at $5 and a spending limit on the DeepSeek account.
Every digest has a footer: `💰 run $X · month $Y/$1`.

## D12. Delivery (defaults, change later)
08:00 Asia/Ho_Chi_Minh, Mon–Fri (matches arXiv's announcement schedule). Top 5 papers; on a slow day (<3 above threshold) send only those, plus a "quiet day" note.
Multi-user: each chat ID maps to a profile (D3); allowlist of chat IDs for now. Commands: `/today`, `/topics`.

## D13. Secrets
Local: `.env` (gitignored). Cloud: GCP Secret Manager, mounted into Cloud Run as env vars. Secrets: Telegram token, DeepSeek, Gemini, Neon, Langfuse keys.

## D14. Build order (vertical slices, each one runnable)
1. Build each stage alone on `tests/fixtures/arxiv_sample.json`, review, then connect: stage 0 ✅ → fetch → keyword rank → Telegram (local).
2. Gemini embeddings: stage 1 with `config/users/<name>.yaml`, then Neon + pgvector.
3. DeepSeek summaries for the top 5.
4. Langfuse tracing + cost log + digest footer.
5. Docker → Cloud Run + Cloud Scheduler + GitHub Actions deploy.
6. Telegram webhook: 👍/👎, `/today`, `/topics`.
7. Golden set + `label` CLI → eval gate in CI.
8. Cost guardrails (per-run cap, monthly budget, fallback).
