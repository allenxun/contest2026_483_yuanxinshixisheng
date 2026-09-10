# N2 诊断列消费点分类检视（原始 grep + 分类）

原始命中 23 处；规则：echo GET=客户端投影(read)，worker complete/loop=写入，其余人工检视；未见用于业务决策或跨服务任务协议。

| 文件:行 | 读/写 | 分类 | 业务决策? |
|---|---|---|---|
| web-java/src/main/java/cn/yuanxin/mvp/web/system/SystemEchoController.java | read | 客户端投影（echo GET lastError） | 否 |
| web-java/src/main/java/cn/yuanxin/mvp/web/system/SystemEchoController.java | read | 客户端投影（echo GET lastError） | 否 |
| web-java/src/main/java/cn/yuanxin/mvp/web/system/SystemEchoController.java | read | 客户端投影（echo GET lastError） | 否 |
| web-java/src/main/java/cn/yuanxin/mvp/web/media/MediaService.java | review | 其他引用（人工检视） | 待检视 |
| web-java/src/main/java/cn/yuanxin/mvp/web/media/MediaService.java | review | 其他引用（人工检视） | 待检视 |
| web-java/src/main/java/cn/yuanxin/mvp/web/media/MediaService.java | review | 其他引用（人工检视） | 待检视 |
| web-java/src/main/java/cn/yuanxin/mvp/web/media/MediaService.java | review | 其他引用（人工检视） | 待检视 |
| web-java/src/main/java/cn/yuanxin/mvp/web/media/MediaIntakeService.java | review | 其他引用（人工检视） | 待检视 |
| worker-python/src/mvp_worker/runtime/complete.py | write | 写入（worker 失败诊断） | 否 |
| worker-python/src/mvp_worker/runtime/complete.py | write | 写入（worker 失败诊断） | 否 |
| worker-python/src/mvp_worker/runtime/complete.py | write | 写入（worker 失败诊断） | 否 |
| worker-python/src/mvp_worker/runtime/complete.py | write | 写入（worker 失败诊断） | 否 |
| worker-python/src/mvp_worker/runtime/complete.py | write | 写入（worker 失败诊断） | 否 |
| worker-python/src/mvp_worker/runtime/complete.py | write | 写入（worker 失败诊断） | 否 |
| worker-python/src/mvp_worker/runtime/complete.py | write | 写入（worker 失败诊断） | 否 |
| worker-python/src/mvp_worker/runtime/complete.py | write | 写入（worker 失败诊断） | 否 |
| worker-python/src/mvp_worker/runtime/complete.py | write | 写入（worker 失败诊断） | 否 |
| worker-python/src/mvp_worker/runtime/complete.py | write | 写入（worker 失败诊断） | 否 |
| worker-python/src/mvp_worker/runtime/complete.py | write | 写入（worker 失败诊断） | 否 |
| worker-python/src/mvp_worker/runtime/expire.py | review | 其他引用（人工检视） | 待检视 |
| worker-python/src/mvp_worker/runtime/expire.py | review | 其他引用（人工检视） | 待检视 |
| worker-python/src/mvp_worker/runtime/expire.py | review | 其他引用（人工检视） | 待检视 |
| worker-python/src/mvp_worker/media/repository.py | review | 其他引用（人工检视） | 待检视 |
