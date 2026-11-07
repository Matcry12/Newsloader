# Architecture — source of truth for the idea (see decisions.md for the why)

## 1. Daily pipeline (D2)
```mermaid
flowchart LR
    A[arXiv API<br/>union of users' categories] --> S0
    S0[Stage 0 · $0<br/>dedupe · v1 only] -->|all new| S1
    S1[Stage 1 · Gemini<br/>embed once · per user:<br/>max-cosine vs profile − 👎] -->|top 5| S3
    S3[Summaries · DeepSeek<br/>2-line summary +<br/>why it matters] --> T[Telegram<br/>digest + 💰 footer]
    T -->|👍/👎| FB[(feedback)]
    FB -.-> S1
    I[user profiles<br/>config/users/*.yaml] -.-> S1
    I -.->|categories| A
    G{{Cost guard D11<br/>per-run cap · monthly $1}} -.->|over → no summaries ⚠️| S3
```

## 2. Runtime & deploy (D4–D9)
```mermaid
flowchart LR
    CS[Cloud Scheduler<br/>08:00 VN Mon-Fri] -->|POST /run-digest| CR
    TG[Telegram] -->|webhook 👍/👎 /today /topics| CR
    CR[Cloud Run<br/>FastAPI container] --> DB[(Neon Postgres<br/>+ pgvector)]
    CR --> V[Gemini embed]
    CR --> D[DeepSeek LLM]
    CR --> LF[Langfuse traces]
    CR --> TG
    SM[Secret Manager] -.-> CR
    GH[GitHub Actions<br/>test · eval gate · deploy] -->|image| CR
```

## 3. Interfaces (swap points)
| Interface | v1 impl | demo stub | alt later |
|---|---|---|---|
| `Source` | arXiv API | fixture JSON | HN, GitHub trending |
| `Embedder` | Gemini gemini-embedding-001 | fake in tests | fastembed local |
| `LLMClient` | DeepSeek v4-flash | rule-based fake | Haiku |
| `VectorStore` | Neon pgvector | in-memory | Qdrant Cloud |
| `Sender` | Telegram Bot API | print to stdout | — |

## 4. Demo run
Each stage runs alone on `tests/fixtures/arxiv_sample.json` (e.g. `uv run python -m newsloader.filters`), reviewed, then connected. $0, no keys.
