"""MVP 后台异步任务 Worker（T12 async_jobs 消费端）。

A 包交付：领取/续租/过期回收/代次受控完成运行时、``system.echo`` handler、
handler 注册表扩展点（B/C/D）、媒体访问骨架与健康端点。
至少一次执行；重复落地由租约代次 + 业务输入版本 + 唯一约束阻断（不宣称
exactly-once）。见 backend/worker-python/README.md。
"""
__all__ = ["__version__"]
__version__ = "0.0.1"
