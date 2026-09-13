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

## Why it exists (vs. the legacy servers)

| Capability | Legacy `/extract_face` | This service |
|---|---|---|
| Extract embeddings | **searches** the DB and auto-`INSERT`s (write side effect) | `POST /v1/extract` is **pure extraction, zero writes** |
| Membership check | whole-library top-1 (`/recognize`) | `POST /v1/verify` is **strict 1:1 for a named subject** |
| Missing target | returns some global top-1 | `SUBJECT_NOT_FOUND` — never degrades to top-1 |
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
(`conflict`|`overwrite`). Returns a receipt (`subject_id`, `namespace`,
`created`, `created_at`, `updated_at`, `embedding_dim`, `model_version`,
`quality`, `library_revision`, `request_id`) — **no embedding**. `201` on
create, `200` on overwrite, `409 SUBJECT_ALREADY_EXISTS` on conflict.

### `GET /v1/namespaces/{ns}/subjects/{id}` — read-only

Metadata (no embedding) + `library_revision` + `request_id`.

### `DELETE /v1/namespaces/{ns}/subjects/{id}` — write path

Returns `{deleted: true, subject_id, namespace, library_revision, request_id}`.
Deleting a non-existent subject → `404 SUBJECT_NOT_FOUND` (explicitly
**not** idempotent-success); a failed delete does not bump the revision.

### `GET /v1/health` — read-only, no auth

`status`, `model_loaded`, `model_version`, `library_revision`,
`uptime_seconds`, `liveness`. Never reloads the model. Public (no token) so a
local monitor can poll it.

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
| `VERIFY_THRESHOLD` | `0.40` | cosine similarity |
| `MAX_BODY_BYTES` | `10485760` | 10 MB |
| `INFERENCE_TIMEOUT_SECONDS` | `30` | |
| `MAX_CONCURRENCY` | `2` | |
| `INTERNAL_TOKEN` / `INTERNAL_TOKEN_FILE` | unset | prefer the 0600 file |
| `AUTH_REQUIRED` | `false` | if true, no token ⇒ refuse to start |
| `AUTH_HEADER` | `X-Internal-Token` | |
| `REGISTER_ON_EXISTS` | `conflict` | or `overwrite` |
| `QUALITY_ENFORCE` | `false` | report-only unless true |
| `QUALITY_MIN_DET_SCORE` | `0.50` | |
| `QUALITY_MIN_BLUR` | `30.0` | |
| `QUALITY_MIN_BBOX_RATIO` | `0.02` | |
| `REQUEST_ID_HEADER` | `X-Request-Id` | echoed; inbound value sanitised |
| `LOG_LEVEL` | `INFO` | |

Startup validation refuses to start when a security key is missing/unsafe
(e.g. `AUTH_REQUIRED=true` without a token, or a token file with group/other
bits). Messages name keys only, never values.

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

* No liveness / anti-spoofing.
* No pose or occlusion estimation in this build.
* Actual embedding quality and CUDA-provider availability are **not** verified
  here; they depend on the real `buffalo_l` weights and host GPU.
* The 1:1 threshold is not yet calibrated.
* Embeddings are sensitive biometric data; retention/encryption/access-control
  policy is out of scope of this service and must be handled by the caller.
