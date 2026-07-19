# The VC Brain Technical Design Document

> **Historical pre-build design (unmaintained).** The as-built system differs materially —
> see `docs/SYSTEM_DESIGN.md` (with its as-built banner) and the code. Notably: the backend
> is Python/FastAPI (not Next.js), there is **no embedding/vector tier** (no
> `signal_embeddings` table, no fuzzy/embedding resolution — strong-ID + normalized-name
> match only), and the NL query is a one-pass LLM ranking, not vector retrieval.

This document expands `docs/public/Design Document.pdf` into an implementation-oriented technical design for The VC Brain. The product is a founder-sourcing and investment-intelligence system that helps an investor find early founders, evaluate opportunities on evidence, and produce a decision-ready memo.

This design replaces the technology stack listed in section 12 of the source document. The implementation uses Next.js with TypeScript for both the frontend and the backend, Postgres with pgvector as the only database, and no Supabase services.

The design keeps the three source layers:

- Memory: the data foundation.
- Intelligence: the reasoning, scoring, validation, and memo layer.
- Experience: the investor-facing product.

It also keeps the four-stage pipeline:

- Sourcing.
- Screening.
- Diligence.
- Decision.

## 1. Product Goals

The product must support a small-check investor who needs to move from discovery to a defensible investment memo within a day.

Core goals:

- Source opportunities from inbound applications and outbound discovery.
- Preserve founder identity and Founder Score across companies.
- Score opportunities on three independent axes: Founder, Market, and Idea versus Market.
- Validate claims with source-level evidence and per-claim Trust Scores.
- Treat cold-start founders fairly by separating limited evidence from negative evidence.
- Generate a memo with citations, gaps, and a recommendation.
- Give an investor a clear ranked dashboard, opportunity detail view, memo view, founder profile, and outbound queue.

Non-goals for the first version:

- Portfolio monitoring.
- Follow-on investment workflows.
- Fund accounting and operations.
- Legal closing workflows.
- Automated final investment decisions without human review.

## 2. System Context

The system has one primary user type in the first version: an investor or analyst operating a fund-specific thesis.

External systems supply raw signals, document content, reasoning, authentication, and persistence.

```text
Investor
  -> Experience web app
  -> Backend API
  -> Memory services
  -> Intelligence services
  -> Postgres and pgvector
  -> External source APIs, OpenAI API, object storage
```

The investor can configure a thesis, submit or review applications, inspect evidence, generate memos, and activate outbound targets. Background jobs handle source ingestion, document parsing, claim extraction, validation, scoring, and memo generation.

## 3. Architecture

### 3.1 Runtime View

```text
                            +---------------------+
                            | External sources    |
                            | GitHub, arXiv, HN,  |
                            | Product Hunt,       |
                            | Crunchbase, decks   |
                            +----------+----------+
                                       |
                                       v
+------------------+        +---------+----------+        +-------------------+
| Experience       |        | Backend API        |        | Background jobs   |
| Next.js frontend |<------>| Next.js Route      |<------>| pg-boss workers   |
| TypeScript       |        | Handlers, TS       |        | Node.js process   |
+--------+---------+        +---------+----------+        +---------+---------+
         |                            |                             |
         |                            v                             v
         |                  +---------+----------+        +---------+---------+
         |                  | Intelligence      |        | Memory            |
         |                  | extraction,       |        | ingestion,        |
         |                  | validation,       |        | resolution,       |
         |                  | scoring, memo     |        | storage, search   |
         |                  +---------+----------+        +---------+---------+
         |                            |                             |
         +----------------------------+-------------+---------------+
                                                      |
                                                      v
                                +---------------------+    +---------------------+
                                | Postgres            |    | S3-compatible       |
                                | pgvector, pg-boss   |    | object storage      |
                                +---------------------+    | for decks           |
                                                           +---------------------+
```

### 3.2 Technology Stack

One TypeScript codebase serves the frontend, the backend API, and the workers.

- Framework: Next.js App Router with TypeScript. The frontend and the backend API live in one application, with API endpoints implemented as Route Handlers under `app/api`.
- Runtime: Node.js LTS.
- Database: Postgres 16 or newer with the pgvector extension. One database holds relational data, vectors, and the job queue.
- ORM and migrations: Drizzle ORM with drizzle-kit migrations. Drizzle supports the pgvector column type directly.
- Background jobs: pg-boss, a Postgres-backed job queue. Workers run as a separate long-lived Node.js process from the same repository.
- Authentication: Auth.js with the Drizzle adapter and Postgres-backed sessions.
- Object storage: a private S3-compatible bucket for uploaded decks, accessed only from server code.
- Validation: Zod schemas at every API boundary and on every model output before a database write.
- Testing: Vitest for unit and integration tests, Playwright for end-to-end tests.
- Reasoning: OpenAI API, called only from server code.

### 3.3 Layer Responsibilities

Memory owns durable facts and evidence:

- Source ingestion.
- Raw signal storage.
- Entity resolution.
- Deduplication.
- Structured records.
- Embeddings.
- Founder Score history.
- Search and retrieval APIs.

Intelligence owns derived analysis:

- Thesis filtering.
- Claim extraction.
- Claim validation.
- Trust Score calculation.
- Three-axis scoring.
- Cold-start scoring.
- Founder Score updates.
- Memo generation.
- Traceable rationale.

Experience owns investor workflows:

- Thesis configuration.
- Inbound application intake.
- Ranked dashboard.
- Opportunity detail.
- Claim evidence review.
- Memo view.
- Founder profile.
- Outbound queue and activation.

### 3.4 Pipeline Flow

Inbound opportunities:

```text
Deck and company name
  -> application intake
  -> deck parsing
  -> public source enrichment
  -> entity resolution and deduplication
  -> claim extraction
  -> claim validation
  -> three-axis scoring
  -> memo generation
  -> ranked dashboard
```

Outbound opportunities:

```text
Public source scan
  -> founder candidate extraction
  -> cold-start scoring when needed
  -> outbound target ranking
  -> investor activation
  -> invitation to apply
  -> same screening flow as inbound
```

## 4. Modules

### 4.1 Experience Modules

`ThesisConfig`

- Captures sectors, stage, geography, check size, ownership target, risk appetite, and free-form thesis text.
- Sends normalized thesis data to the backend.
- Shows validation errors for unsupported or incomplete values.

`ApplicationIntake`

- Accepts company name and deck upload.
- Creates an inbound opportunity.
- Shows processing state while background jobs parse and enrich the application.

`RankedDashboard`

- Shows opportunities ranked against the active thesis.
- Supports compound natural-language query input.
- Shows source track, status, axis scores, momentum, trust warnings, and memo readiness.

`OpportunityDetail`

- Shows Founder, Market, and Idea versus Market as separate panels.
- Shows each axis score, trend, rationale, and evidence links.
- Shows extracted claims with Trust Score, validation status, confidence, and citations.

`MemoView`

- Shows the decision-ready memo.
- Includes company snapshot, investment hypotheses, SWOT, problem, product, traction, KPIs, risks, open diligence gaps, and recommendation.
- Keeps citations attached to each conclusion.

`FounderProfile`

- Shows the persistent Founder Score as a time series.
- Shows founder identity, identifiers, prior companies, shipped milestones, and confidence over time.

`OutboundQueue`

- Shows public-source founders that match the thesis.
- Allows the investor to activate a candidate, which creates an invitation and later an application.

### 4.2 Backend API Modules

Each module is a group of Next.js Route Handlers under `app/api`, with shared service code in `lib/` so route files stay thin. Workers import the same service code instead of calling the HTTP API.

`auth`

- Verifies user identity and permissions.
- Applies organization or fund-level authorization if multi-user support is enabled.

`opportunities`

- Creates, reads, filters, and updates opportunities.
- Coordinates application intake and opportunity status transitions.

`thesis`

- Stores and retrieves thesis configuration.
- Validates thesis fields used by the scoring layer.

`documents`

- Handles deck upload metadata.
- Stores files in object storage.
- Enqueues parsing jobs.

`jobs`

- Creates background jobs and exposes job status.
- Applies retries, idempotency keys, and failure reasons.

`intelligence_api`

- Exposes scoring, validation, cold-start scoring, and memo generation.
- Keeps synchronous API calls short by returning job IDs for long-running work.

### 4.3 Memory Modules

`source_fetchers`

- Fetch raw records from GitHub, Crunchbase, arXiv, Product Hunt, Hacker News Algolia, and uploaded decks.
- Normalize each source into a common `Signal` shape.
- Store source URL, source name, fetched timestamp, raw payload hash, and normalized text.

`entity_resolution`

- Matches founders and companies across sources.
- Uses strong identifiers first: email, domain, GitHub handle, LinkedIn URL, and company website.
- Falls back to fuzzy matching over names, domains, and embedding similarity.
- Preserves all source links after merging records.

`deduplication`

- Avoids duplicate signals by source record ID, canonical URL, content hash, and near-duplicate embeddings.
- Records merge decisions for auditability.

`embedding_index`

- Generates embeddings for source text, deck text, public profiles, claim text, and memo sections.
- Stores vectors in pgvector with metadata filters for opportunity, founder, company, source, and timestamp.

`founder_score_store`

- Stores Founder Score as a versioned time series.
- Never resets score when a founder starts a new company.
- Stores the reason, evidence, and actor or job that produced each score update.

### 4.4 Intelligence Modules

`ThesisEngine`

- Converts thesis config and natural-language query into structured filters and scoring weights.
- Evaluates opportunities against sector, stage, geography, check size, ownership, and risk appetite.
- Rejects unsupported interpretations instead of silently broadening a query.

`ExtractionAgent`

- Extracts claims from decks, public profiles, source documents, and source APIs.
- Writes claims with category, statement, evidence signal IDs, extraction confidence, and provenance.

`ValidatorAgent`

- Checks each claim against independent sources where possible.
- Produces `verified`, `unverified`, or `contradicted` status.
- Attaches rationale, independent source count, contradiction details, and confidence.

`TrustScoreEngine`

- Computes a per-claim confidence score.
- Increases confidence for independent corroboration, source quality, recency, and exact matches.
- Decreases confidence for contradictions, stale evidence, weak source quality, or sole reliance on applicant-provided material.
- Stores Trust Score history so changes are explainable.

`ThreeAxisScorer`

- Scores Founder, Market, and Idea versus Market independently.
- Computes trend for each axis from score history and new signals.
- Returns rationale and evidence for each axis.
- Does not produce a single blended score.

`ColdStartModule`

- Scores first-time or thin-footprint founders from public footprint proxies.
- Uses technical depth, communication, founder-market fit, and velocity.
- Returns a confidence band.
- Labels no public trail as limited evidence, not as negative evidence.

`MemoGenerator`

- Produces investor memo sections from validated claims, score sets, and retrieved evidence.
- Cites each conclusion.
- Marks gaps plainly when data is missing.
- Produces a recommendation only with stated assumptions and open risks.

`TraceabilityLogger`

- Stores trace events that explain inputs, source documents, model versions, generated outputs, and citations.
- Stores user-visible rationale, not private model chain-of-thought.

## 5. Data Model

All tables use:

- `id` as a stable UUID.
- `created_at` and `updated_at` timestamps.
- `source` or provenance fields when data is derived from an external system.
- Soft deletion only where auditability matters.

### 5.1 Core Tables

| Table | Key fields | Purpose |
| --- | --- | --- |
| `users` | `id`, `email`, `name`, `role`, `created_at` | Investor and analyst identities. |
| `funds` | `id`, `name`, `created_at` | Fund or workspace boundary for thesis, opportunities, and access control. |
| `thesis_configs` | `id`, `fund_id`, `sectors`, `stage`, `geography`, `check_size_min`, `check_size_max`, `ownership_target`, `risk_appetite`, `free_text`, `is_active` | Fund-specific lens used by sourcing, screening, and ranking. |
| `founders` | `id`, `canonical_name`, `current_company_id`, `founder_score_current`, `confidence_low`, `confidence_high`, `created_at` | Persistent person identity across startups. |
| `founder_identifiers` | `id`, `founder_id`, `type`, `value`, `source`, `confidence` | GitHub handle, LinkedIn URL, email, website, domain, or other identifiers used for resolution. |
| `companies` | `id`, `canonical_name`, `domain`, `description`, `status`, `created_at` | Company identity independent of a specific evaluation. |
| `opportunities` | `id`, `fund_id`, `company_id`, `primary_founder_id`, `source_track`, `status`, `submitted_at`, `rank_position` | One venture under evaluation for one fund. |
| `opportunity_founders` | `opportunity_id`, `founder_id`, `role`, `is_primary` | Many-to-many join between founders and opportunities. |
| `signals` | `id`, `opportunity_id`, `founder_id`, `company_id`, `source_name`, `source_url`, `source_record_id`, `raw_payload_hash`, `text`, `occurred_at`, `fetched_at`, `confidence` | Raw or normalized evidence from any source. |
| `signal_embeddings` | `id`, `signal_id`, `embedding`, `embedding_model`, `metadata` | Vector search index over signals. |
| `claims` | `id`, `opportunity_id`, `statement`, `category`, `claim_type`, `extraction_confidence`, `trust_status`, `trust_score`, `validation_summary`, `created_at` | Extracted assertion with validation state. |
| `claim_evidence` | `claim_id`, `signal_id`, `relationship`, `confidence` | Links claims to supporting or contradicting evidence. |
| `score_sets` | `id`, `opportunity_id`, `thesis_config_id`, `founder_axis_value`, `founder_axis_trend`, `market_axis_value`, `market_axis_trend`, `idea_market_axis_value`, `idea_market_axis_trend`, `created_at` | Three-axis screening result. |
| `score_rationales` | `id`, `score_set_id`, `axis`, `rationale`, `evidence_signal_ids` | User-visible explanation for each axis. |
| `founder_scores` | `id`, `founder_id`, `value`, `confidence_low`, `confidence_high`, `reason`, `evidence_signal_ids`, `created_at` | Persistent Founder Score time series. |
| `memos` | `id`, `opportunity_id`, `status`, `sections`, `recommendation`, `generated_at`, `model`, `version` | Decision-ready memo output. |
| `memo_citations` | `id`, `memo_id`, `section_key`, `claim_id`, `signal_id`, `citation_text` | Citation links from memo statements to evidence. |
| `sourcing_channels` | `id`, `name`, `type`, `enabled`, `last_success_at`, `yield_count`, `quality_score` | Source channel configuration and measurement. |
| `outbound_targets` | `id`, `fund_id`, `founder_id`, `status`, `score_snapshot`, `activation_message`, `activated_at` | Founders identified for outbound activation. |
| `jobs` | `id`, `type`, `status`, `input_ref`, `attempt_count`, `last_error`, `started_at`, `completed_at` | Background processing state. |
| `trace_events` | `id`, `opportunity_id`, `job_id`, `event_type`, `input_refs`, `output_refs`, `model`, `metadata`, `created_at` | Audit and traceability for derived outputs. |
| `audit_events` | `id`, `actor_id`, `fund_id`, `event_type`, `entity_type`, `entity_id`, `metadata`, `created_at` | User and system action history. |

Two implementation notes:

- Auth.js manages its own `accounts`, `sessions`, and `verification_tokens` tables through the Drizzle adapter. They sit alongside `users` and come from the adapter schema, not hand-written migrations.
- `signal_embeddings.embedding` is a pgvector `vector` column. Its dimension is fixed by the embedding model, and `embedding_model` is stored on every row so a model change can be migrated deliberately.

### 5.2 Important Relationships

- A `fund` has many `thesis_configs`, but only one active thesis for default ranking.
- A `founder` can have many `companies` through `opportunity_founders`.
- An `opportunity` belongs to one fund and one company.
- A `signal` can attach to an opportunity, founder, company, or any combination.
- A `claim` belongs to one opportunity and references one or more signals through `claim_evidence`.
- A `score_set` belongs to one opportunity and one thesis config.
- A `memo` belongs to one opportunity and cites claims and signals.
- A `founder_score` belongs to one founder and is never scoped only to the current opportunity.

### 5.3 Enumerations

`opportunity.status`:

- `submitted`
- `ingesting`
- `screening`
- `diligence`
- `memo_ready`
- `rejected`
- `watchlist`
- `investor_review`

`source_track`:

- `inbound`
- `outbound`

`claim.trust_status`:

- `verified`
- `unverified`
- `contradicted`

`axis_trend`:

- `improving`
- `stable`
- `declining`
- `unknown`

`job.status`:

- `queued`
- `running`
- `succeeded`
- `failed`
- `retrying`
- `cancelled`

## 6. API Contract

The backend API is JSON over HTTPS, implemented as Next.js Route Handlers under `app/api`. Long-running operations return a job ID. Clients poll job status or subscribe to server-sent events if added later.

Conventions:

- IDs are UUID strings.
- Timestamps are ISO 8601 UTC strings.
- Requests include an authenticated user context.
- Responses include only objects the user can access through their fund or workspace.
- Error responses use a stable shape:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Company name is required.",
    "details": {
      "field": "company_name"
    }
  }
}
```

### 6.1 Thesis APIs

`GET /api/thesis-configs/active`

Returns the active thesis for the current fund.

`PUT /api/thesis-configs/active`

Request:

```json
{
  "sectors": ["AI infrastructure"],
  "stage": ["pre-seed", "seed"],
  "geography": ["Berlin", "Europe"],
  "check_size_min": 50000,
  "check_size_max": 250000,
  "ownership_target": 0.01,
  "risk_appetite": "high",
  "free_text": "Technical founders with enterprise traction and no prior venture backing."
}
```

Response:

```json
{
  "id": "3cb0d64a-0630-4d31-8d58-badf4d5cba41",
  "is_active": true,
  "updated_at": "2026-07-19T00:00:00Z"
}
```

### 6.2 Application APIs

`POST /api/applications`

Creates an inbound opportunity and enqueues ingestion.

Request:

```json
{
  "company_name": "Ligarch",
  "founder_name": "Aria Vance",
  "deck_file_id": "ab5f2be1-6c7f-4d1a-98f0-4cc88958a782"
}
```

Response:

```json
{
  "opportunity_id": "dd1b4b64-6c99-4fdc-87c0-4db967649605",
  "job_id": "a2b59ed6-7524-4d79-b33f-93ca05a9d8ea",
  "status": "ingesting"
}
```

`POST /api/documents/decks`

Uploads a deck and returns a `deck_file_id`. The API must enforce file type, file size, malware scanning, and storage access controls.

### 6.3 Opportunity APIs

`GET /api/opportunities`

Query parameters:

- `status`
- `source_track`
- `query`
- `limit`
- `cursor`

Response:

```json
{
  "items": [
    {
      "id": "dd1b4b64-6c99-4fdc-87c0-4db967649605",
      "company_name": "Ligarch",
      "primary_founder": {
        "id": "0481f8f5-835b-48e9-bba9-c6f17820397f",
        "name": "Aria Vance"
      },
      "source_track": "inbound",
      "status": "memo_ready",
      "rank_position": 1,
      "axis_summary": {
        "founder": { "value": 86, "trend": "improving" },
        "market": { "value": 81, "trend": "stable" },
        "idea_market": { "value": 78, "trend": "improving" }
      },
      "trust_warning_count": 0
    }
  ],
  "next_cursor": null
}
```

`GET /api/opportunities/{opportunity_id}`

Returns the opportunity detail bundle: founder, company, score set, claims, evidence, memo status, and open gaps.

`POST /api/opportunities/{opportunity_id}/screen`

Enqueues extraction, validation, and three-axis scoring.

Response:

```json
{
  "job_id": "3103ff84-9640-4d1f-8e95-97622e66a8cf",
  "status": "queued"
}
```

`GET /api/opportunities/{opportunity_id}/scores/latest`

Returns the latest three-axis score set and rationale.

`GET /api/opportunities/{opportunity_id}/claims`

Returns extracted claims, their evidence, Trust Scores, and validation status.

### 6.4 Memo APIs

`POST /api/opportunities/{opportunity_id}/memo`

Enqueues memo generation.

Response:

```json
{
  "job_id": "a2ac18f0-9c82-4a47-9776-933d31f5118f",
  "status": "queued"
}
```

`GET /api/opportunities/{opportunity_id}/memo`

Returns memo sections, citations, recommendation, gaps, and generation metadata.

### 6.5 Founder APIs

`GET /api/founders/{founder_id}`

Returns profile, identifiers, current and prior opportunities, Founder Score history, and supporting evidence.

`GET /api/founders/{founder_id}/scores`

Returns the Founder Score time series with confidence bands.

### 6.6 Outbound APIs

`GET /api/outbound-targets`

Returns ranked outbound candidates for the active thesis.

`POST /api/outbound-targets/{target_id}/activate`

Creates an activation message and marks the target as invited.

Request:

```json
{
  "message_override": null
}
```

Response:

```json
{
  "target_id": "0e7f438e-f52b-481f-b515-e89db8e95413",
  "status": "invited",
  "activation_message": "Aria, we are looking for technical founders building AI infrastructure in Europe..."
}
```

### 6.7 Job APIs

`GET /api/jobs/{job_id}`

Response:

```json
{
  "id": "a2b59ed6-7524-4d79-b33f-93ca05a9d8ea",
  "type": "screen_opportunity",
  "status": "running",
  "attempt_count": 1,
  "progress": {
    "current_step": "validate_claims",
    "completed_steps": ["extract_claims"]
  },
  "last_error": null
}
```

## 7. Frontend Flows

### 7.1 Thesis Configuration

Entry point: first screen for a new fund or first demo scene.

Flow:

1. Investor opens Thesis Config.
2. Investor enters structured fields and free-form thesis.
3. Frontend validates required fields locally.
4. Backend stores the active thesis.
5. Dashboard refreshes using the updated thesis.

Required states:

- Empty thesis.
- Edited but unsaved thesis.
- Save in progress.
- Validation error.
- Saved thesis.

### 7.2 Inbound Application Intake

Flow:

1. Investor or applicant enters company name and uploads a deck.
2. Frontend sends deck to document upload API.
3. Frontend creates application with returned file ID.
4. Backend creates opportunity and ingestion job.
5. Frontend shows processing status.
6. Opportunity appears in the ranked dashboard when screening is complete.

Required states:

- Upload progress.
- Unsupported file type.
- Oversized file.
- Parse failed with retry option.
- Ingestion running.
- Screening complete.

### 7.3 Ranked Dashboard

Flow:

1. Investor enters a compound natural-language query.
2. Backend resolves query against thesis config and stored signals.
3. Dashboard shows ranked opportunities.
4. Investor filters by status, source track, score trend, trust warnings, or memo readiness.
5. Investor opens an opportunity detail view.

The dashboard must not hide disagreement between axes. It can sort by rank, but each opportunity still shows Founder, Market, and Idea versus Market independently.

### 7.4 Opportunity Detail

Flow:

1. Investor opens an opportunity.
2. Frontend loads opportunity bundle.
3. Frontend displays three independent axis panels.
4. Investor reviews claims and evidence.
5. Investor opens cited source records or starts memo generation.

Key product rule:

- A contradicted claim must be visible before the memo recommendation.
- Unverified claims are allowed, but they must be labeled.

### 7.5 Memo View

Flow:

1. Investor opens memo view.
2. If no memo exists, frontend offers Generate Memo.
3. Backend generates memo as a job.
4. Frontend shows memo sections when complete.
5. Investor opens citations inline.
6. Investor sees gaps as explicit unanswered diligence items.

Required sections:

- Company snapshot.
- Investment hypotheses.
- SWOT.
- Problem and product.
- Traction and KPIs.
- Risks and diligence gaps.
- Recommendation.

### 7.6 Founder Profile

Flow:

1. Investor clicks founder name from an opportunity.
2. Frontend loads founder profile and score history.
3. Founder Score timeline shows prior startups and milestone updates.
4. Investor can inspect supporting evidence for score changes.

Product rule:

- Founder Score belongs to the person. It does not reset when a company winds down.

### 7.7 Outbound Queue

Flow:

1. Investor opens outbound queue.
2. Frontend shows thesis-matched founders from public source scanning.
3. Investor opens a candidate and reviews cold-start assessment if applicable.
4. Investor clicks Activate.
5. Backend creates activation message and marks the target as invited.
6. If the founder applies, the opportunity enters the same pipeline as inbound.

## 8. Background Jobs

The system uses pg-boss as the worker queue for every operation that can exceed a normal request timeout or touch external rate-limited services. Jobs live in the same Postgres database, so a job can be enqueued in the same transaction that writes the record it will process. The `jobs` table in the data model is the application-facing status record; each row stores the pg-boss job ID so the status API never exposes queue internals. Workers run as a separate Node.js process built from the same repository.

### 8.1 Job Types

`ingest_application`

- Parses uploaded deck.
- Fetches company and founder signals.
- Writes normalized signals.
- Enqueues entity resolution.

`sync_source`

- Polls or searches one external source.
- Normalizes source records.
- Handles rate limits and pagination.
- Records sync cursor and failures.

`resolve_entities`

- Links signals to founders and companies.
- Applies deterministic matching first.
- Applies fuzzy and embedding matching second.
- Records merge decisions.

`generate_embeddings`

- Creates embeddings for text signals and claims.
- Writes pgvector records.
- Retries transient model or network errors.

`extract_claims`

- Reads deck text and retrieved signals.
- Writes structured claims.
- Links claims to supporting signals.

`validate_claims`

- Searches independent sources for each claim.
- Updates Trust Score and validation status.
- Flags contradictions.

`score_opportunity`

- Runs thesis scoring.
- Computes three-axis score set.
- Updates Founder Score if new founder milestones are observed.

`cold_start_score`

- Builds a proxy footprint from public signals.
- Computes trait scores and confidence band.
- Writes score rationale and limited-evidence labels.

`generate_memo`

- Retrieves validated claims, score sets, and citations.
- Writes memo sections.
- Marks gaps.

`discover_outbound_targets`

- Scans public sources for founders matching the active thesis.
- Scores candidates.
- Writes outbound targets.

### 8.2 Retry and Idempotency

Every job should have an idempotency key based on job type and input reference. Retried jobs must not duplicate signals, claims, score sets, memos, or outbound targets.

Recommended retry policy:

- Retry transient network, timeout, and rate limit errors with exponential backoff.
- Do not retry validation errors until input changes.
- Store `last_error` with a concise operator-facing message.
- Keep raw exception details out of user-visible responses if they contain provider data or credentials.

### 8.3 Job Progress

Jobs expose progress through `jobs.progress.current_step` and `jobs.progress.completed_steps`. The frontend should use this to show state in application intake, opportunity detail, memo generation, and outbound discovery.

## 9. External Services

### 9.1 OpenAI API

Uses:

- Deck and PDF parsing where vision or document understanding is needed.
- Embeddings for signal and claim search.
- Claim extraction.
- Claim validation assistance.
- Cold-start trait extraction.
- Memo generation.

Design constraints:

- Store prompts and model versions with generated outputs.
- Require citations for generated claims and memo conclusions.
- Do not store private model chain-of-thought.
- Apply output schema validation before writing derived records.
- Keep model calls behind backend services, never from the browser.

### 9.2 Postgres and pgvector

Uses:

- Primary relational store.
- Vector search through pgvector.
- pg-boss queue tables.
- Auth.js session and account tables.

Design constraints:

- Apply schema changes only through drizzle-kit migrations.
- Add an HNSW index on embedding columns before vector search becomes a scan over large tables.
- Use a connection pooler if the API runs on serverless infrastructure, because parallel Route Handler invocations can exhaust direct connections.
- Enforce fund-level access control in application queries. There is no platform row-level security layer in front of this database.
- Back up the database before demo and production deploys.

### 9.3 Object Storage

Uses:

- Private S3-compatible bucket, such as AWS S3 or Cloudflare R2, for uploaded decks.

Design constraints:

- The browser never receives bucket credentials. Uploads pass through the backend or use short-lived pre-signed URLs.
- Objects are keyed by generated IDs, never by uploaded file names.
- Read access is limited to the API and worker service roles.

### 9.4 GitHub REST API

Uses:

- Public repository and contribution signals.
- Founder technical depth proxy.
- Working artifacts and activity cadence.

Constraints:

- Respect rate limits.
- Store source URLs and fetched timestamps.
- Avoid over-weighting absence of GitHub activity.

### 9.5 Crunchbase API

Uses:

- Funding, company, founder, and investor metadata.
- Contradiction checks for funding and company stage.

Constraints:

- Treat coverage gaps as missing data.
- Separate unavailability from negative evidence.

### 9.6 arXiv API

Uses:

- Research output.
- Technical depth signals.
- Domain expertise signals.

Constraints:

- Normalize author names carefully.
- Keep confidence lower unless identifiers corroborate the founder match.

### 9.7 Product Hunt API

Uses:

- Launch history.
- Shipping velocity.
- Product traction proxy.

Constraints:

- Treat popularity as one signal, not a business outcome.

### 9.8 Hacker News Algolia API

Uses:

- Technical discussion footprint.
- Launch and community signals.
- Founder communication proxy.

Constraints:

- Avoid using tone or popularity as a direct quality score.
- Store exact item URLs for review.

### 9.9 Email or Outreach Provider

The first version may only compose activation messages. If sending is added, use a dedicated provider such as SendGrid, Resend, or Postmark.

Constraints:

- Require investor confirmation before sending.
- Store sent message metadata.
- Support unsubscribe and suppression lists if outreach is automated.

## 10. Security and Privacy

### 10.1 Authentication and Authorization

- Require authentication for all non-public APIs. Sessions come from Auth.js and are stored in Postgres.
- Scope every record by fund or workspace.
- Enforce authorization inside every Route Handler and server action. Next.js middleware may redirect unauthenticated pages, but it is not the authorization boundary.
- Use least-privilege service keys for background jobs.
- Keep admin operations behind explicit role checks.

### 10.2 Secret Management

- Store API keys in deployment secret storage.
- Do not expose OpenAI, database, object storage, source API, or email provider keys to the browser. Next.js only ships environment variables prefixed with `NEXT_PUBLIC_` to the client bundle, so secrets must never use that prefix.
- Do not commit real `.env` files.
- Provide only example environment files when implementation begins.

### 10.3 Upload Safety

- Accept only expected deck file types.
- Enforce file size limits.
- Store uploads in private object storage.
- Scan uploads before parsing when available.
- Never use uploaded file names as storage paths without sanitization.
- Avoid fetching arbitrary URLs from deck contents unless SSRF protections are in place.

### 10.4 Data Privacy

- Classify decks, founder emails, outreach messages, and investor notes as sensitive.
- Keep raw public-source payloads and user-uploaded documents separate.
- Provide deletion workflows for uploaded decks and user-added data when required.
- Apply retention periods to raw source payloads if licensing terms require it.

### 10.5 LLM Safety

- Treat deck and public text as untrusted input.
- Use structured extraction schemas.
- Validate model outputs before database writes.
- Require evidence signal IDs for claims.
- Show gaps instead of allowing generated text to invent missing facts.
- Do not put secrets or hidden system instructions in prompts that include untrusted user content.

### 10.6 Auditability

- Record audit events for thesis changes, application submissions, memo generation, outbound activation, and manual overrides.
- Preserve evidence links after entity merges.
- Record who generated or approved an outbound message.

## 11. Testing Strategy

Unit, contract, and integration tests use Vitest. End-to-end tests use Playwright against a seeded database.

### 11.1 Unit Tests

Cover deterministic logic:

- Entity resolution exact-match rules.
- Deduplication by source record ID, URL, content hash, and near-duplicate threshold.
- Trust Score calculation.
- Founder Score update logic.
- Axis trend calculation.
- Cold-start confidence band rules.
- API request validation.

### 11.2 Contract Tests

Cover stable boundaries:

- Memory read APIs return the opportunity bundle shape expected by Intelligence.
- Intelligence APIs return score, claim, and memo shapes expected by Experience.
- Error responses use the standard error envelope.
- Job APIs return stable status values and progress fields.

### 11.3 Integration Tests

Cover service interactions:

- Deck upload creates an opportunity and job.
- Ingestion writes signals and embeddings.
- Claim extraction writes claims with evidence IDs.
- Validation marks at least one seeded contradiction.
- Memo generation creates citations for memo conclusions.
- Outbound activation moves target status to `invited`.

### 11.4 End-to-End Tests

Use the seeded demo data from the source design:

- Aria Vance and Ligarch as the strong match.
- Nadia Ksanti and PulseGrid as the contradiction case.
- Mateo Rossi as the cold-start founder.
- One weaker opportunity to show ranking.

Critical paths:

- Configure thesis and run compound query.
- Open ranked opportunity and inspect three axes.
- Inspect verified and contradicted claims.
- Open cold-start founder profile with confidence band.
- Generate and read memo with citations and gaps.
- Activate outbound candidate.

### 11.5 Evaluation Tests for LLM Outputs

Automated tests should reject generated outputs when:

- A claim has no evidence signal ID.
- A memo conclusion has no citation.
- A missing field is filled with invented content.
- Contradictory evidence is ignored.
- The three axes are collapsed into one aggregate score.
- Limited evidence is treated as negative evidence.

### 11.6 Security Tests

Cover:

- Unauthorized access across fund boundaries.
- Upload type and size rejection.
- Attempts to access private deck files without authorization.
- Prompt injection in deck text.
- SSRF attempts through uploaded content.
- Missing or invalid auth tokens.

## 12. Observability

### 12.1 Logs

Use structured logs with:

- `request_id`
- `job_id`
- `fund_id`
- `opportunity_id`
- `founder_id`
- `source_name`
- `event_type`
- `duration_ms`
- `status`
- `error_code`

Do not log:

- API keys.
- Full uploaded deck contents.
- Founder private contact details unless explicitly needed and redacted.
- Full model prompts if they include sensitive uploaded data.

### 12.2 Metrics

Core product metrics:

- Applications submitted.
- Opportunities screened.
- Memos generated.
- Outbound targets discovered.
- Outbound targets activated.
- Claims extracted per opportunity.
- Claims verified, unverified, and contradicted.
- Average time from submission to memo ready.

Quality metrics:

- Percentage of memo conclusions with citations.
- Average Trust Score by source.
- Contradiction rate by source.
- Entity merge conflict rate.
- Cold-start confidence band width.

System metrics:

- API latency.
- Job queue depth.
- Job duration by type.
- Job failure rate.
- External API rate limit events.
- OpenAI token usage and cost.
- Database query latency.
- Vector search latency.

### 12.3 Traces

Trace across:

- HTTP request.
- Job enqueue.
- Worker execution.
- External API calls.
- Model calls.
- Database writes.

Each generated claim, score, and memo section should be traceable to source signals and job metadata.

### 12.4 Alerts

Alert when:

- Job failure rate exceeds threshold.
- Memo generation succeeds without citations.
- External source syncs fail repeatedly.
- OpenAI or database latency exceeds threshold.
- Queue age grows beyond the expected processing window.
- Storage upload scanning fails closed.

## 13. Deployment

### 13.1 Environments

Use at least three environments:

- Local development.
- Staging or demo.
- Production.

Each environment has separate:

- Database.
- Object storage bucket.
- API keys.
- Auth configuration.
- Worker queue.
- Seed data.

### 13.2 Services

Recommended deployment shape:

- Web app: one Next.js deployment serving the frontend and the API Route Handlers, hosted on Vercel or run as a Node.js container.
- Workers: a separate long-lived Node.js container built from the same repository, running the pg-boss workers. Workers do not run inside serverless functions because jobs outlive request timeouts.
- Database: managed Postgres with pgvector enabled, such as Neon or RDS, or a self-hosted instance.
- Storage: private S3-compatible bucket.
- Queue: pg-boss tables inside the primary Postgres database. No separate queue service.

### 13.3 Release Process

1. Apply database migrations to staging.
2. Deploy backend API and workers to staging.
3. Deploy frontend to staging.
4. Run smoke tests against seeded demo data.
5. Validate one full inbound path and one outbound path.
6. Apply migrations to production.
7. Deploy backend API and workers to production.
8. Deploy frontend to production.
9. Monitor logs, queue depth, and job failure rate.

### 13.4 Database Migrations

- All schema changes go through drizzle-kit migrations committed to the repository.
- Migrations are reviewed before production.
- Destructive migrations require a backup and rollback plan.
- Seed data should be environment-specific and never mixed with production investor data.

### 13.5 Backups and Recovery

- Enable automated database backups.
- Keep object storage retention aligned with database backup retention.
- Test restoring demo data before the presentation.
- Record recovery steps for database restore, storage restore, and worker replay.

## 14. Risks and Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Source coverage is thin for early founders. | Cold-start founders may appear weaker than they are. | Use confidence bands and limited-evidence labels. Avoid penalizing missing public footprint. |
| Entity resolution merges two people incorrectly. | Evidence and scores can become misleading. | Use strong identifiers first, keep merge audit trails, and allow manual review for low-confidence merges. |
| Model output invents facts. | Memo trust is damaged. | Require evidence IDs, schema validation, citation checks, and gap marking. |
| Claims rely too much on applicant-provided data. | Traction claims may be overstated. | Track source independence and lower confidence for single-source applicant claims. |
| External API rate limits slow ingestion. | Screening delays increase. | Queue jobs, cache source responses, back off on rate limits, and show processing state. |
| Axis scores are collapsed into one ranking. | Investor loses important disagreement between dimensions. | Keep axis values visible everywhere and use rank only as dashboard ordering. |
| Founder Score becomes a credential proxy. | The system can reproduce network bias. | Make Founder Score one input, include cold-start scoring, and separate absence from negative evidence. |
| Uploaded decks expose sensitive data. | Privacy and trust risk. | Private storage, access control, retention policy, and limited logging. |
| Demo depends on live external sources. | Presentation can fail due to network or rate limits. | Freeze seeded demo database and rehearse with deterministic data. |
| Outreach automation sends unwanted messages. | Compliance and reputation risk. | Require human confirmation, maintain suppression lists, and log approvals. |

## 15. Open Decisions

These decisions should be resolved before implementation:

- Which Auth.js sign-in providers to enable first: email magic link, Google, or GitHub.
- Whether the first version sends outbound email or only composes messages.
- Which external sources are required for the demo versus deferred.
- Whether Crunchbase credentials are available and legally usable for the intended demo.
- The exact score scale for axes and Founder Score.
- The confidence thresholds for `verified`, `unverified`, and `contradicted`.
- The retention period for uploaded decks and raw external payloads.

## 16. Definition of Done

The first usable version is done when:

- The thesis lens can be configured.
- A compound natural-language query returns a ranked opportunity list.
- Inbound application intake accepts a deck and company name.
- Memory ingests at least two live sources plus deck upload.
- Entity resolution, deduplication, source tagging, and evidence storage work on seeded data.
- Opportunity detail shows Founder, Market, and Idea versus Market separately with trends.
- Claims show Trust Score, validation status, confidence, and evidence.
- At least one seeded contradiction is caught and shown.
- A cold-start founder is scored with trait scores, confidence band, and limited-evidence label.
- Founder Score persists across two companies for one founder.
- Memo generation produces required sections with citations and gaps.
- Outbound queue identifies and activates a founder into an invitation state.
- The demo path from the source design runs end to end on a frozen seed database.
