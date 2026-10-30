# Newsloader — design decisions

Daily personalized tech digest → Telegram. Also a CV project: deployment, eval in CI, tracing, cost control.

## D1. Product
Personalized digest: fetch → rank against interest profile → send top 5–7 (2-line summary, "why it matters", link).
v1 source: arXiv only. Sources pluggable (HN, GitHub trending, blogs later).

## D2. Ranking pipeline
- **Stage 0 ($0):** arXiv API (`export.arxiv.org/api/query`, 1 req/3s), RSS as fallback (can be empty; none on weekends).
  Keep: category in whitelist, `v1` only, dedupe by ID (cross-lists), keyword blocklist.
- **Stage 1 (embeddings):** embed title+abstract, cache by ID. Score = max cosine over interest vectors, minus 👎 penalty. Keep top K=30–50 (recall matters here).
- **Stage 2 (LLM rerank):** one batched call, short IDs + title + abstract cut to ~120 tok, JSON `{id, score, reason}`. Cheap model, cached static prefix.
- **Stage 3:** summaries for top 5–7 only, output capped.
- Measure during development: recall@K (stage 1) and precision@5 (stage 2) on labeled 👍/👎.

## D3. Interest profile
`interests.yaml`: per topic, a name, a pseudo-abstract in paper vocabulary (HyDE-style; LLM drafts it, user edits), and optional seed arXiv IDs.
One-time LLM expansion into 5–10 technique phrasings per topic. Telegram 👍/👎 adds to it over time.

Topics:
1. LLM agents & tool use (function calling, MCP, coding agents)
2. RAG & retrieval techniques
3. Model releases / tech reports (DeepSeek, Qwen, Llama, Claude…)
4. LLM engineering in production (eval, serving, inference cost)
5. OCR / document understanding

Categories: cs.CL, cs.AI, cs.LG, cs.IR, cs.CV (cs.CV only if it passes an OCR/document keyword gate, since it's high volume).

## D4. Deployment
Google Cloud Run (one container: Telegram webhook + `/run-digest` endpoint) and Cloud Scheduler for the daily cron. Both fit the free tier.
GitHub Actions does CI only: tests, eval gate, build, deploy. Budget alert set on the billing account.

## D5. Storage
Neon Postgres (free tier) + pgvector holds papers, embeddings, sent log, feedback and run/cost logs.
Vector access goes through a `VectorStore` interface, so Qdrant Cloud (free 1GB) can be swapped in later if scale or features need it.
Not Qdrant self-hosted on Cloud Run: the container is stateless and its disk is wiped.

## D6. Embeddings
Voyage `voyage-4-lite` via API: 200M free tokens, then $0.02/1M (~75k tok/day ≈ 2.25M/mo).
Sits behind an `Embedder` interface, with OpenAI `text-embedding-3-small` ($0.02/1M) as the fallback. Not local: it bloats the image and slows cold starts.
Researched 2026-10-29; dims and the training-use policy are not yet verified.

## D7. LLM
DeepSeek `deepseek-v4-flash` (existing API key) for both the rerank and the summaries. JSON output; static prefix first so DeepSeek's context cache gets hits.
Sits behind an `LLMClient` interface, so another model (e.g. Haiku) can be compared on the eval set later. Not v4-pro: worse and pricier.

## D8. Stack
Python 3.12, uv, FastAPI, httpx (calling the Telegram Bot API directly, no framework), psycopg + pgvector, pytest, ruff, mypy.

## D9. Observability
Langfuse Cloud (free tier) traces each pipeline stage and LLM call, with tokens, cost and latency per digest, and stores eval scores next to them.
Structured JSON logs go to Cloud Logging. OpenTelemetry can be added later (Langfuse accepts OTel).

## D10. Eval in CI
- Golden set: one week of arXiv (~1,500 papers) frozen as a fixture. DeepSeek pre-labels it; the user checks ~100 labels in a `label` CLI (y/n). Telegram 👍/👎 add more labels over time.
- CI runs the pipeline on the fixture on every PR. It fails if stage-1 recall@30 or stage-2 precision@5 drops more than 5 points below the baseline stored in the repo, or if cost per run goes over budget.
- Metrics are posted as a PR comment.

## D11. Cost control (limits are config values, tune them later)
1. Per-run cap: estimate tokens before calling the LLM. If over the cap (default 50k), reduce K or send an embeddings-only digest marked ⚠️.
2. Monthly budget (default $1): every call logs its cost to the DB. Over budget → LLM stages pause and the user gets a Telegram alert.
3. Backstop: a GCP budget alert at $5 and a spending limit on the DeepSeek account.
Every digest has a footer: `💰 run $X · month $Y/$1`.

## D12. Delivery (defaults, change later)
08:00 Asia/Ho_Chi_Minh, Mon–Fri (matches arXiv's announcement schedule). Top 5 papers; on a slow day (<3 above threshold) send only those, plus a "quiet day" note.
Private chat only (chat-ID allowlist). Commands: `/today`, `/topics`.

## D13. Secrets
Local: `.env` (gitignored). Cloud: GCP Secret Manager, mounted into Cloud Run as env vars. Secrets: Telegram token, DeepSeek, Voyage, Neon, Langfuse keys.

## D14. Build order (vertical slices, each one runnable)
1. `git init`, then `uv run newsloader digest`: arXiv fetch → stage 0 → keyword rank → top 5 sent to Telegram (local).
2. Neon + pgvector + Voyage embeddings: stage 1 with `interests.yaml`.
3. DeepSeek rerank + summaries (stages 2–3).
4. Langfuse tracing + cost log + digest footer.
5. Docker → Cloud Run + Cloud Scheduler + GitHub Actions deploy.
6. Telegram webhook: 👍/👎, `/today`, `/topics`.
7. Golden set + `label` CLI → eval gate in CI.
8. Cost guardrails (per-run cap, monthly budget, fallback).
