# N2 诊断消费点人工逐项复核（当前 SHA f6e500e）

共 10 项（9 处待复核 + echo 新投影路径）；逐项：当前 file:line、片段、读/写、使用方式、脱敏/大小依据、判定。

| 文件:行 | 代码片段 | 使用方式 | 判定 | 依据 |
|---|---|---|---|---|
| web-java/src/main/java/cn/yuanxin/mvp/web/media/MediaService.java:21 | `* pending → (StoragePort 写入 + 校验) → available；失败路径 state=failed + last_error。` | 内部诊断写入说明（注释） | **合规** | 仅文档描述；明确写诊断用途，无客户端投影 |
| web-java/src/main/java/cn/yuanxin/mvp/web/media/MediaService.java:96 | `+ " storage_metadata = ?::jsonb, last_error = NULL, updated_at = now()"` | 诊断写入（成功时清除内部诊断） | **合规** | available 成功路径清空诊断；无外部读取方 |
| web-java/src/main/java/cn/yuanxin/mvp/web/media/MediaService.java:106 | `/** 失败路径：pending → failed + 可诊断 last_error（不含供应商密钥级细节）。 */` | 注释（脱敏边界声明） | **合规** | 显式声明不含密钥级细节；写入值为 ErrorCode.name+message |
| web-java/src/main/java/cn/yuanxin/mvp/web/media/MediaService.java:115 | `jdbc.update("UPDATE media_objects SET state = 'failed', last_error = ?::jsonb,"` | 内部诊断写入（失败路径） | **合规** | media last_error 无任何对外端点投影；MediaController 仅返回 content |
| web-java/src/main/java/cn/yuanxin/mvp/web/media/MediaIntakeService.java:54 | `* 校验实际格式/大小后标 available。校验失败 → failed + last_error 并抛出。` | 注释（写入边界说明） | **合规** | 受理失败诊断写入说明，非业务决策 |
| worker-python/src/mvp_worker/runtime/expire.py:9 | `last_error；否则旧领取者过期后任务被无限重放。两条 UPDATE 各自带` | 注释（重试上限语义） | **合规** | 说明终态诊断用途；代次守护条件更新 |
| worker-python/src/mvp_worker/runtime/expire.py:28 | `'code', 'RETRY_LIMIT_EXCEEDED',` | 内部诊断写入（回收触顶） | **合规** | code 常量+固定 message；echo 投影现仅映射为 closed enum，不外发原始 code |
| worker-python/src/mvp_worker/runtime/expire.py:77 | `'message', 'graceful release at attempt ceiling',` | 内部诊断写入（停机释放触顶） | **合规** | 同上；固定文本，无动态敏感内容 |
| worker-python/src/mvp_worker/media/repository.py:13 | `last_error, created_at, updated_at` | 内部读取（列清单） | **合规** | 读入 MediaObject 供内部状态判断；未用于业务决策或跨服务协议、不对外投影 |
| web-java/src/main/java/cn/yuanxin/mvp/web/system/SystemEchoController.java:94 | `EchoJobLastError lastError) {` | 客户端投影（closed enum 映射） | **合规** | lastError 仅投影 {reason 封闭枚举, retryable bool}；原始 code/message 不外发（RV-2/3 实测） |
