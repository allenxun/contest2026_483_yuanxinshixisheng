# N2 诊断消费点人工逐项复核（A SHA f6e500e）

审核人：E 实施代理；核验人：oracle round-9；A SHA=f6e500e。

> 本文件为**预写审查结论 + 片段定位存在性检查（非自动代码审查）**；实质判定依据 = 人工逐项复核记录 + oracle 第九轮核验。
共 10 行（9 处待复核 + echo 新投影路径）。

| 文件:行 | 代码片段 | 使用方式 | 审核人 | 核验人 | 判定 | 依据 |
|---|---|---|---|---|---|---|
| web-java/src/main/java/cn/yuanxin/mvp/web/media/MediaService.java:21 | `* pending → (StoragePort 写入 + 校验) → available；失败路径 state=failed + last_error。` | 内部诊断写入说明（注释） | E 实施代理 | oracle round-9 | **合规** | 仅文档描述；明确写诊断用途，无客户端投影 |
| web-java/src/main/java/cn/yuanxin/mvp/web/media/MediaService.java:96 | `+ " storage_metadata = ?::jsonb, last_error = NULL, updated_at = now()"` | 诊断写入（成功时清除内部诊断） | E 实施代理 | oracle round-9 | **合规** | available 成功路径清空诊断；无外部读取方 |
| web-java/src/main/java/cn/yuanxin/mvp/web/media/MediaService.java:106 | `/** 失败路径：pending → failed + 可诊断 last_error（不含供应商密钥级细节）。 */` | 注释（脱敏边界声明） | E 实施代理 | oracle round-9 | **合规** | 显式声明不含密钥级细节；写入值为 ErrorCode.name+message |
| web-java/src/main/java/cn/yuanxin/mvp/web/media/MediaService.java:115 | `jdbc.update("UPDATE media_objects SET state = 'failed', last_error = ?::jsonb,"` | 内部诊断写入（失败路径） | E 实施代理 | oracle round-9 | **合规** | 当前调用链（MediaIntakeService.java:76-82）仅写入错误码/消息或固定文本；该处本身无通用脱敏/限长机制（局限如实记录）；media last_error 无对外端点投影 |
| web-java/src/main/java/cn/yuanxin/mvp/web/media/MediaIntakeService.java:54 | `* 校验实际格式/大小后标 available。校验失败 → failed + last_error 并抛出。` | 注释（写入边界说明） | E 实施代理 | oracle round-9 | **合规** | 受理失败诊断写入说明，非业务决策 |
| worker-python/src/mvp_worker/runtime/expire.py:9 | `last_error；否则旧领取者过期后任务被无限重放。两条 UPDATE 各自带` | 注释（重试上限语义） | E 实施代理 | oracle round-9 | **合规** | 说明终态诊断用途；代次守护条件更新 |
| worker-python/src/mvp_worker/runtime/expire.py:28 | `'code', 'RETRY_LIMIT_EXCEEDED',` | 内部诊断写入（回收触顶） | E 实施代理 | oracle round-9 | **合规** | code 常量+固定 message；echo 投影现仅映射为 closed enum，不外发原始 code |
| worker-python/src/mvp_worker/runtime/expire.py:77 | `'message', 'graceful release at attempt ceiling',` | 内部诊断写入（停机释放触顶） | E 实施代理 | oracle round-9 | **合规** | 同上；固定文本，无动态敏感内容 |
| worker-python/src/mvp_worker/media/repository.py:13 | `last_error, created_at, updated_at` | 内部读取（返回 dict） | E 实施代理 | oracle round-9 | **合规** | 返回 dict 而非 MediaObject；当前生产源码未发现调用方（仅测试调用）——不得称“供内部状态判断已实际发生”；未用于业务决策/跨服务协议、不对外投影 |
| web-java/src/main/java/cn/yuanxin/mvp/web/system/SystemEchoController.java:94 | `EchoJobLastError lastError) {` | 客户端投影（closed enum 映射） | E 实施代理 | oracle round-9 | **合规** | lastError 仅投影 {reason 封闭枚举, retryable bool}；原始 code/message 不外发（RV-2/3 实测） |
