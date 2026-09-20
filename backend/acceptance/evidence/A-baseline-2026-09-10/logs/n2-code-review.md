# N2 诊断列消费点分类检视（file:line + 片段 + 读/写 + 分类）

命中 23 处；待人工复核 9 处；含客户端投影=True。
分类规则：SystemEchoController→客户端投影(read)；worker complete/loop→写入；其余机械不可判定→待人工复核（本子项降 INFO）。

| 文件:行 | 代码片段 | 读/写 | 分类 | 备注 |
|---|---|---|---|---|
| web-java/src/main/java/cn/yuanxin/mvp/web/system/SystemEchoController.java:89 | `String leaseRevision, String finishedAt, Object lastError) {` | read | 客户端投影 | echo GET 投影 data.lastError（关联已确认 A 缺陷） |
| web-java/src/main/java/cn/yuanxin/mvp/web/system/SystemEchoController.java:153 | `+ " last_error::text AS last_error"` | read | 客户端投影 | echo GET 投影 data.lastError（关联已确认 A 缺陷） |
| web-java/src/main/java/cn/yuanxin/mvp/web/system/SystemEchoController.java:162 | `parseError(rs.getString("last_error"))),` | read | 客户端投影 | echo GET 投影 data.lastError（关联已确认 A 缺陷） |
| web-java/src/main/java/cn/yuanxin/mvp/web/media/MediaService.java:21 | `* pending → (StoragePort 写入 + 校验) → available；失败路径 state=failed + last_error。` | review | 其他 | 待人工复核 |
| web-java/src/main/java/cn/yuanxin/mvp/web/media/MediaService.java:96 | `+ " storage_metadata = ?::jsonb, last_error = NULL, updated_at = now()"` | review | 其他 | 待人工复核 |
| web-java/src/main/java/cn/yuanxin/mvp/web/media/MediaService.java:106 | `/** 失败路径：pending → failed + 可诊断 last_error（不含供应商密钥级细节）。 */` | review | 其他 | 待人工复核 |
| web-java/src/main/java/cn/yuanxin/mvp/web/media/MediaService.java:115 | `jdbc.update("UPDATE media_objects SET state = 'failed', last_error = ?::jsonb,"` | review | 其他 | 待人工复核 |
| web-java/src/main/java/cn/yuanxin/mvp/web/media/MediaIntakeService.java:54 | `* 校验实际格式/大小后标 available。校验失败 → failed + last_error 并抛出。` | review | 其他 | 待人工复核 |
| worker-python/src/mvp_worker/runtime/complete.py:7 | `last_error；否则 failed。守卫同代次。` | write | 写入（worker 诊断） | failed/last_error 写入路径 |
| worker-python/src/mvp_worker/runtime/complete.py:12 | `last_error JSON（snake_case）：{"code","message","retryable","retry_after_seconds"?}。` | write | 写入（worker 诊断） | failed/last_error 写入路径 |
| worker-python/src/mvp_worker/runtime/complete.py:36 | `last_error = NULL,` | write | 写入（worker 诊断） | failed/last_error 写入路径 |
| worker-python/src/mvp_worker/runtime/complete.py:50 | `last_error = CAST(:last_error AS jsonb),` | write | 写入（worker 诊断） | failed/last_error 写入路径 |
| worker-python/src/mvp_worker/runtime/complete.py:62 | `last_error = CAST(:last_error AS jsonb),` | write | 写入（worker 诊断） | failed/last_error 写入路径 |
| worker-python/src/mvp_worker/runtime/complete.py:87 | `def make_last_error(` | write | 写入（worker 诊断） | failed/last_error 写入路径 |
| worker-python/src/mvp_worker/runtime/complete.py:147 | `last_error = make_last_error(` | write | 写入（worker 诊断） | failed/last_error 写入路径 |
| worker-python/src/mvp_worker/runtime/complete.py:153 | `last_error = make_last_error(code, message, retryable=False)` | write | 写入（worker 诊断） | failed/last_error 写入路径 |
| worker-python/src/mvp_worker/runtime/complete.py:161 | `"last_error": last_error,` | write | 写入（worker 诊断） | failed/last_error 写入路径 |
| worker-python/src/mvp_worker/runtime/complete.py:180 | `last_error = make_last_error(reason_code, message, retryable=False)` | write | 写入（worker 诊断） | failed/last_error 写入路径 |
| worker-python/src/mvp_worker/runtime/complete.py:188 | `"last_error": last_error,` | write | 写入（worker 诊断） | failed/last_error 写入路径 |
| worker-python/src/mvp_worker/runtime/expire.py:9 | `last_error；否则旧领取者过期后任务被无限重放。两条 UPDATE 各自带` | review | 其他 | 待人工复核 |
| worker-python/src/mvp_worker/runtime/expire.py:27 | `last_error = jsonb_build_object(` | review | 其他 | 待人工复核 |
| worker-python/src/mvp_worker/runtime/expire.py:75 | `last_error = jsonb_build_object(` | review | 其他 | 待人工复核 |
| worker-python/src/mvp_worker/media/repository.py:13 | `last_error, created_at, updated_at` | review | 其他 | 待人工复核 |
