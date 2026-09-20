# 医疗云后端怎么调 AI 服务（K7 云台）

设备没有屏幕和登录。流程是：

```text
云台拍照测肤
  → 图像算法产出检测 JSON
  → 医疗云后端（用服务密钥）把 JSON 交给 RAG
  → RAG 返回中文方案文本
  → 后端自行决定如何给云台（例如 TTS，那是后端的事）
用户再追问
  → 后端先把语音转成文字（ASR，不是 RAG 的工作）
  → 后端把这段文字发给 RAG 问答接口（带上上次的 continuation_state）
  → RAG 结合刚才的检测结果返回中文回答
  → 后端再自行转成语音播给云台
```

RAG **只收发文字**。语音识别、语音合成都不是本服务的接口能力。

终端用户**无需登录**。身份用可选的 `device_id`（建议传云台编号），没有则记为匿名普通客户。鉴权只有后端的 `X-API-Key`。

AI 负责人把 **Base URL** 和密钥私下发给后端。默认 `http://<AI机器IP>:7861`。  
`X-Service-Name` 固定 `medical-platform`。不要带顾客 `Authorization` / `Cookie`。

---

## 接口一览

| 谁做什么 | 调哪个接口 |
|---|---|
| 把测肤 JSON 交给 RAG，拿中文方案文本 | `POST /internal/v1/weijing/reports/assess` |
| 用户追问（已转成文字的问题） | `POST /internal/v1/ai/responses`，**原样带回**评估接口返回的 `continuation_state` |
| 存活 / 能否接单 | `GET /internal/health/live` 、 `GET /internal/health/ready`（不用密钥） |

本仓库网页问答是给人用浏览器点的，**云台用不到**。

---

## 1. 提交检测 JSON

**`POST /internal/v1/weijing/reports/assess`**

Header：

| Header | 填什么 |
|---|---|
| `X-Service-Name` | `medical-platform` |
| `X-API-Key` | 私下给的密钥 |
| `X-Request-Id` | 本次请求 ID（8～128 位字母数字或 `._:-`） |
| `Idempotency-Key` | 每次新请求换新的 |
| `X-Protocol-Version` | `1.0` |
| `traceparent` | 如 `00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01` |
| `Accept` / `Content-Type` | `application/json` |

请求体至少要有 `regions`。建议带 `device_id`。不要传网页登录用户。

```bash
curl -sS -i -X POST "<BASE_URL>/internal/v1/weijing/reports/assess" \
  -H "X-Service-Name: medical-platform" \
  -H "X-API-Key: <API_KEY>" \
  -H "X-Request-Id: req-20260913-0001" \
  -H "Idempotency-Key: idem-20260913-0001" \
  -H "X-Protocol-Version: 1.0" \
  -H "traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01" \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  --data '{
    "device_id": "k7-01",
    "report_id": "WJ-TEST-001",
    "algorithm_version": "2.0",
    "assessed_at": "2026-09-13T15:00:00+08:00",
    "regions": {
      "F": {"O": {"score": 40, "label": "较明显"}, "P": {"score": 62, "label": "轻度"}, "D": {"score": 81, "label": "未见明显"}},
      "L": {"O": {"score": 35, "label": "较明显"}, "P": {"score": 28, "label": "较明显"}, "D": {"score": 55, "label": "中度"}},
      "R": {"O": {"score": 70, "label": "轻度"}, "P": {"score": 82, "label": "未见明显"}, "D": {"score": 50, "label": "中度"}},
      "C": {"O": {"score": 20, "label": "显著"}, "P": {"score": 50, "label": "中度"}, "D": {"score": 65, "label": "轻度"}}
    }
  }'
```

区：`F` 额、`L` 左脸、`R` 右脸、`C` 下巴。项：`O` 油脂、`P` 色斑、`D` 干燥性细纹。

成功 200 后后端：

- 使用 **`spoken_text`**（普通中文方案正文）。若要给云台出声，由**后端做 TTS**，不要把音频发给 RAG。
- 把 **`continuation_state`** 存到这台设备会话里，追问时原样带回。不要改里面的字段。

---

## 2. 追问（只传文字）

**`POST /internal/v1/ai/responses`**

同一套 Header（`Accept: application/json`）。  
`input.text` 必须是**已经转成文字的用户问题**。语音转文字由后端/云台完成，本接口不接收音频、不负责 ASR。再附上评估时拿到的 `continuation_state`。

```bash
curl -sS -i -X POST "<BASE_URL>/internal/v1/ai/responses" \
  -H "X-Service-Name: medical-platform" \
  -H "X-API-Key: <API_KEY>" \
  -H "X-Request-Id: req-20260913-0002" \
  -H "Idempotency-Key: idem-20260913-0002" \
  -H "X-Protocol-Version: 1.0" \
  -H "traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01" \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  --data '{
    "protocol_version": "1.0",
    "request_id": "req-20260913-0002",
    "use_case": "APP_AGENT_CONVERSATION",
    "input": {"text": "左脸为什么用这个成分？"},
    "continuation_state": {"weijing_assessment_id": "<评估返回的id>", "weijing_owner_id": "device:k7-01"}
  }'
```

`X-Request-Id` 必须等于正文 `request_id`，每次换新。

成功后使用 **`answer.text`**（中文回答）。若要出声，同样由后端 TTS。若响应里还有 `continuation_state`，下次继续原样带回。

流式用 `POST /internal/v1/ai/responses:stream`，`Accept: text/event-stream`，正文相同。

---

## 3. 密钥

仓库根目录 `.env`（不要提交）：

```text
APP_INTERNAL_AI_API_KEYS=自己生成的一串随机字符
```

---

## 4. 失败

非 2xx 为 `application/problem+json`，用 `code` 分支。缺 Header / JSON 无效 / 没有 `regions` → `AI_REQUEST_INVALID`；密钥不对 → `AI_UNAUTHORIZED`；知识库未就绪 → `AI_SERVICE_UNAVAILABLE`。
