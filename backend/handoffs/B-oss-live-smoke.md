# B 真实 OSS 跨语言 smoke（root-only）——交付说明

## 1. 目的与边界
让根用**同一份私有 UTF-8 YAML** 驱动 Java 与 Python **两侧当前生产适配器**对真实阿里云 OSS 做
跨语言闭环验证。**OpenCode 侧从未联网真实 OSS**：本地只跑 `--dry-run`（两侧本地文件系统替身
共享同一 root）与单元/契约回归。

- Java 侧对象操作全部经 `OssStorageAdapter`；`OSS` 客户端复用**生产装配方法**
  `new OssProvidersConfig().ossClient(AliyunOssProperties, AppProperties)`（`OssProvidersConfig:46-72`），
  故 endpoint/region/credentials（含 STS）/连接与 socket 超时与生产完全一致；`finally` 中 `shutdown()`。
- Python 侧经**生产解析路径** `build_storage_port(DConfig.from_env(), environment=…, dev_dir=…)`
  （按 `MVP_D_STORAGE_PROVIDER` 选择，绝不静默回退），live → `AliyunOssStorage`，double → 同一工厂的替身。
- **未另写任何 SDK put/get/exists/delete 逻辑**；两侧都只调用上述生产实现。

## 2. 根的运行命令（非秘密参数）
```bash
# 本地干跑（无需任何凭据、不联网；两进程两语言完整闭环 + 精确清理 + 交叉确认不存在）
backend/tests/oss-live-smoke/run-oss-live-smoke.sh --dry-run

# 真实 OSS 闭环（仅根执行；四道门缺一即拒绝）
OSS_LIVE_SMOKE=true backend/tests/oss-live-smoke/run-oss-live-smoke.sh \
    --live --config /abs/path/OUTSIDE/worktree/application-local.yml \
    [--env dev] [--content-bytes 256] [--skip-build]
```
非秘密参数：`--live`、`--config <绝对路径，必须在工作树之外>`、`--env <对象键首段，默认 dev>`、
`--content-bytes <合成对象字节数，默认 256>`、`--skip-build`（复用已编译的 test-classes 与
`.coordination/B-work/oss-live-smoke/cp.txt`）；驱动级 opt-in 环境变量 `OSS_LIVE_SMOKE=true`。
**秘密从不作为参数传入**：凭据只存在于根的私有 YAML 中，由驱动在进程内 `eval` 导出为 Python 侧
环境变量（`MVP_A_STORAGE_OSS_*`），**绝不落盘、绝不打印、绝不写入工作树**。

前置：`mvp-b-pg` 无需启动（本工具不连数据库）；Java 侧需要 `mvn test-compile` 产物（驱动会自动构建，
除非 `--skip-build`）；Python 侧需要 `backend/worker-python/.venv`（含 `oss2`）。

## 3. 四道门（`--live`；任一不满足立即退出码 2，绝不静默通过）
1. 显式 `--live`（与 `--dry-run` 互斥）；
2. 环境变量 `OSS_LIVE_SMOKE=true`（驱动**绝不**自动设置）；
3. `--config` 是可读文件、**不在工作树内**、`app.storage.provider=aliyun`、必填键齐备
   （校验只输出**键名**）；
4. 两侧各自的三重 opt-in：Java `-Dapp.oss.live-smoke=true`、Python `MVP_OSS_LIVE_SMOKE=true`
   （门 1-3 通过后由驱动代为传递），加上 provider 为真实值与凭据非空。
`--dry-run` 时若检测到 `OSS_LIVE_SMOKE=true` 也会拒绝（避免模式混淆）；两侧在 `--mode double`
下发现 live opt-in 为真同样 abort（`step=double-mode-refuses-live-opt-in`）。

## 4. 闭环序列与清理保证
`java write keyA` → `python verify keyA`（exists+get+**逐字节**比对）→ `python write keyB` →
`java verify keyB` → `java public-url-probe keyA`（未鉴权 GET，断言状态 **!= 200**；仅 live，
dry-run 跳过 `reason=no-live-bucket`）→ **EXIT trap 清理**：
`java delete keyA`、`python delete keyB`，随后**两侧交叉确认两个键都不存在**（4 次 confirm-absent）。
- 键形态固定 `<env>/assessment_result/<uuid>`，由驱动随机生成，**合成、无用户数据**；
  两侧都用同一正则校验并拒绝 `..`、首/尾斜杠、段数≠3、purpose 非 `assessment_result`、UUID 形态错误。
- 删除**只**针对这两个精确键；**绝不** list、**绝不**批量/前缀删除、**绝不**任何桶级操作、
  **绝不**触碰任何既有对象。
- 清理在 `trap EXIT INT TERM` 中执行，**无论前面阶段成败都会跑**；清理未确认时脚本**退出码非 0**
  （即使所有阶段都通过），并把两个完整键写入 `0600` 文件（`.coordination/B-work/oss-live-smoke/`，
  git 忽略），stdout 只给该路径与 keyDigest。
- dry-run 的共享 root 建在 `.coordination/B-work/`（git 忽略）下并于结束时删除，**不用 /tmp**。

## 5. 输出纪律（两侧 + 驱动）
只允许三种行：契约 `[oss-smoke] side=… mode=… phase=… step=… result=… reason=… code=… requestId=…
bytes=… sha256=<12hex> keyDigest=<12hex> purpose=assessment_result`、净化后的
`[oss-smoke-error] … exception=<类名> message=<已净化>`、以及不含任何值的
`[oss-smoke-note] side=… note=<token>`。**绝不**输出 AK/SK/STS、bucket 名、endpoint、region、
完整 objectKey 或对象内容；`sha256`/`keyDigest` 均只取前 12 位十六进制。
`reason` 为固定 token（含 orchestrator 裁定的 `object-missing`＝verify 阶段对象不存在；
`absent-confirmed` **只**用于 confirm-absent 的成功语义）。`step` 是信息性诊断字段、
不属跨语言契约（唯一例外 `public-url-status-<n>`，HTTP 状态码非秘密且任务要求输出）。
退出码：Java `0`=ok/skipped、`1`=阶段失败/适配器异常、`2`=用法/门/非法键/配置错误；
Python `0`/`1`；驱动只要求"失败必非 0"。
**已披露**：完整 objectKey 会作为子进程 argv 出现（同机同用户可见）。它是本次随机生成的合成键、
不含任何用户数据，非秘密；bucket 与凭据从不入 argv。

## 6. 配置来源的不对称与拼写对称（如实记录）
- **Java** 用 snakeyaml（2.4，已在测试 classpath）以**显式 UTF-8** `Reader` 读私有 YAML
  （严禁 ISO-8859-1——这是上一轮短信中文签名乱码的同类教训）；支持嵌套与扁平点号两种形状。
- **Python** 只读环境变量：worker venv **没有 pyyaml**，为一个 root-only smoke 给生产依赖树新增
  依赖不合理；env 本就是它的生产配置路径（`dconfig`）。翻译由驱动调用**系统 python3**
  （已确认 pyyaml 6.0.1）完成：`backend/tests/support/oss-smoke-config.py`，`--check` 只输出键名，
  `--emit shell` 的输出只被 `eval` 捕获。
- **拼写严格对称**：两侧都**只**接受 Spring 规范 kebab-case（`access-key-id` 等）与扁平点号键；
  camelCase/snake_case/UPPER **一律响亮拒绝并列出缺失键名**。orchestrator 明确**不**为假设性的
  拼写差异加投机式 relaxed binding——半实现会造成"Python 侧拿到凭据而 Java 侧中止"的半成功危害，
  比统一拒绝更糟。

## 7. 本地已验证（orchestrator 亲自执行，全部不联网）
- **驱动级 dry-run 全绿**：`RESULT=PASS failures=0 cleanup=confirmed`，五阶段全部 ok
  （`public-url-probe` 按设计 skipped），**跨语言 sha256 完全一致**（Java 写→Python 校验、
  Python 写→Java 校验两个方向同为 `d556219a8f1c`），无残留 root。
- **精确篡改矩阵**（按 key 定位文件，非 `find|head`）：A 同语言篡改、B 同语言篡改、
  **C Java 写→篡改→Python 校验**、**D Python 写→篡改→Java 校验** 四例全部
  `result=fail reason=sha-mismatch`；对照 E/F 未篡改跨语言校验 `result=ok`；
  G 截断到 100 字节 → `result=fail reason=bytes-mismatch`（长度与内容分别校验）。
- **verify 缺失对象**：两侧均 `result=fail reason=object-missing`、exit 1（无假成功）；
  `confirm-absent` 对同一缺失键两侧均 `result=ok reason=absent-confirmed`。
- **非法键拒绝**：`grant_face` purpose、`..` 路径穿越、非 UUID 三例两侧均 rc≠0 且**创建对象数 0**。
- **门测试（全部无网络）**：`--live --dry-run` 互斥、缺 `OSS_LIVE_SMOKE`、dry-run+opt-in、
  config 在工作树内、config 不可读 ⇒ 均 rc=2；翻译器 provider≠aliyun ⇒ rc=3、缺 bucket ⇒ rc=4
  且只报键名、stderr 泄漏 0；camelCase/snake_case ⇒ rc=4 并列出规范键名；嵌套与扁平点号 ⇒ rc=0。
- **权威跨语言向量**：两侧硬编码同一期望值，`seed=b-oss-smoke-vector` 的 256/64/1 字节 sha256
  分别为 `0e46beb4…4e32` / `f3a94291…58fd` / `0a43b22d…cd97a`，keyDigest 示例 `6ca2e86b3621`；
  两侧实测逐字一致（任一侧算法偏离即测试失败）。
- **泄漏扫描**：驱动完整日志中假桶名/假 AK/假 SK/`aliyuncs` 出现 **0** 次、完整 UUID 键 **0** 次；
  `bucket` 一词仅出现于 `reason=no-live-bucket` token 与驱动自己的说明文字。
- **判别力负向证明**（两道各自完成并已还原、无探针残留）：Java——`smokeBytes` 偏移一轮 ⇒ 向量测试失败、
  去掉净化 ⇒ `sanitizationRemovesSecrets` 失败、放宽 purpose ⇒ `invalidObjectKeysRejected` 失败；
  Python——同类三项分别 3 FAIL / `AssertionError: leaked: fake-bucket-do-not-use` / 参数化用例 FAIL。
- **测试数字**：Java 全量 **606 run / 0 failures / 0 errors**（基线 590 + 新增 16，BUILD SUCCESS）；
  Python 全量 **385 passed**（基线 352 + 新增 33）；定向 Java 32/0/0、Python 90 passed；
  `test-compile` rc=0、`compileall`/`py_compile` rc=0；`55432` 引用 0；ephemeral 库已清理。
- **生产代码零改动**：`backend/web-java/src/main/**`、`backend/worker-python/src/**`、`pom.xml`、
  `application.yml`、依赖清单全部 diff 为 **0 文件**；worker venv 仍**无 pyyaml**（未新增依赖）。

## 8. 只有根能验证的（如实声明未验证项）
1. **真实 OSS 闭环**：live 模式下 Java `OssStorageAdapter` 与 Python `AliyunOssStorage` 对真实桶的
   put/get/exists/delete、真实 V4 签名被接受、桶权限与生命周期、跨语言真机互通——OpenCode 侧
   **从未执行**（live 分支只经编译期与注入假存储/桩探测验证）。
2. **`public-url-probe` 对真实桶的状态码**未取得（dry-run 按设计跳过）。若真实返回 200，
   工具会报 `result=fail reason=public-url-status-200`——这是真实安全发现，须如实上报而非忽略。
3. Java live 分支中 `AppProperties(null, null, new AppProperties.Storage(null, bucket), …)` 的构造
   满足生产的 bucket 一致性校验，但该路径未在真实配置下运行过。
4. 两侧 `step` token 词表不同（裁定为信息性字段，驱动只解析 `result=`）。

## 9. 新增文件（生产代码零改动）
- `backend/tests/oss-live-smoke/run-oss-live-smoke.sh`（驱动：四道门、键生成、阶段编排、EXIT trap 清理）
- `backend/tests/support/oss-smoke-config.py`（私有 UTF-8 YAML → Python env 翻译器；`--check` 只给键名）
- `backend/web-java/src/test/java/cn/yuanxin/mvp/web/storage/OssLiveSmoke.java`（纯逻辑 harness）
- `…/storage/OssLiveSmokeRunner.java`（`main`；不以 Test/IT 结尾 ⇒ surefire 绝不执行）
- `…/storage/OssLiveSmokeTest.java`（16 项回归）
- `backend/worker-python/tests/oss_live_smoke.py`（CLI 阶段运行器；不以 `test_` 开头 ⇒ pytest 不收集）
- `backend/worker-python/tests/test_oss_live_smoke.py`（33 项回归）
共享契约与 orchestrator 裁决见 `.coordination/B-work/oss-live-smoke/contract.md`（git 忽略目录）。

## 10. 根的真实 OSS 闭环验证结果（根侧执行，绑定提交 `ede19b5`）
**执行方＝根**（非 OpenCode；本环境从未联网真实 OSS）。**被验证提交＝`ede19b5c7a713626ae70a953afcac6deadef36fa`**。
**结果＝PASS**，逐项如下（按根回报如实转录；**不含** bucket、endpoint、完整 objectKey、凭据与对象内容）：
1. Java 生产适配器写入后，Python 生产适配器 `exists`/`get` **逐字节校验成功**；
2. Python 生产适配器写入后，Java 生产适配器 `exists`/`get` **逐字节校验成功**；
3. 两侧 **256 字节**对象摘要**一致**；
4. **未签名公网探测返回 403**（即 `public-url-probe` 断言"状态 != 200"成立 ⇒ 对象未公开可读，
   符合"私有桶、无公开 URL"的既定要求）；
5. `finally` 精确删除本次生成的**两个随机合成对象**，Java 与 Python **双方确认均不存在**，
   `cleanup=confirmed`。
**这闭合了第 8 节的未验证项 1 与 2**（真实 OSS 闭环、真实签名被接受、桶权限、`public-url-probe`
真实状态码）。仍未由任何一方验证的：真实 STS 临时凭据路径（根使用的是长期 AK/SK 还是 STS 未回报）、
多实例并发下的清理、以及桶生命周期/版本控制策略与本工具的交互。
**注**：本节证据绑定 `ede19b5`。其后若代码变更（例如 endpoint 拆分），真实闭环须由根在新 SHA 上重跑，
本节不得被引用为新 SHA 的证据。
