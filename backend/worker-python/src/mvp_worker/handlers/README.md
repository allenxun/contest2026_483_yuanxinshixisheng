# handlers/ — Job Handler 注册表（B/C/D 扩展点）

本目录是 Worker 侧**唯一**的业务接入点。A 包只注册 `system.echo`；
其余业务 job_type（`assessment.analyze`、`identity.enroll`、
`plan.generate`、`notification.deliver`、`media.cleanup`）**不注册**——
领取后走 `fail_unsupported`（failed / `UNSUPPORTED_CONTRACT`，一次写回，
绝不重试循环），运行日志带 "extension point for B/C/D" 提示。

## 如何新增一个 handler（B/C/D）

1. **契约先行**：在 `backend/contracts/schemas/payload-<job>.json` 定义/更新
   payload JSON Schema（draft 2020-12，必含 `schema_version` const），
   并在 `backend/contracts/samples/jobs/` 放样例。契约变更走总协调。
2. 新建 `src/mvp_worker/handlers/<job_type点改横线>.py`，实现
   `mvp_worker.handlers.Handler` 协议：

   ```python
   class MyHandler:
       name = "my-handler"

       def validate(self, payload: object) -> None:
           # 用 jsonschema 严格校验 payload-<job>.json；
           # 未知 schema_version / 违反 schema → raise UnsupportedPayload
           # （错误消息只含 json_path + 关键字，禁止回显 payload 值）

       def handle(self, ctx: HandlerContext, job: JobRow) -> HandlerResult | None:
           # 1) 事务外做重活（算法/大模型/OSS）；每次外部调用边界检查
           #    ctx.abort_event —— 置位即立刻 return None（租约已丢，禁提交）
           # 2) 需要写业务表：把短事务回调放进 HandlerResult(business_tx=...)
           #    运行时在同一个最终事务里先执行 business_tx（先锁业务行、
           #    持锁后复核 job.input_revision 仍是当前版本），再条件更新
           #    async_jobs → succeeded；守卫失败整体回滚（旧代次/旧输入的结果
           #    不发布，DD 8.1 锁顺序）
           # 3) 业务性失败 raise JobFailed(code, message, retryable=False/True)
   ```
3. 模块底部导出实例并在 `handlers/__init__.py` 末尾注册：
   `register("<job_type>", my_handler_module.handler)`。
4. **写入边界（硬约束）**：只允许
   - `async_jobs` 的租约/状态字段（由运行时统一写，handler 不直接写）；
   - 本任务自己的 `media_objects` 行；
   - 设计中划给 Worker 的业务表**字段**（字段级条件 UPDATE，禁整行
     upsert 覆盖 Java 侧字段；禁写 `idempotency_requests`——T13 归 Java）。
5. 测试：`tests/` 内用真实 PG（临时库 + Flyway 迁移），至少覆盖
   claim→handle→complete 成功、租约丢失中止、stale-generation 回滚
   （business_tx 写了也不能发布）。

payload 禁止携带照片/pickle/Java 类名/可执行代码/签名 URL/凭据（DD 9.1）。
