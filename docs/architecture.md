# Architecture — source of truth for the idea (see decisions.md for the why)

## 1. Daily pipeline (D2)
```mermaid
flowchart LR
    A[arXiv API<br/>union of users' categories] --> S0
    S0[Stage 0 · $0<br/>dedupe · v1 only] -->|all new| S1
    S1[Stage 1 · Voyage<br/>embed once · per user:<br/>max-cosine vs profile − 👎] -->|top K=30-50| S2
    S2[Stage 2 · DeepSeek<br/>1 batched rerank<br/>JSON id/score/reason] -->|top 5| S3
    S3[Stage 3 · DeepSeek<br/>2-line summary +<br/>why it matters] --> T[Telegram<br/>digest + 💰 footer]
    T -->|👍/👎| FB[(feedback)]
    FB -.-> S1
    I[user profiles<br/>config/users/*.yaml] -.-> S1
    I -.->|categories| A
    G{{Cost guard D11<br/>per-run cap · monthly $1}} -.->|over → embeddings-only ⚠️| S2
```

## 2. Runtime & deploy (D4–D9)
```mermaid
flowchart LR
    CS[Cloud Scheduler<br/>08:00 VN Mon-Fri] -->|POST /run-digest| CR
    TG[Telegram] -->|webhook 👍/👎 /today /topics| CR
    CR[Cloud Run<br/>FastAPI container] --> DB[(Neon Postgres<br/>+ pgvector)]
    CR --> V[Voyage embed]
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
| `Embedder` | Voyage voyage-4-lite | keyword overlap | OpenAI 3-small |
| `LLMClient` | DeepSeek v4-flash | rule-based fake | Haiku |
| `VectorStore` | Neon pgvector | in-memory | Qdrant Cloud |
| `Sender` | Telegram Bot API | print to stdout | — |

## 4. Demo run
Each stage runs alone on `tests/fixtures/arxiv_sample.json` (e.g. `uv run python -m newsloader.stage0`), reviewed, then connected. $0, no keys.
