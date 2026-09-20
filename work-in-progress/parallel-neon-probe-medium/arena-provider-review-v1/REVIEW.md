# Arena provider / buft 独立只读审查

结论：**正常路径和已显式处理的provider/wrapper失败分支，在既定single-owner、固定ABI、原allocator遵守契约的范围内通过静态审查；最多1MiB、实际32KiB payload无模型诊断可按这些限制继续独立构建。不能评为生产异常恢复全部通过。** 下列已知上游OOM缺口在本次小额路径也可达，应在声称“所有失败安全回收”前修复。未修改B目录或正式源码，未重新运行会向B目录写证据的脚本，未接触SDK/硬件。

## 需修项：单buffer也存在未检查realloc失败

`model-arena-provider-v1/k7_arena_diagnostic.c:24`调用`ggml_backend_alloc_ctx_tensors_from_buft`。固定ggml `ggml/src/ggml-alloc.c:955–956`的alloc_tensor_range先从buft成功申请buffer，随后直接用realloc覆盖`*buffers`，并未判NULL就写入buffer条目。即便只有一个buffer，第一次realloc(NULL,sizeof(pointer))普通heap不足仍会触发NULL写入，arena buffer所有权未返回给kap_diagnostic，无法经过其done清理。该问题不被1MiB arena限额或provider OOM模拟覆盖。

建议最小修法：针对固定版本准备checked helper/独立补丁，先用临时指针接realloc；失败释放本次尚未入数组的buffer，再释放此前数组中buffer与数组，返回NULL；禁止覆盖旧数组后丢失所有权。测试应在真实provider申请之后精确注入该metadata realloc失败，确认provider live slots/bytes和arena available基线恢复、ctx丢弃且type释放。若本轮只做正常小额target诊断，可以保留此明确未验收项，不应改写成异常路径通过。B的HANDOFF已声明该上游问题，审查新增的是“本次单buffer路径也到达”的确认。

另一明确边界：`ggml_init`即便传入静态metadata，仍在ggml.c:1441经GGML_MALLOC申请context；OOM走上游abort而非返回NULL，诊断中的`if(!ctx)`无法覆盖。此时尚未arena payload分配，但C入口可能非正常结束、owner flag无法普通清理。外部生产服务需要另行修改/封装该行为，不能通过加C++catch捕获abort。多buffer wrapper new异常另有已知清理边界，本次固定32KiB单buffer不触发多buffer分支，不扩大本审查为完整loader审核。

## 指针、尺寸与释放

- 真实port arena头/实现与provider的input副本逐字SHA256一致：base=0x60000000、size=0x40000000、alloc为mm_memalign(heap,64,bytes)，free为void mm_free。证据见verification.json。
- buft向provider申请向64字节取整的padded尺寸，CPU borrowed wrapper使用原logical bytes。release按同alignment重新计算padded，并传回buffer->context原指针；没有把arena payload交普通free/delete。wrapper小对象由ggml核心释放，domain只在无非零buffer存活时释放。
- provider记录原pointer/bytes/valid，只有三项完全匹配才调用k7_model_free，错误size/foreign/double release不进入mm_free。范围和对齐在接受指针前检查；不合规指针保留quarantine槽而不是尝试释放未知地址。这是保留资源失败，不是回收成功。
- 范围检查用address-base及size差值避免加法溢出；64对齐+bytes区间只说明域内，分配大小/不重叠/可访问性仍依赖真实mm allocator契约，没有假称范围检查能证明allocator本体正确。
- 正常销毁顺序aggregate buffer→ggml ctx→buft可接受；先释放tensor引用的buffer后立刻丢弃ctx，期间不再访问tensor。失败ctx不复用。type销毁失败留在static provider.retained_type；不能清零state丢弃隔离资源。
- zero-size dummy绕过buft回调，无法进入live_buffers计数；已在头文件和交接明确，必须先释放所有dummy/外部type引用。本诊断创建两个非零tensor，不走dummy。通用生产调用方不能把destroy的EBUSY视为完整引用计数。

## 限额与错误报告

- provider请求alignment必须恰64，bytes为64倍数，单次及累计<=1MiB、最多8槽；buft同时受单buffer/累计padded quota限制。前提是state不复制不改写，所有调用串行；没有跨独立provider实例或其他k7mem客户的全局1MiB限额。
- 实际诊断2×64×64×4=32768 payload，另32768静态metadata，以及普通heap的context/domain/wrapper和任务栈；“1MiB上限”不是全程序占用上限，更不是把1GiB arena初始化缩为1MiB。真实arena初始化仍建立已有1GiB CPU heap。
- 包装构造异常被buft捕获并释放已申请payload；provider回调自身依合同不抛异常。void释放无法报告mm回收结果，因此available前后对照只在独占arena窗口有意义。其他客户并发变化不能直接判为泄漏。
- `errors`/`quarantined`会使后续kap_initialize拒绝复用；初始化raw负errno与诊断正EIO分别报告，没有把失败伪装为成功。配额拒绝计errors是该候选既有fail-close策略，不是错误计数清零重试。计数器长期回绕未防护，但本次单轮诊断不触及；不据此给长期服务验收。

## 目标编译门禁

1. 使用C11编译provider/diagnostic/entry，C++17且异常支持编译buft，链接同一固定ggml ABI及实际C++异常运行库。不能用-fno-exceptions编译含try/catch的生产buft。
2. 目标不得定义KAP_HOST_MAIN或K7_BUFT_TESTING，不得添加host-mock include路径、不得链接mock.c；建议检查预处理宏BASE/SIZE仍为真实值及nm符号由正式arena实现提供。
3. provider/input/arena仅作证据，不要与正式port实现重复编译。provider冻结的input/buft源码应与buft-v1本体哈希一致，本次已核对。
4. 运行入口只锁定本应用owner；静态metadata要求全局单诊断，不支持不同state同时调用kap_diagnostic。测试窗口禁止另一arena客户并发，才能判断基线恢复。
5. 实际范围检查、8192项set/get、available恢复、栈峰值、内存映射/cache属性均需新镜像实测；已有主机mock/shape-only对象不证明目标编译或DDR验收。此审查不操作硬件，不产生模型/图算子验收结论。

## 审查证据

inputs.json锁定本次读取的生产代码、真实port接口、上游实现和B的已存在测试摘要；verification.json包含源码身份比较与B测试摘要统计。只做只读源码/已存在证据核对，无新执行测试，不冒称重新验证B的主机结果。输出哈希见hashes.json。
