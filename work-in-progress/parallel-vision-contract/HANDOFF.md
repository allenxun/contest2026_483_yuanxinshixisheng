# 视觉检测结果与跟踪输入候选

2026-09-10；实现者为当前协作系统明确分派的 `/root/vision_contract`，协调者 `/root`。环境给出的主会话上下文 ID 为 `01a0892e-2964-7ec3-bd76-9ab4937980cb`；未取得独立子代理会话 UUID，不编造。未写中央日志、未导出或伪造 JSONL。

交付只在本目录。正式代码、旧 PC 与文档只读，未运行模型、摄像头、NPU、云台或任何硬件。未访问 SDK/Ubuntu/私密配置。未提交推送。

## 核实调用链

以下是当前正式源码静态核对；历史已确认功能依据 README 与代码日志对应表，本轮未重复硬件验收。

1. `app/k7host/k7host_main.c`：`photos` 预置调用 `camera_capture(..., scale=4, detect_faces=true, &config)`；`track`/`trackcal` 为跟随入口。`camera_capture` 建立 `k7_pipeline_start`，摄像数据发布到流水线。
2. `k7_pipeline.c`：`k7_pipeline_publish` 赋 parser publication monotonic 时间；`decode_worker` 将 JPEG 缩为 RGB160×120，经 `k7_yunet_detect` 得 `k7_faces_s`，成功才传给 `track_observation`，失败传 NULL。`k7_yunet.h/.c` 已规定去除上下 letterbox 并裁到160×120，最多16框，x/y/width/height/score；`faces.usec` 是推理耗时，绝不是曝光或帧时间。
3. `track_observation` 调用纯计算 `k7_track_step(faces, now, published_us, halted)`。跟踪器自行选主脸、至少两次确认、按 IoU 连续关联、边界限位、置信度至少0.7、年龄最多250000微秒；未来/重复/倒退时间失效。只有外围 `gimbal_link_send` 才发送目标。本候选不链接该外围，只链接原始 `k7_track.c` 做主机回放。
4. 同一帧 `k7_photo_process(jpeg, sequence, published_us, track_result, face_count, halt)` 仅对单脸锁定且命令变化估算稳定的帧做原图640×480解码、ROI、`k7_pose_infer`；`vf_step` 按真实观测 yaw 执行正面→左45→右45。稳定是图像姿态/命令变化估算，没有伺服编码器证据。
5. `PHOTO/PHOTOQ` 携 sequence、epoch、side；`host/vision/photo_protocol.py` 的 Protocol → capture.request → saver_worker → FrameCache精确sequence → save_exact，保存JPEG及元数据后写ack.request；`photo_controller.py` 发photoack，板端 `k7_photo_ack` → `vf_saved` 才确认完成。缺精确帧、落盘失败不能完成。候选不改拍照链。

## 已实现接口与边界

`vision_contract.h/.c` 直接 include 正式 `k7_yunet.h`，不复制或更改其结构。

|来源/能力|实现|限制|
|---|---|---|
|原生人脸结果|vv_from_yunet|仅已有160×120、最多16框，保留原始置信度|
|旧PC已后处理仪器结果|vv_from_legacy_device|只接runtime.infer_bytes的device_bbox xyxy/device_score，原始EXIF归一化且不镜像图像坐标；不接raw logits|
|原生人体/仪器|vv_unavailable / vv_native_supported|unsupported；模型存在不证明可运行|
|现有人脸跟踪输入|vv_tracking_input|原坐标回转k7_faces_s，不缩放、不把仪器或人体伪装成人脸|

读取了旧PC模型manifest与runtime代码，并只核对model.onnx存在；未读取/复制模型本体。旧PC decoded_xywh 后处理和RK3576候选raw stride logits不相同，未猜测新模型输出。此处“仪器”是旧接口device的语义类别，没有捏造模型类别ID。没有找到已核实人体输出接口。

统一结果携 frame_id、published_us、now_us、尺寸、框/中心、置信度、类别、source、replay、inference_us 和帧级失效状态。`replay` 与 source 独立：本测试所有数据是synthetic replay，通过已有接口形状，不是实测检测。调用者必须在同一单调时钟域提供时间；PC可空的timestamp_ms不能直接当板端published_us。未知时钟返回TIME_UNKNOWN，未来或超过250000微秒返回STALE；恰好250000允许。消费时再次检查过期/时钟回退。零目标EMPTY与无能力UNSUPPORTED、推理错误、非法数据明确分离。

无堆分配、无排队、最多16项扫描，图像尺寸上限8192；人脸仍严格160×120。非法NaN/Inf/越界/非正框使整帧失效，不交付半帧。低于0.7的人脸置信度原样保留，由现有跟踪器决定不跟随。所有拒绝的跟踪输入清零，调用者应给 `k7_track_step` 传NULL使其失锁，而不是保留旧框。输入输出对象必须独立且调用期间不可并发修改；此C API不是不可信网络字节解析器。

**无状态适配边界：** frame_id只是原样保留，不提供跨帧去重或乱序门控。现有k7_track_step拒绝重复/倒退的sample和now；halt在时钟检查之前处理，不消费该帧时间。本轮回放覆盖此行为。若未来队列可能以新时间戳重复旧frame_id，集成层必须按流/会话代际拒绝重复、乱序并定义序号回绕与重启策略；本候选不宣称解决该情形，不得绕开已有跟踪状态机。

## 测试与交付

运行：`C:\Users\pc2025\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe E:\openvela\VelaVision\work-in-progress\parallel-vision-contract\run_tests.py`。

MinGW GCC12.2，C11 -O2 -Wall -Wextra -Werror -pedantic，编译与进程分别限30秒。链接原始k7_track.c，1000帧纯合成序列直接输入与适配输入逐帧对照，涵盖空帧、过期/未来、halt、重复时间与低置信度；其余覆盖容量、整帧拒绝、NaN/Inf、尺寸、时钟未知、消费时过期、仪器坐标与unsupported。最终通过2236项检查。不是模型准确率或设备性能测试。

首次运行编译成功、测试失败：错误地预期每个halt后的重复采样都STALE；实际正式跟踪器halt先返回且不消费时间。已修正测试预期，不改正式跟踪器。首次失败命令/输出/二进制保留在evidence/20260910T065810321594Z。该次未单独冻结测试源码，不能声称其二进制能用最终源码逐字重建。最终运行额外冻结测试和候选源码哈希。各次evidence/result.json保留真实命令、输出和退出码；inputs.json记录所读路径及SHA256，前后未变化。目录枚举不等同逐文件内容审计，模型本体不在输入清单。

未完成：正式流水线接入/队列门控、跨域时钟转换、人体检测器、原生仪器模型运行时、真实图像回放与精度验证、板端编译/硬件联合验收。中央日志由协调者按真实会话采集。本候选交付冻结后仅供只读核对，不自动集成。
