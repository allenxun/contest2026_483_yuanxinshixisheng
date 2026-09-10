# multipart-metadata 样例说明

两个文件分别是 M1-A01、M3-A01 `multipart/form-data` 请求中 **`metadata`
part 的完整 JSON**（`Content-Type: application/json`，camelCase），已通过
`scripts/validate_samples.py` 对 OpenAPI `M1A01Metadata` / `M3A01Metadata`
的校验。图片 part 的命名规则如下（完整布局也是契约的一部分，二进制内容
不在样例内）：

## M1-A01 `POST /api/v1/member-access-grants`

| part 名 | Content-Type | 说明 |
|---|---|---|
| `metadata` | application/json | `m1a01-metadata.json` 内容 |
| `face` | image/*（实际格式校验） | 当前人脸采集图片，单图 ≤10MiB 初值 |

- 客户端去重字段：请求头 `Idempotency-Key`（T13 键）+ `capture.captureId`、
  `capture.clientContinuityId`（本轮采集/连续性关联，参与 payload_hash 的
  canonicalObject）。更换人脸必须换新 `Idempotency-Key`。
- payload_hash 的图片部分 = part 名 `face` + 原始字节 SHA-256
  （见 `canonicalization.md` 第 2.4 节）。

## M3-A01 `POST /api/v1/skin-assessment-tasks`

| part 名 | Content-Type | 说明 |
|---|---|---|
| `metadata` | application/json | `m3a01-metadata.json` 内容 |
| `front` | image/* | 正面视角 |
| `left` | image/* | 左侧视角 |
| `right` | image/* | 右侧视角 |

- 三图合计 ≤32MiB 开发初值；三 part **必须齐备**（缺失不受理、不切当前
  任务指针）。
- 客户端去重字段：`Idempotency-Key` 头 + `captureSessionId`（云台本轮采集
  会话）+ `photoVersion`；同键同 canonical 内容重放返回原 taskId。
- M3-A02 复用 front/left/right part 名，但仅携带被更换视角（清单在
  `metadata.replacedViews`）。
