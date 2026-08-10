# RAGShield - Secure Enterprise RAG & Knowledge Intelligence Platform

An **authorization-aware RAG (Retrieval-Augmented Generation) platform**. It answers
questions over a private document corpus while enforcing fine-grained access control
**inside the retrieval layer** — the LLM only ever receives evidence the requester is
allowed to see.

## Highlights

- **Multi-tenant** — data is isolated per tenant at the row level and at vector search time.
- **ACL-aware retrieval** — RBAC roles + per-document ACLs + ABAC policies are resolved
  *before* any search. Both the Qdrant query filter and the BM25 corpus are restricted to
  the user's authorized documents, and every returned chunk is re-verified.
- **Hybrid retrieval** — dense embeddings (Qdrant) + lexical BM25 fused with Reciprocal
  Rank Fusion; optional cross-model LLM reranker.
- **Grounded answers with citations** — the generator can only cite retrieved chunks and
  returns the source documents used.
- **Observability & audit** — query tracing, latency metrics, security telemetry, and a
  full audit log of sensitive actions.
- **Evaluation gates** — recall/precision/groundedness/completeness gates protect deployed
  prompt/model versions (offline evaluation + canary promotion).
- **Versioning** — prompt versions and model configurations are versioned entities, so the
  LLM "brain" is reproducible and rollback-able.

## Architecture

```
┌───────────────┐   HTTPS/JSON   ┌──────────────────────────┐
│   Client / UI │ ─────────────▶ │  FastAPI backend (:8000)  │
└───────────────┘                └────────────┬─────────────┘
                                              │
              ┌───────────────────────────────┼────────────────────────────┐
              │                               │                            │
      ┌───────▼────────┐              ┌───────▼─────────┐          ┌───────▼─────────┐
      │   PostgreSQL   │              │   Qdrant (:6333)│          │   Ollama (:11434)│
      │  users, roles, │              │ vector store    │          │ embeddings +    │
      │  ACLs, docs,   │              │ (dense search)  │          │ chat + rerank   │
      │  audit, eval   │              └─────────────────┘          └─────────────────┘
      └────────────────┘
```

| Component  | Purpose |
|------------|---------|
| **FastAPI backend** | REST API, authentication (JWT), authorization, ingestion, retrieval, generation, observability, evaluation |
| **PostgreSQL 16** | Source of truth for users, roles, permissions, document metadata, audit logs, evaluation data, model/prompt versions |
| **Qdrant** | Vector index. Every point carries security payload (`tenant_id`, `document_id`, `owner_id`, `classification`) so retrieval can filter by authorization at query time |
| **Ollama** | Local LLM runtime. `qwen3-embedding:8b` for embeddings, `llama3.2:3b` for chat; optional LLM reranker |
| **FileStore** | Filesystem object store: `data/files/{tenant_id}/{document_id}/{original,extracted}/` |

## How it works

### Ingestion pipeline

`VALIDATE → STORE → EXTRACT → CHUNK → EMBED → INDEX → READY`

1. Upload goes through `validate_upload` (allowed types, size limit).
2. Original bytes saved to the FileStore; a `Document` row and a `DocumentVersion`
   (with checksum) are created.
3. `extract_text` pulls raw text (PDF, DOCX, XLSX, XLS, HTML, TXT, MD, JSON, CSV).
   Scanned/image PDFs fall back to built-in OCR (RapidOCR), so image-only documents
   can be ingested too.
4. `chunk_text` splits the text into overlapping chunks (configurable size/overlap).
5. Chunks are embedded with the configured embedding model and upserted into Qdrant.
   Each point carries the security payload above.
6. Status moves to `READY`.

### Retrieval pipeline (per query, per user)

```
authorize ─▶ build BM25 corpus ─▶ dense search ─▶ RRF fusion ─▶ (optional) rerank ─▶ ACL verify ─▶ answer
```

1. `authorized_document_ids(identity)` is computed **first**. It unions:
   - documents the user **owns**,
   - documents with an **everyone** read ACL,
   - documents with a **user** or **role** read ACL,
   - documents granted by **ABAC policies**,
   - everything if the user holds an `owner`/`admin` role.
2. The BM25 corpus is built from Qdrant points restricted to those document ids, and the
   dense query is filtered with the same set.
3. Reciprocal Rank Fusion combines the dense and lexical ranked lists (keyed by chunk id).
4. An optional LLM reranker reorders the fused list (enabled via `RERANKER_ENABLED`).
5. `verify_chunks` re-authorizes each chunk against the DB before anything reaches the
   prompt — defense in depth.
6. The chat model answers using only the verified chunks and must cite them.

### Authorization model

- **Roles** (system, seeded): `owner`, `admin`, `manager`, `employee`, `lecturer`,
  `student`. `owner`/`admin` bypass document ACLs within their tenant.
- **ACL** per document: principal types `user`, `role`, `everyone`, action `read`.
- **ABAC policies**: attribute-based rules evaluated against subject + resource attributes.
- Every sensitive API call is written to the **audit log**.

## Project tree

```
RAGShield/
├── .env / .env.example        # environment configuration
├── docker-compose.yml         # PostgreSQL + Qdrant
├── README.md
├── data/
│   └── samples/               # demo documents (alice/bob salary, policy, secret)
├── backend/
│   ├── alembic/               # DB migrations (initial_schema)
│   ├── alembic.ini
│   ├── requirements.txt
│   ├── tests/
│   ├── data/files/            # stored originals + extracted text
│   └── app/
│       ├── main.py            # FastAPI app factory, startup bootstrap
│       ├── api/v1/            # REST endpoints (auth, chat, admin_*, users, ...)
│       ├── auth/              # RBAC roles/permissions, JWT, authorization service
│       ├── core/              # settings, database, bootstrap, security
│       ├── embeddings/        # Ollama embedding provider
│       ├── generation/        # chat gateway, grounding, prompts
│       ├── ingestion/         # extractors, chunking, ingestion pipeline
│       ├── models/            # SQLAlchemy models (user, tenant, document, rbac, ...)
│       ├── observability/     # tracing, audit, security metrics
│       ├── retrieval/         # hybrid retrieval, BM25, vector index, reranker, ACL filter
│       ├── schemas/           # Pydantic request/response schemas
│       ├── storage/           # FileStore
│       └── versioning/        # model/prompt versioning + canary promotion
└── frontend/                  # React + Vite admin UI (proxies /api -> :8000)
    ├── vite.config.ts         # dev proxy to http://localhost:8000
    └── src/
        ├── pages/             # Login, Chat, Tenants, Users, Documents, Permissions,
        │                      # Policies, Models, Settings, Evaluation, Observability, Audit
        ├── context/           # auth provider (JWT in localStorage, auto-refresh)
        ├── components/        # layout/sidebar, shared UI kit
        └── lib/               # typed API client + SSE streaming chat client
```

## Prerequisites

- **Docker Desktop** (PostgreSQL + Qdrant)
- **Python 3.11**
- **Ollama** installed locally with the models used in `.env`:
  ```sh
  ollama pull qwen3-embedding:8b
  ollama pull llama3.2:3b
  ```

## Running the project

### 1. Infrastructure

```sh
docker compose up -d          # starts ragshield-postgres and ragshield-qdrant
```

### 2. Backend

```sh
cd backend
python -m venv .venv
.\.venv\Scripts\activate        # Windows
pip install -r requirements.txt

# apply database migrations
alembic upgrade head

# start the API
.\.venv\Scripts\python -m uvicorn app.main:app --port 8000
```

On startup the app is idempotently bootstrapped: default tenant, system roles &
permissions, admin user, and default prompt/model versions.

### 3. Frontend

```sh
cd frontend
npm install
npm run dev          # http://localhost:5173, proxies /api -> http://localhost:8000
```

The admin UI lives in `frontend/` (React + Vite + TypeScript). It signs in with the same
credentials as the API, keeps the JWT in localStorage with automatic refresh, and streams
chat responses over the POST-based SSE endpoint. The same UI can be served by the backend
after `npm run build` (the built assets in `frontend/dist/` are mountable statically).

The UI uses a custom "Aurora" design system (`src/index.css`): glassmorphism cards, animated
gradient backdrop, permission-aware sidebar with icons, skeleton loading states, gradient
buttons and badges, animated modals and chat bubbles. Fonts: Inter + Space Grotesk + JetBrains
Mono (Google Fonts, with system fallbacks).

### 4. Configuration

Copy `.env.example` to `.env` and adjust. Key variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+psycopg://ragshield:ragshield@localhost:5432/ragshield` | PostgreSQL DSN |
| `QDRANT_URL` / `QDRANT_COLLECTION` | `http://localhost:6333` / `enterprise_documents` | Vector store |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Ollama runtime |
| `EMBEDDING_MODEL` | `qwen3-embedding:8b` | Embedding model |
| `CHAT_MODEL` | `llama3.2:3b` | Chat/generation model |
| `EMBEDDING_DIM` | `1024` | Vector dimension |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `600` / `80` | Chunking parameters |
| `GROUNDING_MODE` | `heuristic` | Grounding strategy |
| `RERANKER_ENABLED` | `false` | Enable LLM reranker (`true` to use the Ollama reranker) |
| `HYBRID_TOP_K` / `RERANK_TOP_K` | `20` / `5` | Retrieval windows |
| `BOOTSTRAP_ADMIN_*` | `admin` / `admin123` | First-run admin credentials |

## API overview

Base path: `http://localhost:8000/api/v1`

| Method & path | Purpose |
|---------------|---------|
| `POST /auth/login` | Login, returns JWT |
| `GET /auth/me` | Current user summary |
| `GET /auth/identity` | Resolved identity: roles, permissions, tenant, `is_admin` |
| `POST /chat/query` | Ask the RAG assistant (`{query, stream}`), returns answer + citations |
| `GET /chat/conversations` | Past conversations |
| `GET /chat/conversations/{id}` | Messages in a conversation |
| `POST /admin/tenants` | Create an isolated tenant workspace (optionally with an admin user) |
| `GET /admin/tenants` | List tenants (`tenant.manage`) |
| `PATCH /admin/tenants/{id}` | Update tenant name/description/status |
| `POST /admin/documents/upload` | Upload + ingest a document (multipart `file`, optional `owner_id`) |
| `GET /admin/documents` | List documents readable by the caller |
| `DELETE /admin/documents/{id}` | Delete document (DB + vectors + files) |
| `PATCH /admin/documents/{id}` | Update metadata (title, classification, owner) |
| `POST /admin/documents/{id}/reindex` | Re-run ingestion for a document |
| `POST /admin/documents/{id}/replace` | Replace the file and re-ingest (keeps id + ACLs, bumps version) |
| `GET/POST /admin/permissions/documents/{id}` | List / grant document ACLs |
| `DELETE /admin/permissions/documents/{id}/{perm_id}` | Revoke ACL |
| `GET/POST /admin/permissions/policies` | List / create ABAC policies |
| `POST /admin/permissions/policies/{id}/test` | Dry-run a policy against attributes |
| `GET/POST /admin/users` | List / create users, assign roles (`tenant_id` enables cross-tenant) |
| `GET /admin/users/{id}` | User detail |
| `PATCH /admin/users/{id}` | Update user / roles / enable-disable |
| `GET /admin/users/roles/list` | System roles with permissions |
| `GET/POST /admin/models/config` | View / update default chat + embedding models |
| `GET/POST /admin/settings/prompts` | List / create prompt versions |
| `POST /admin/settings/prompts/{v}/activate` | Activate a prompt version |
| `GET/POST /admin/settings/experiments` | List / create canary A/B experiments |
| `GET /admin/settings/evaluation-gate?run_id=` | Check a run against release gates |
| `GET/POST /admin/evaluation/golden` | Golden questions |
| `GET/POST /admin/evaluation/runs` | Evaluation runs |
| `GET /admin/evaluation/runs/{id}/items` | Per-question metrics |
| `GET /admin/observability/latency` | Latency percentiles |
| `GET /admin/observability/traces` | Request traces |
| `GET /admin/observability/security` | Security action counts + events |
| `GET /admin/audit/logs` | Audit trail |
| `GET /admin/audit/security-events` | Security-relevant audit events |
| `GET /health` | Liveness |

Interactive docs: `http://localhost:8000/docs` (Swagger UI).

## Tenant workspaces (lecturer / student)

**What is a tenant?** A tenant is an isolated workspace — typically one company or one
course — that owns its own users, documents, ACLs, policies, conversations, and audit
logs. Every row in those tables carries a `tenant_id`, and each user belongs to exactly
one tenant, so a user in one tenant can never see another tenant's data. Users hold a role
*inside their tenant* (`owner` / `manager` / `employee` / `lecturer` / `student`), and
retrieval enforces the tenant boundary both in PostgreSQL and at vector-search time via the
Qdrant payload filter. This is the classic multi-tenant SaaS model: one platform, many
isolated workspaces.

Tenants are isolated workspaces — e.g. a separate tenant per course. Everything
(documents, users, ACLs, audit) is scoped by `tenant_id` in PostgreSQL and by the Qdrant
payload filter, so one lecturer's course can never leak into another's.

Typical flow:

1. A `tenant.manage` holder creates a tenant (optionally bootstrapping its admin):
   `POST /admin/tenants {"name": "ENGR-220 Students", "admin_username": "...", "admin_password": "..."}`
2. The tenant admin creates users (`lecturer`, `student` roles) — optionally targeting
   another tenant via `tenant_id`.
3. A lecturer uploads documents, replaces/re-indexes them, and grants `read` ACLs to
   individual students, roles, or everyone.
4. Students log in, see only their granted documents, and chat. Restricted files are
   excluded at retrieval time and the model abstains rather than fabricate.

### Seeded demo tenants

On startup the app is idempotently bootstrapped with two isolated tenants:

**1. `Default`** — `Platform Administrator` workspace

| User | Role | Notes |
|------|------|-------|
| `admin` | owner | platform admin (`admin/admin123`) |
| `alice` | employee | owns `alice_salary.txt` |
| `bob` | employee | owns `bob_salary.txt` |
| `charlie` | owner | sees everything |
| `sriharir` | employee | dept. `aiml` |

| Document | Type | Classification | Status |
|----------|------|----------------|--------|
| `company_policy.txt` | general | internal | READY |
| `company_secret.txt` | general | internal | READY |
| `alice_salary.txt` | general | internal | READY |
| `bob_salary.txt` | general | internal | READY |

**2. `ENGR-220 Students`** — intro course workspace (`665cd9f0…`)

| User | Role | Notes |
|------|------|-------|
| `engr_admin` | owner | tenant admin (`engr_admin/engrpass123`) |
| `lecturer1` | lecturer | uploads/grades, can read restricted files (`lecturer1/lecturerpass1`) |
| `student1` | student | only sees granted, non-restricted docs (`student1/studentpass1`) |

| Document | Type | Classification | Status |
|----------|------|----------------|--------|
| `Syllabus v1` | text | internal | READY (v2) |
| `Exam Answer Key` | text | restricted | READY |
| `Exam Key Scanned` | text | restricted | READY (OCR) |
| `Gradebook` | text | internal | READY (xlsx) |

Everything is scoped by `tenant_id`: `student1` can chat with the syllabus but the
restricted exam keys are excluded from his retrieval, while `lecturer1` can access them.
The tenant ids are queryable via `GET /admin/tenants`.

## Demo setup and security matrix

The bundled samples (`data/samples/`) model a small company:

- `alice_salary.txt` — Alice Smith, EMP-001, salary 85000 INR
- `bob_salary.txt` — Bob Jones, EMP-002, salary 95000 INR
- `company_policy.txt` — leave policy (24 days), readable by **everyone**
- `company_secret.txt` — master API credential, restricted

Create demo users (`employee` role), upload the documents as admin (or set the salary
documents' `owner_id` to the matching employee), and grant the `everyone` read ACL on
`company_policy.txt`. The expected matrix:

| Question | Alice | Bob | Charlie |
|----------|:---:|:---:|:---:|
| Company policy? | ✓ | ✓ | ✓ |
| My salary? | ✓ | ✓ | ✓ |
| Alice salary? | ✓ | ✗ | ✓ |
| Bob salary? | ✗ | ✓ | ✓ |
| Company secret? | ✗ | ✗ | ✓ |

A ready-to-run checker lives at `data/security_matrix_check.py` — it logs in as each
user, asks every question, and compares whether the answer reveals the expected keyword.

## Testing

```sh
cd backend
.\.venv\Scripts\python -m pytest        # unit tests (run with the API stack up if integration is enabled)
```

The security behavior can be exercised end-to-end against a running server with:

```sh
.\.venv\Scripts\python ..\data\security_matrix_check.py
```

## Notes on behavior

- The LLM reranker is **disabled by default** (`RERANKER_ENABLED=false`); hybrid fusion
  order is stable and ACL-safe. If enabled, the reranker can only reorder already-authorized
  chunks — it can never add unauthorized ones.
- Document deletion removes the DB row, the Qdrant points, and the on-disk files for that
  document in one transaction-safe sequence.
- Retrieval keys fusion on a single chunk identity (payload `chunk_id`) so the same chunk
  is never double-counted across the dense and lexical paths.
