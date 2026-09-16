# InsightFace-for-openvela

A **project-dedicated, fully isolated** face service for the openvela MVP. It is
a *new*, self-contained project: it does **not** touch the existing shared
`face-insightface-server` instances, their PostgreSQL library, or
`face_cache.pkl`.

> **Honesty statement (read first):** this service does **not** implement
> liveness detection. The configured model (`buffalo_l`) has no liveness
> capability. Every response returns
> `liveness = {"supported": false, "reason": "buffalo_l has no liveness model"}`.
> Detection scores and embedding similarities are **never** used as liveness
> proxies. Quality is reported as raw, honestly-computed signals; it is not a
> liveness or authenticity verdict.
>
> **This is photo comparison only and has NO anti-replay / anti-spoofing
> capability.** A face similarity (1:1 or 1:N) proves only that two images look
> alike; it does **not** prove that a live person was present. A printed photo,
> a screen replay or a re-photographed ID can reach a high similarity. Never
> treat a `matched` decision as proof of "on-site liveness", and never use it as
> the sole factor for a security decision. An explicit `require_liveness=true`
> request is refused with `501 LIVENESS_UNSUPPORTED` rather than faked.

## Why it exists (vs. the legacy servers)

| Capability | Legacy `/extract_face` | This service |
|---|---|---|
| Extract embeddings | **searches** the DB and auto-`INSERT`s (write side effect) | `POST /v1/extract` is **pure extraction, zero writes** |
| Membership check | whole-library top-1 (`/recognize`) | `POST /v1/verify` is **strict 1:1 for a named subject** |
| Missing target | returns some global top-1 | `SUBJECT_NOT_FOUND` — never degrades to top-1 |
| 1:N lookup | whole-library top-1 `/recognize` | namespace-scoped, read-only `search` with a conservative 3-state decision |
| Registration | no receipt, shared library | namespaced, receipt, `library_revision` |
| Library state | not observable per request | monotonic `library_revision` in every response |
| Quality / liveness | none | honest quality signals; **liveness explicitly unsupported** |

## Architecture

```
src/face_service/
  config.py    env config + fail-fast validation (names keys, never values)
  errors.py    stable ErrorCode -> (HTTP status, retryable) + envelope
  auth.py      optional constant-time internal token (env or 0600 file)
  model.py     FaceModel protocol + InsightFaceModel (ONLY insightface import,
               lazily) + FakeModel for tests
  quality.py   honest, computable quality signals (no fake metrics)
  store.py     isolated SQLite store: namespaces, receipts, library_revision
  api.py       FastAPI routes (read/write separation)
  app.py       app factory, request-id middleware, error handlers
  main.py      `python -m face_service` entrypoint
```

The model layer is behind a `FaceModel` protocol with a **lazy**
`insightface` import, so the whole app (API/store/quality) is importable and
testable without the CV stack or any model download. Tests inject `FakeModel`.

## Isolation boundary

* **Data:** SQLite (stdlib `sqlite3`), default
  `<service>/data/openvela_faces.sqlite3`. No PostgreSQL, no `face_cache.pkl`,
  no import of the existing 400 subjects.
* **Namespaces:** every read/write is scoped by `namespace`; cross-namespace
  data is invisible.
* **Audit:** a single monotonic `library_revision` is bumped on every write and
  returned in every response.
* **Model weights:** by default the service **read-only reuses**
  `~/.insightface/models` (weights are not identity data; this avoids a second
  881 MB download). This is configurable via `FACE_SVC_MODEL_ROOT`; point it at
  a private copy if strict separation of weights is required.
* **Binding:** defaults to `10.3.6.163:8010` (intranet only, **not** `0.0.0.0`).

## Model root layout

`FACE_SVC_MODEL_ROOT` must be the directory that **contains** the model
subdirectories, e.g. `~/.insightface/models`, with `buffalo_l/` inside it.
`insightface.app.FaceAnalysis` is given `root=<model_root>.parent`.

## HTTP API

Image input is accepted either as a `multipart/form-data` file field named
`image`, or as `application/json` with an `image_base64` string (a
`data:image/...;base64,` URL is also accepted). Anything else →
`UNSUPPORTED_MEDIA_TYPE`. All responses are JSON with a `request_id`.

The interactive documentation surfaces are **disabled**: `/docs`, `/redoc` and
`/openapi.json` all return **404**. The service is an internal protocol consumed
by the **Python Worker's `FacePort` adapter** (see
`backend/handoffs/B-face-service-worker-contract.md`, the frozen contract), which
never consumes OpenAPI; the schema must not be exposed without the internal
token.

### `POST /v1/extract` — read-only, zero writes

Returns `face_count`, `faces[]` (`bbox`, `det_score`, `embedding`, `dim`,
`quality`, `largest_face`), `largest_face_index`, optional echoed `namespace`,
`model_version`, `library_revision`, `liveness`, `request_id`.
**Never** returns a subject match. Blank/no-face image → `NO_FACE`.

### `POST /v1/quality` — read-only, zero writes

Same input; returns the `quality` block per face (no embeddings). Quality is
also embedded in `/v1/extract`; this endpoint is a convenience.

### `POST /v1/verify` — strict 1:1, read-only

Inputs: `namespace`, `subject_id`, image, optional `threshold` override,
optional `require_liveness`. Only the named subject's embedding is read. Returns
`matched`, `similarity`, `threshold`, `face_count`, `quality`, `liveness`,
`namespace`, `subject_id`, `model_version`, `library_revision`, `request_id`.
Missing namespace → `NAMESPACE_NOT_FOUND`; missing subject → `SUBJECT_NOT_FOUND`
(**never** a whole-library top-1). `require_liveness=true` → `LIVENESS_UNSUPPORTED`.

### `POST /v1/namespaces/{ns}/subjects` — the only write path

Inputs: `subject_id` (caller-chosen), image, optional `on_exists`
(`conflict`|`overwrite`), and the optional reconciliation keys
`correlation_id` / `provider_request_id`. Returns a receipt (`subject_id`,
`namespace`, `created`, `created_at`, `updated_at`, `embedding_dim`,
`model_version`, `quality`, `library_revision`, `replayed`, `registered_at`,
`request_id`) — **no embedding**, and the reconciliation keys are not echoed
back. `201` on create, `200` on overwrite **or idempotent replay**,
`409 SUBJECT_ALREADY_EXISTS` on conflict.

**Idempotent registration (contract §6.1).** The Worker registers *outside* its
lease and can lose the response; it then reconciles with the **same**
`correlation_id` rather than minting another one. Therefore:

| situation | result |
|---|---|
| `subject_id` absent | `201`, keys persisted, revision bumped |
| exists **and** `correlation_id` matches | `200` with `replayed: true` — stored subject returned **as-is**: no overwrite, **no revision bump** |
| exists but `correlation_id` differs (or is absent while one is stored) | `409 SUBJECT_ALREADY_EXISTS` — the stored reference image is **never** silently replaced |
| `on_exists=overwrite` | `200`, embedding replaced, revision bumped, new keys recorded (controlled back-office only; the Worker must not use it) |

Callers that send no `correlation_id` keep the exact previous behaviour
(`201` / `409`).

### `GET /v1/namespaces/{ns}/registrations/{correlation_id}` — read-only

Reconciliation lookup used after a lost register response. Optional query params
`provider_request_id` and `entity_id` **tighten** the match: a disagreement is
reported as `not_found` rather than returning a subject that does not belong to
the caller's own attempt.

```json
{"status": "registered", "subject_id": "…", "correlation_id": "…",
 "provider_request_id": "…", "registered_at": "…", "library_revision": 7,
 "request_id": "…"}
```

* `status` is only ever `registered` or `not_found` (an unknown correlation id is
  a normal `200` answer, because the Worker branches on `status`, not on the HTTP
  code). **`unknown` is never produced by the service** — it is a client-side
  transport state, and fabricating it would mask real failures.
* Zero writes: creates no namespace and never bumps `library_revision`. An
  unknown **namespace** is still `404 NAMESPACE_NOT_FOUND`.
* Minimum disclosure: no embedding, no quality block, no bbox, no reference-image
  ref, no other correlation's registration, no library listing.

### `POST /v1/compare` — image↔image 1:1, read-only, zero writes

Compares two **probe** images (`image_a` / `image_b`, or `image_a_base64` /
`image_b_base64` in JSON). Backs `FacePort.same_person` (three-view "same
person" confirmation). Unlike `/v1/verify` it reads **no** subject, so it cannot
disclose library contents.

Returns `matched`, `similarity`, `threshold`, `face_count_a`, `face_count_b`,
`quality_a`, `quality_b`, `liveness`, `reasons`, `model_version`,
`library_revision`, `request_id`.

* `threshold` **is** accepted here (default `FACE_SVC_VERIFY_THRESHOLD`) because
  nothing is looked up in a namespace, so a caller cannot lower a server-fixed
  library policy. Search still accepts no threshold.
* 0 faces on either side → `NO_FACE`; >1 face on either side →
  `MULTI_FACES_AMBIGUOUS` (the largest face is **never** picked: with two probes
  it would be ambiguous which face was compared to which).
* **Fail-closed on quality:** if either probe is below the quality floor,
  `matched` is `false` and `reasons` contains `quality_below_minimum` — even at
  similarity 1.0.
* `require_liveness` is **not** a parameter here; it is ignored, and the response
  reports `liveness.supported: false`. Photo comparison has **no anti-replay
  capability** and must never be used where liveness is required.

### `GET /v1/namespaces/{ns}/subjects/{id}` — read-only

Metadata (no embedding) + `library_revision` + `request_id`.

### `DELETE /v1/namespaces/{ns}/subjects/{id}` — write path

Returns `{deleted: true, subject_id, namespace, library_revision, request_id}`.
Deleting a non-existent subject → `404 SUBJECT_NOT_FOUND` (explicitly
**not** idempotent-success); a failed delete does not bump the revision.

### `GET /v1/health` — read-only, no auth

`status`, `model_loaded`, `model_version`, `library_revision`,
`uptime_seconds`, `liveness`. Never reloads the model. Public (no token) so a
local monitor can poll it. When the model is not loaded it stays **`200` +
`status:"degraded"`** (it reports, it does not refuse) — this behaviour is
deliberately unchanged.

### `GET /live` — public probe, no auth

Returns **`200 {"status":"alive"}`** whenever the process can answer. It does
**not** touch the model or SQLite, so it proves process liveness only.

### `GET /ready` — public probe, no auth

Readiness = **model loaded AND SQLite reachable**. Success returns `200`:
`{"status":"ready","model_loaded":true,"model_version":"…","library_revision":N}`.
Failure returns **`503`** with the standard error envelope:

* model not loaded → `MODEL_NOT_LOADED` (also chosen when both are down, since
  the model is the more fundamental prerequisite);
* SQLite unreachable → `STORE_UNAVAILABLE` (retryable).

Unlike `/v1/health`, `/ready` must fail when the service cannot serve identity
decisions; "not ready" is a refusal, not a status string. The bodies of both
probes contain no namespace, subject count, path, host, port or token
information. Deploy gates on `/ready`.

### `POST /v1/namespaces/{ns}/search` — internal 1:N, read-only

**Internal protocol endpoint for the trusted backend only** (token-protected).
It is a *namespace-scoped* search, **not** a public whole-library search, and is
not part of the public business API.

Request (same image encoding as extract/verify):

```json
{ "image": "<binary | base64 | data-url>", "media_type": "image/jpeg", "top_k": 5 }
```

* `top_k` optional integer, **2..10**, default `FACE_SVC_SEARCH_TOP_K` (5);
  out-of-range / non-integer → `400 INVALID_REQUEST`. The lower bound is **2**,
  not 1: this endpoint returns no candidate list and uses `top_k` solely to bound
  the candidate window for the margin rule, and a single candidate has no
  runner-up — `top_k=1` would make the ambiguity/margin check structurally
  vacuous (a near-tied library could then report `matched`).
* **The matching thresholds are server-fixed.** `threshold` /
  `match_threshold` / `margin` sent by a client are **ignored** — only
  `policy_version` is disclosed, never the numeric thresholds.
* Zero writes: it never registers a subject and never advances
  `library_revision`.

Response (`200` for every decision — `reliable_new`/`uncertain` are business
judgements, not errors):

```json
{
  "decision": "matched",
  "subject_id": "…",
  "similarity": 0.7321,
  "ambiguous": false,
  "quality": { "…": "…" },
  "subject_count": 12,
  "top_k": 5,
  "reasons": [],
  "policy_version": "search-v2",
  "model_version": "…",
  "library_revision": 7,
  "request_id": "…"
}
```

* `subject_id` and `similarity` appear **only** for `matched`; for
  `reliable_new` and `uncertain` those keys are **absent** (not `null`).
* `decision` is exactly one of **`matched` / `uncertain` / `reliable_new`** —
  the vocabulary the Worker's `FacePort` consumes. Any other value would be
  treated by the Worker as a dependency failure, so no fourth value may appear.
* Hard exclusions: no candidate list, no embedding, no registered subject's
  bbox/det_score, no numeric matching thresholds.
* `library_revision` and `subject_count` come from the **same read snapshot** as
  the candidate comparison.

Three-state decision (conservative; first match wins):

1. **Precondition errors always win** over any decision: unknown namespace →
   `NAMESPACE_NOT_FOUND`; no face → `NO_FACE` (a blank image is **not** a
   `reliable_new`); >1 face → `MULTI_FACES_AMBIGUOUS`; undecodable →
   `IMAGE_DECODE_FAILED`.
2. **Quality gate (fail-closed):** if `quality.min_acceptable` is false the
   decision can be **at most** `uncertain` (`reasons` contains
   `quality_below_minimum`); a blurred probe can never be `matched`.
3. `matched`: top similarity ≥ `search_match_threshold` **and** the gap to the
   best *different* candidate ≥ `search_margin` (a single-candidate library
   satisfies the margin).
4. `uncertain`: top ≥ threshold but the margin is not met → `ambiguous: true`;
   **or** the top lies within `search_uncertain_band` below the threshold.
5. `reliable_new`: the library is **non-empty**, the probe is a single face of
   acceptable quality, and the top similarity is below
   `threshold - uncertain_band`.
6. **Empty library → `uncertain`** with `subject_count: 0` and
   `reasons: ["empty_library"]` — deliberately **not** `reliable_new`. An empty
   namespace far more likely means "never populated" (or "cleared by mistake")
   than "this person is new", and answering `reliable_new` would mass-enrol
   everybody.

> **What `reliable_new` does and does not mean.** It states: *in this namespace,
> under the policy named by `policy_version`, a single acceptable-quality probe
> found no candidate reaching the threshold.* It is **not** proof of a new human
> being — a 1:N search cannot prove absence from the world, only absence from
> this library. `后端详细设计-V1-MVP.md:657` says a miss "只成为新人候选"
> (only becomes a new-person *candidate*), and `:663` forbids enabling real
> automatic enrolment before the PoC gate. Consumers must keep their own
> reconciliation (the Worker checks PostgreSQL for an existing member before
> enrolling) and must not treat `reliable_new` as an authorisation to enrol.

> **The thresholds are NOT calibrated.** `search_match_threshold = 0.60`,
> `search_uncertain_band = 0.10` and `search_margin = 0.05` are **conservative
> placeholder defaults**, not measured results. 0.60 is intentionally stricter
> than the 1:1 default 0.40 because false accepts grow with library size.
> Similarity values are **not** percentage confidence. **Until the thresholds
> are calibrated on authorised samples, no automatic enrolment/registration of
> a "new person" may be enabled** — an `uncertain`/`reliable_new` result is a
> candidate for review, never an automatic archive.

### `GET /v1/namespaces/{ns}/info` — read-only

`subject_count`, `library_revision`, `model_version`, `request_id`.
Unknown namespace → `NAMESPACE_NOT_FOUND`.

## Error codes

Unified envelope:

```json
{"error": {"code": "...", "message": "...", "retryable": false, "request_id": "..."}}
```

| Code | HTTP | retryable | Meaning |
|---|---|---|---|
| `NO_FACE` | 400 | false | No face detected |
| `MULTI_FACES_AMBIGUOUS` | 400 | false | >1 face where exactly one is required |
| `IMAGE_DECODE_FAILED` | 400 | false | Bytes are not a decodable image / bad base64 |
| `IMAGE_TOO_LARGE` | 413 | false | Body exceeds `FACE_SVC_MAX_BODY_BYTES` |
| `UNSUPPORTED_MEDIA_TYPE` | 415 | false | Content-Type not multipart or JSON |
| `INVALID_REQUEST` | 400 | false | Malformed params / invalid id / bad threshold |
| `SUBJECT_NOT_FOUND` | 404 | false | Subject absent in that namespace |
| `NAMESPACE_NOT_FOUND` | 404 | false | Namespace absent |
| `SUBJECT_ALREADY_EXISTS` | 409 | false | Conflict policy is `conflict` |
| `QUALITY_INSUFFICIENT` | 422 | false | Quality below minimums (only when enforced) |
| `LIVENESS_UNSUPPORTED` | 501 | false | `require_liveness=true` was requested |
| `MODEL_UNAVAILABLE` | 503 | true | Model stack missing / failed to load |
| `MODEL_NOT_LOADED` | 503 | true | Inference attempted before load |
| `STORE_UNAVAILABLE` | 503 | true | `/ready`: subject store (SQLite) unreachable |
| `UNAUTHORIZED` | 401 | false | Missing/invalid internal token |
| `CONCURRENCY_LIMIT` | 429 | true | All inference slots busy |
| `INFERENCE_TIMEOUT` | 504 | true | Inference exceeded `FACE_SVC_INFERENCE_TIMEOUT_SECONDS` |
| `INTERNAL_ERROR` | 500 | true | Unexpected error |

Errors never echo images, embeddings, tokens, or filesystem paths.

## Quality signals (honest by construction)

| Signal | Supported | Method |
|---|---|---|
| `det_score` | ✅ | Detector confidence (model output) |
| `blur` | ✅ | Variance of the 4-neighbour Laplacian over the grayscale crop |
| `bbox_area_ratio` | ✅ | bbox area / image area |
| `illumination` | ✅ | Grayscale mean + std of the crop |
| `pose` | ❌ `unsupported` | No validated estimator wired in this build |
| `occlusion` | ❌ `unsupported` | No validated estimator wired in this build |
| `liveness` | ❌ `unsupported` | `buffalo_l` has no liveness model |

`min_acceptable` is a coarse conjunction of configurable thresholds
(`FACE_SVC_QUALITY_MIN_DET_SCORE`, `..._MIN_BLUR`, `..._MIN_BBOX_RATIO`) and is
**only enforced when** `FACE_SVC_QUALITY_ENFORCE=true`. The defaults are
heuristics and must be recalibrated on real data.

## Verification threshold

`FACE_SVC_VERIFY_THRESHOLD` (default `0.40`) is the cosine-similarity threshold
on L2-normalised embeddings. 0.40 is a conservative starting point often used
for ArcFace-style 1:1; **it is not calibrated against this project's data** and
must be recalibrated (FAR/FRR) on real enrolment/query pairs before production.
It is configurable per request via the `threshold` field of `/v1/verify`.

The 1:N policy keys (`FACE_SVC_SEARCH_MATCH_THRESHOLD`,
`FACE_SVC_SEARCH_UNCERTAIN_BAND`, `FACE_SVC_SEARCH_MARGIN`) are likewise
**conservative placeholders and are not calibrated**. They are **server-side
only** and cannot be overridden per request (`/v1/compare` is the single
exception: it accepts `threshold` because it compares two probes and reads no
namespace). Because no calibration exists, the service must not be used to
automatically enrol a person: `uncertain` and `reliable_new` are review
candidates, and auto-enrolment stays disabled until the thresholds are
calibrated on authorised samples.

**Two different classes of number — do not confuse them.** The **matching**
thresholds (`search_match_threshold`, `search_uncertain_band`, `search_margin`)
are server-side policy and are **never disclosed** in any response; callers only
receive `policy_version`. The **quality** thresholds in the `quality.thresholds`
block (`det_score` = 0.50, `blur` = 30.0, `bbox_area_ratio` = 0.02) are a
different thing: they gate `min_acceptable`, are already returned by the
pre-existing public `/v1/quality` endpoint, and their presence in a search
response is not a new disclosure.

## Known limitations

* **Unbounded in-memory candidate scan (search).** `POST
  /v1/namespaces/{ns}/search` computes cosine similarity in Python (no vector
  library / index is allowed by the design), and returns no candidate list, so
  it **loads every embedding in the namespace into memory** to obtain the global
  top-k. Memory and latency therefore grow without bound as a namespace grows;
  there is **no pagination and no index**. This is acceptable only because MVP
  library sizes are small. A large-scale deployment needs a bounded/ANN
  retrieval design before this can be relied on.
* **`top_k` does not limit work, only the margin window.** Because the scan is
  exhaustive, a larger `top_k` does not reduce cost; it only widens the
  candidate window that participates in the margin/ambiguity rule.

## Configuration

All variables are prefixed `FACE_SVC_`. See `.env.example`.

| Key | Default | Notes |
|---|---|---|
| `HOST` | `10.3.6.163` | bind intranet only |
| `PORT` | `8010` | |
| `DATA_DIR` | `<service>/data` | |
| `DB_PATH` | `<data_dir>/openvela_faces.sqlite3` | |
| `MODEL_ROOT` | `~/.insightface/models` | read-only reuse |
| `MODEL_NAME` | `buffalo_l` | |
| `MODEL_VERSION` | `buffalo_l@insightface-0.7.3` | reported in responses |
| `VERIFY_THRESHOLD` | `0.40` | cosine similarity (1:1) |
| `SEARCH_MATCH_THRESHOLD` | `0.60` | 1:N match threshold (uncalibrated; stricter than 1:1) |
| `SEARCH_UNCERTAIN_BAND` | `0.10` | below-threshold band reported as `uncertain` |
| `SEARCH_MARGIN` | `0.05` | required gap to the runner-up for `matched` |
| `SEARCH_TOP_K` | `5` | candidates participating in the margin rule (2..10; lower bound 2 keeps the margin check meaningful) |
| `MAX_BODY_BYTES` | `10485760` | 10 MB |
| `INFERENCE_TIMEOUT_SECONDS` | `30` | |
| `MAX_CONCURRENCY` | `2` | |
| `INTERNAL_TOKEN` / `INTERNAL_TOKEN_FILE` | unset | prefer the 0600 file |
| `AUTH_REQUIRED` | `true` | fail-closed; no token ⇒ refuse to start |
| `AUTH_HEADER` | `X-Internal-Token` | |
| `REGISTER_ON_EXISTS` | `conflict` | or `overwrite` |
| `QUALITY_ENFORCE` | `false` | report-only unless true |
| `QUALITY_MIN_DET_SCORE` | `0.50` | |
| `QUALITY_MIN_BLUR` | `30.0` | |
| `QUALITY_MIN_BBOX_RATIO` | `0.02` | |
| `REQUEST_ID_HEADER` | `X-Request-Id` | echoed; inbound value sanitised |
| `LOG_LEVEL` | `INFO` | |

Booleans accept only `1/true/yes/on` or `0/false/no/off` (trimmed,
case-insensitive). Any other non-empty value is a startup `ConfigError` that
names the key and the allowed domain — a misspelling can never silently disable
a security control.

Startup validation refuses to start when a security key is missing/unsafe:

* `AUTH_REQUIRED=true` without a token, or a non-loopback `HOST` with auth
  disabled or without a token (allowed loopback values: `127.0.0.1`, `::1`,
  `localhost`);
* a token file that is unreadable or has group/other bits;
* `INTERNAL_TOKEN` and `INTERNAL_TOKEN_FILE` configured together.

Messages name keys only, never values.

## Access logging

Raw uvicorn access logs are **disabled** (`access_log=False`) because they print
the expanded request path, which contains identity references (namespace /
subject_id). The service emits its own sanitized access log on the
`face_service.access` logger:

```
access method=POST route=/v1/namespaces/{namespace}/subjects status=201 duration_ms=1.23 request_id=<id>
```

Only the matched route **template** (`route.path_format`), HTTP method, status,
request_id and duration are recorded. For unmatched paths it falls back to the
first two path segments (e.g. `/v1/namespaces/...`). Real namespace/subject
values, image bytes, embeddings and tokens are never logged.


## Tests

Tests never download models, never use real faces, never touch the network.
They use synthetic PIL images and an injected `FakeModel`.

```bash
cd backend/face-service
uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python pytest httpx 'fastapi==0.135.3' \
  'uvicorn>=0.44.0' 'numpy==2.4.4' 'pillow>=12.2.0' 'python-multipart>=0.0.24'
PYTHONPATH=src .venv/bin/python -m pytest -q
```

## Deployment

See `deploy/README-deploy.md`. The service runs as a **user-level** systemd
unit (linger must already be enabled: `loginctl show-user $USER -p Linger` →
`Linger=yes`). No system unit, no `nohup`.

## Explicit non-claims

* No liveness / anti-spoofing. **Photo comparison only: no anti-replay
  capability.** Similarity proves resemblance, never a live person present.
* No pose or occlusion estimation in this build.
* Actual embedding quality and CUDA-provider availability are **not** verified
  here; they depend on the real `buffalo_l` weights and host GPU.
* The 1:1 threshold and the 1:N search thresholds are not yet calibrated.
* Embeddings are sensitive biometric data; retention/encryption/access-control
  policy is out of scope of this service and must be handled by the caller.
