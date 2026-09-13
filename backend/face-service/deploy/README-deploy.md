# Deploying InsightFace-for-openvela (user-level systemd)

> **Not executed in the implementation round.** This document is the checklist
> for the orchestrator to run after review. Do not SSH from here.

## 1. Prerequisites (verify, do not assume)

| # | Check | Command | Required |
|---|---|---|---|
| 1 | User linger on (survives logout/reboot) | `loginctl show-user $USER -p Linger` | `Linger=yes` |
| 2 | `uv` available | `$HOME/.local/bin/uv --version` | yes |
| 3 | Model weights present | `ls ~/.insightface/models/buffalo_l/` | `w600k_r50.onnx`, `det_10g.onnx`, … |
| 4 | Port free | `ss -ltnp \| grep :8010` | empty |
| 5 | No system unit used | (`/etc/systemd/system` not writable; we never need it) | — |

If linger is not `yes`, enable it once (already done for `bool` per the
orchestrator): `loginctl enable-linger $USER`.

## 2. Remote layout (convention)

```
/home/bool/deployment/InsightFace-for-openvela/   # this repo subtree
  .venv/                                          # created by uv sync --frozen
  pyproject.toml  uv.lock  src/  deploy/  README.md
  data/                                           # 0700, SQLite lives here
  logs/                                           # 0750 (journal is primary)
~/.config/face-service-openvela.env               # 0600, NON-secret config
~/.config/face-service-openvela.token             # 0600, SECRET
~/.config/systemd/user/InsightFace-for-openvela.service
```

## 3. One-time setup (no secret values ever printed)

```bash
# 3.1 internal token -- generate, never echo, never commit
openssl rand -hex 32 > ~/.config/face-service-openvela.token
chmod 600 ~/.config/face-service-openvela.token

# 3.2 env file from the public example (contains no secrets)
install -m 0600 /home/bool/deployment/InsightFace-for-openvela/.env.example \
                ~/.config/face-service-openvela.env
# edit it if needed; the example already points at the token file and
# sets FACE_SVC_AUTH_REQUIRED=true
```

> The token value must never appear in any log, report, commit or chat. Clients
> send it as the `X-Internal-Token` header.

Authentication is **fail-closed**: `FACE_SVC_AUTH_REQUIRED` defaults to `true`,
and because the bind host is non-loopback the service refuses to start without
auth enabled *and* a configured token. A misspelled boolean (e.g. `treu`) is a
startup error rather than a silent `false`, so a bad env file makes the unit
fail loudly (visible via `systemctl --user status` / `deploy.sh` health poll)
instead of exposing an unauthenticated API.

## 4. Deploy (idempotent)

```bash
cd /home/bool/deployment/InsightFace-for-openvela
./deploy/deploy.sh
```

`deploy.sh` performs, in order:

1. Verifies linger = yes (hard-fails otherwise), `uv` present, unit template
   present, service dir at `$HOME/deployment/InsightFace-for-openvela`.
2. Verifies the env file exists at 0600; if `FACE_SVC_AUTH_REQUIRED=true`,
   verifies the token file exists at 0600 (hard-fails with generation
   instructions otherwise).
3. `uv sync --frozen`.
4. Creates `data/` (0700) and `logs/` (0750).
5. Installs the unit to `~/.config/systemd/user/`.
6. `systemctl --user daemon-reload && systemctl --user enable --now`.
7. Polls `/v1/health` for up to 60 s and prints a **sanitized** summary
   (`status`, `model_loaded`, `model_version`, `library_revision`,
   `liveness.supported`) — never the token.
8. On any failure prints rollback commands.

## 5. Post-deploy verification checklist

```bash
B=http://10.3.6.163:8010            # bound intranet address
H='X-Internal-Token: <read from the 0600 file at use time>'

# 5.1 process + startup
systemctl --user status InsightFace-for-openvela
curl -sS $B/v1/health

# 5.2 extract is zero-write: note library_revision before/after, and that the
#     namespace echoed back was NOT created
curl -sS -X POST $B/v1/extract -H "$H" \
     -F image=@/tmp/fixture_a.png -F namespace=deploy-smoke
curl -sS $B/v1/namespaces/deploy-smoke/info -H "$H"   # expect 404

# 5.3 register -> 1:1 verify -> delete closed loop with SYNTHETIC fixtures
curl -sS -X POST $B/v1/namespaces/deploy-smoke/subjects -H "$H" \
     -F image=@/tmp/fixture_a.png -F subject_id=probe-a
curl -sS -X POST $B/v1/verify -H "$H" \
     -F image=@/tmp/fixture_a.png -F namespace=deploy-smoke -F subject_id=probe-a
curl -sS -X POST $B/v1/verify -H "$H" \
     -F image=@/tmp/fixture_b.png -F namespace=deploy-smoke -F subject_id=probe-a
     # expect matched=false (NOT a top-1 match, NOT SUBJECT_NOT_FOUND)
curl -sS -X DELETE $B/v1/namespaces/deploy-smoke/subjects/probe-a -H "$H"

# 5.4 no token -> 401
curl -sS -o /dev/null -w '%{http_code}\n' -X POST $B/v1/extract -F image=@/tmp/fixture_a.png

# 5.5 restart survival
systemctl --user restart InsightFace-for-openvela
sleep 3 && curl -sS $B/v1/health

# 5.6 reboot autostart: linger=yes + WantedBy=default.target start the unit
#     after reboot without login. Verify after the next maintenance window:
#     systemctl --user is-enabled InsightFace-for-openvela   # -> enabled

# 5.7 journal must show SANITIZED access logs only (no identity values):
#     route templates like /v1/namespaces/{namespace}/subjects/{subject_id},
#     and no raw uvicorn "GET /v1/namespaces/<real>/subjects/<real>" lines.
journalctl --user -u InsightFace-for-openvela -n 50 | grep -c 'face_service.access' || true
journalctl --user -u InsightFace-for-openvela -n 200 | grep 'deploy-smoke' || echo 'no identity values in journal'
```

Use only **synthetic/blank fixtures** for smoke tests. Do not upload real
biometric photos to any environment without an explicit retention/consent
decision.

## 6. systemd hardening trade-offs (per directive)

| Directive | Effect | Trade-off / why it is safe here |
|---|---|---|
| `NoNewPrivileges=true` | No setuid escalation | Service needs no privileges. |
| `PrivateTmp=true` | Private `/tmp` namespace | Service never uses `/tmp`. |
| `ProtectSystem=strict` | Whole FS read-only except listed paths | Requires `ReadWritePaths` for `data/`; venv/model reads unaffected. |
| `ProtectHome=read-only` | `$HOME` read-only | Needed because the venv and `~/.insightface` live in `$HOME`. Data writes are re-allowed via `ReadWritePaths`. |
| `ReadWritePaths=%h/deployment/InsightFace-for-openvela/data` | Re-allows SQLite writes | Only the isolated data dir is writable. |
| `ReadOnlyPaths=%h/.insightface %h/deployment/InsightFace-for-openvela` | Pins weights/code read-only | Model weights are reused, never modified. |
| `MemoryMax=4G`, `CPUQuota=200%` | Conservative caps | 24-core/62 GB host; inference is bursty. Raise if throughput needs it. |

`ProtectHome=true` would block reading `~/.insightface`; it is deliberately
**not** used — `ProtectHome=read-only` is the correct setting for this layout.

## 7. Liveness

Liveness detection is **not supported**. `buffalo_l` has no liveness model, and
the service never infers liveness from `det_score` or embedding similarity.
Every response carries `liveness: {supported: false, ...}`; an explicit
`require_liveness=true` request returns `501 LIVENESS_UNSUPPORTED`. Do not
represent this service as providing anti-spoofing.

## 8. Rollback

```bash
systemctl --user disable --now InsightFace-for-openvela
rm -f ~/.config/systemd/user/InsightFace-for-openvela.service
systemctl --user daemon-reload
# data/ is left in place; delete it only if a full reset is intended
```
