# T13 payload_hash 与跨语言规范化 JSON 规范（canonicalization）

状态：A 包公共契约（Java Web 与 Python Worker 必须实现同一规范）。
参考实现：`scripts/jcs.py`（Python 3.12，零依赖）；共享向量：
`samples/canonicalization/vectors.json`。**Java 与 Python 的测试都必须复现
这些向量**（A 验收项，decisions #11）。

## 1. 算法

`payload_hash = SHA-256( JCS( canonicalObject ) )`，输出**小写十六进制**。

- **JCS = RFC 8785 JSON Canonicalization Scheme**：
  - 对象成员按键的 **UTF-16 code unit 序**升序排列（ES6 排序，非按码点、
    非按 UTF-8 字节）；
  - 序列化无任何空白：`{"a":1,"b":{"c":null},"d":["x"]}`；
  - 数组**保持原序**（顺序有含义的数组绝不排序）；
  - 字符串按 ES6 `JSON.stringify` 最小转义（`"`、`\`、`\b`、`\t`、`\n`、
    `\f`、`\r`、控制字符 `\u00XX`），其余字符（含中文等非 ASCII）**原样
    UTF-8 输出**；
  - 数字按 ECMAScript `Number::toString(10)`：有限数；`-0 → "0"`；整值且
    |v| < 1e21 的双精度 → 规范十进制（无 `+`、无前导零、无多余 `.0`）；
    其余按最短往返数字 + 小数点位置 n 选形（`k ≤ n ≤ 21` 补零整数、
    `0 < n ≤ 21` 小数点内插、`-6 < n ≤ 0` 用 `0.0…d`、否则 `e+XX`/`e-XX`
    指数，指数无前导零，如 `1e-4 → "0.0001"`、`1e-7 → "1e-7"`、
    `1e21 → "1e+21"`）；
  - **禁止重复 JSON 键**：输入含重复键即错误（不是覆盖），必须拒绝；
  - NaN/Infinity、孤立代理对（lone surrogates）拒绝。
- SHA-256 摘要输入是上述 canonical 字节序列的 **UTF-8 编码**，不带结尾换行。

### bigint-as-string 与数字序列化的关系

本项目的计数/revision/seq（bigint）在 JSON 中**一律以字符串传输**
（`^(0|[1-9][0-9]*)$`），因此 JCS 的数字序列化规则**只**适用于
`schema_version` 这类真正的 JSON 整数和协议明确允许的小数。字符串带引号，
按字符串规范化——`"42"` 与 `42` 是**不同**的 canonical 输入，哈希不同；
这保证 Java（Long→String）与 Python（int→str）永远不会因数字表示差异
碰撞或分叉。

## 2. canonicalObject 的组装（幂等 payload_hash 的输入）

规范来源：DD 3.3。计算 T13 `payload_hash` 前，服务端把请求组装成如下
canonical 对象（随后整体做第 1 节 JCS + SHA-256）：

1. **operation**：稳定的逻辑操作标识（如 `m1a01.CreateMemberAccessGrant`），
   不是 HTTP requestId。
2. **路径参数**：按 OpenAPI 路径模板的参数名放入（如
   `{"grantId": "..."}`、`{"taskId": "...", "photoVersion": "3"}`），值用
   服务端解析后的规范形式（UUID 小写文本、bigint 十进制字符串）。
3. **语义字段**：请求体/query 中参与业务语义的字段（camelCase 字段名与
   OpenAPI 一致）。
   - **缺省值先展开**：所有有默认语义的可选字段必须在组装时补齐为显式值
     （包括 `null`），再进摘要——“带缺省”和“展开后”的请求必须得到同一哈希
     （见向量 `defaults-expanded-equal-pair-a/b`）。
   - **有序数组不排序**：清单类字段（如 `replacedViews:
     ["front","left","right"]`）是协议有序数组，保持原序（向量
     `array-order-significant-*`）；只有文档明确“集合按协议排序”的字段
     才先按该协议排序。
4. **multipart 图片**：不包含图片字节本身；放入
   `{"imageParts": [{"part": "front", "sha256": "<该 part 原始字节的
   SHA-256 小写 hex>"}, ...]}`——part 名（`metadata` 之外：`face`、
   `front`、`left`、`right`）与逐 part 内容摘要按 part 名字典序排列。
   `metadata` part 的 JSON 作为语义字段（第 3 条）参与。
5. **排除项（可变传输头一律不进摘要）**：`Authorization`、`X-Request-Id`、
   `User-Agent`、`Accept*`、`Date`、multipart 边界、part 顺序、HTTP 传输
   压缩、服务端接收时间等。只排除传输层：Idempotency-Key 本身是 T13 唯一键
   的组成部分，不重复放进 canonicalObject。

同一逻辑请求（同 principal、同 operation、同键、同 canonical 内容）在
Java 与 Python 两侧必须得到**字节相同**的 canonicalObject 序列化与同一
SHA-256；不同语义（哪怕只差一个字段值）**不得碰撞**（向量
`near-collision-closure-final-count-3/4` 演示最小语义差异 → 不同哈希）。

## 3. 实现与验收要求

- 两侧不得自行“近似”实现：以 RFC 8785 + 本文件为准，单元测试必须
  逐向量复现 `vectors.json`（键名对上、`expected_sha256` 相等）。
- Python 参考：`python3 scripts/jcs.py hash <file.json>`；
  `scripts/validate_samples.py` 会重算全部向量并校验全部样例。
- **RFC 8785 一致性自测**：`python3 scripts/jcs.py selftest` 断言 23 组
  ES6 `Number::toString` 权威数对（含 0.5、0.000123、1e-4、1e-7、1e21、
  1e23、DBL_MIN/DBL_MAX 等小数点定位与指数形式边界）与结构规则；
  Java 侧 `JcsVectorsTest#es6NumberToString` 用同一清单锁定两侧行为。
  （2026-09-10：修复了参考实现 1e-4≤|v|<1 区间的历史缺陷并重新生成向量，
  现两侧均为标准 ES6 语义；旧向量哈希若出现在任何存储介质中一律作废。）
- Java 侧建议：自实现 ~150 行序列化（Jackson 解析 + 显式写出）或用成熟
  JCS 库，但**以向量测试锁定行为**（特别是 UTF-16 键排序与中文原样输出）。
- 解析输入时拒绝重复键（Jackson `STRICT_DUPLICATE_DETECTION`；Python 见
  `jcs.load_strict`）。
- bigint 一律字符串进摘要（本项目无 JSON bigint 数字）；`schema_version`
  等小整数按 JCS 数字规则序列化。

## 4. 与其他哈希的关系

- T08 `care_records.payload_hash`、媒体 part 的 `content_hash` 都用
  SHA-256 小写 hex；媒体 content_hash 是**原始字节**摘要，不走 JCS。
- T13 摘要域是 canonicalObject（本节），与 requestId 无关；更换
  installation 之外的照片/业务内容必须使用新的 Idempotency-Key，旧键同
  canonical 内容重放返回原结果。
