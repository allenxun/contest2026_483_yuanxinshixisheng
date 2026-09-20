# face-insightface-server 对澜皙 MVP 人脸需求的调研

日期：2026-09-10。性质：代码与设计调研；不是实施、部署、采购或上线决定。

## 1. 结论

**现有仓库不能直接承担澜皙 MVP 的身份准入。** 它是可复用的 Python/FastAPI 同步算法服务原型，已实现检测、特征提取、简易 1:N 搜索、按 name 注册/覆盖及删除。它并非只有 embedding 的裸库，但现有“人员库”距离稳定、可恢复、可并发维护的人员服务仍有明显差距。

阻断直接复用的主要问题：

- 没有指定 person ID 的 1:1 核验，也没有两图比较 HTTP API。
- 没有质量准入、多脸拒绝、身份不确定状态、可靠新人确认、重复人员检测及原子建档。
- 人员引用来自文件名；下划线截断、一人多图覆盖和删除不一致会破坏 member 映射。
- 没有认证、请求防重放、活体检测、持久化事务及多进程索引同步。
- 代码配置使用 buffalo_l，官方预训练权重的默认许可仅限非商业研究；本仓库没有提供额外商用授权证明。
- 没有 Android/云台跨设备测试、容量与延迟压测证据。

**MVP 建议：Java 后端持有业务权限与成员关系，通过统一同步人脸适配层，优先对阿里云已具备的核心 API 做设备 PoC。** 此为工程选择建议，不代表采购或已通过实测。自托管方向可复用本仓库的推理封装，但须先解决权重授权、身份库及准入等缺口。不要把本仓库直接挂到 APP/云台，也不要将“Unknown”直接转换为创建 member。

## 2. 核查范围与证据边界

根规则：[AGENTS.md](/home/lousuan/lansee/AGENTS.md)。先检查管理信息，发现实际仓库名为 face-insightface-server。对应 dev 干净、无项目内 AGENTS.md、无 docs/，本地 dev 与本地记录的 origin/dev 同指向以下提交；没有远端 fetch，因此不声称已验证远端最新状态。

- 基线：`db1b4a7ad3e8f246a080cbb22caf470b5f56cc44`。
- 隔离评审分支：`architecture/face-mvp-review`，直接从本地 dev 创建。
- 评审目录：`/home/lousuan/lansee/architecture-face-mvp-review/face-insightface-server`。
- 源码 SHA256（face_services.py）：`177b4836796ba93310f7e4099671b2f5f7e98f84f3d34200e36ec57ee0119f85`。
- 原始受版本管理文件仅 .gitignore、app.py、face_services.py、main.py、pyproject.toml、uv.lock；无测试、Dockerfile、部署配置、模型权重或业务设计文档。pyproject 声明 README.md，但该文件不存在。
- dev/AGENTS.md 含旧后端及已停用 release 指令，仅作历史定位线索；依照用户明确提供的根规则，不执行旧流程，不读取旧 ai-skin-backend。
- 未检查其他业务仓库源码。当前 Java/PG/OSS、member/account 与权限语义以任务提供背景为设计输入，没有把它们说成已验证的 Java 实现。
- 未运行模型、服务、摄像头、压测或真实人脸测试；未下载模型、上传照片、部署、推送、合并或修改业务代码。只做源码阅读、AST 路由枚举和文件名规则的轻量表达式验证。

本报告保存在隔离评审分支的 docs/，是待评审提案。对应 dev 此前没有 docs/，本报告尚未合入 dev，不能被视作已经发布的权威设计。后续如采纳，应仅将文档变更单独纳入本项目 dev；跨项目业务接口主文档建议归 ai-skin-backend-v2/docs/，本项目引用其版本，不在此复制维护业务权限规范。

## 3. 能力对照

“已实现”指本地基线可从代码确认，不代表已在运行环境验证。阿里云列来自用户已核实背景及本次官方文档复核。

| 需求 | 本仓库已实现 | 缺口/限制 | 阿里云对照 |
|---|---|---|---|
| 人脸检测 | FaceAnalysis.get，搜索返回 bbox | 无独立检测路由；多脸搜索全部返回，注册只取最大脸 | SearchFace 返回人脸位置；两图比对也选最大脸，业务仍须单脸准入 |
| 清晰度、光照、遮挡、姿态 | 未见业务判定 | 不输出质量/姿态；检测到脸不等于照片可用 | SearchFace/AddFace 有质量阈值，默认未配置时不做质量拦截 |
| 特征提取 | normed_embedding，内部使用 | 无对外提取 API，无模型版本字段 | 无需业务直接持有 embedding 即可调用建库与搜索 |
| 1:N 已有人识别 | 字典全量遍历，返回每张脸 Top 1 | 无 Top K、第二名差距和跨候选歧义判定 | SearchFace 提供候选结果、EntityId、FaceId |
| 指定成员 1:1 | 无 | 应新增指定 person 核验或两图比较；不能把全库第一名判定当等价实现 | CompareFace 是两张图片比较；需要保留该 member 的可信参考照 |
| 新建/更新人员 | register 按 name 写文件及向量 | 无稳定 ID 生成、冲突检查、独立人员记录；同名可能覆盖 | CreateFaceDb/AddFaceEntity/AddFace 分离库、人员和照片 |
| 人员读取/列表/删除 | delete 按 name 删除；无读取/列表 API | 删除失败恢复与稳定引用不足，无单照片删除 API | 用户已核实人员库能力；本次未逐项复核删除生命周期保证 |
| 一人多照片 | 磁盘/cache 可有多文件 | 内存只有一条向量，重载相互覆盖；非完整多模板识别 | 一个 EntityId 可含多 FaceId |
| 未匹配/不确定/新人 | 只有 Unknown 或 name | 没有“不确定”；低分、空库等混在 Unknown 里 | 候选与质量数据可供业务判定，但不自动证明“新人” |
| 并发去重 | 无；MD5 仅用于缓存复用 | 不同 name 可登记同一个人，同名写入无事务 | AddFace 有可选类间重复检查，但不能推断跨请求原子去重 |
| 活体/照片或视频重放 | 无 | 无活体模型调用、挑战或新鲜度验证 | DetectLivingFace 是图片静默活体，不等于完整防重放 |
| 长期授权/撤销/历史权限 | 无 | 应由 Java 业务后端承担 | 同样由 Java 业务后端承担 |

阿里云依据：[SearchFace](https://help.aliyun.com/en/viapi/developer-reference/api-t00lyd)、[AddFace](https://help.aliyun.com/zh/viapi/developer-reference/api-trlvh9)、[CompareFace](https://help.aliyun.com/en/viapi/developer-reference/api-fomc02)、[DetectLivingFace](https://help.aliyun.com/zh/viapi/developer-reference/api-j81gjl)。这些是接口能力，不是我们的设备识别率或延迟实测。

## 4. 现有 HTTP API 与调用方式

所有路由都在 [face_services.py](/home/lousuan/lansee/architecture-face-mvp-review/face-insightface-server/face_services.py:203)，AST 枚举确认四个业务路由。启动入口在第 254–255 行：Uvicorn 监听 0.0.0.0:8002。没有可配置端口、健康/就绪检查或服务认证代码。

| 路由 | 输入 | 输出和错误 | 函数证据 |
|---|---|---|---|
| POST /recognize | multipart/form-data：file 必填；threshold 浮点，默认 0.45 | JSON：faces 数组，每项 name、score、bbox；无脸为 faces:[]；无法解码返回 HTTP 200 的 error:"Invalid image" | recognize 203–214；search 138–159 |
| POST /register | multipart：name、file 必填；按上传文件名后缀接受 jpg/jpeg/png | 成功：status、message、count；后缀/无脸/无法解码返回 400 detail；未捕获异常可能为 500 | register 216–232；register_new_face 90–136 |
| POST /reload | 无显式参数 | status、count；同步从磁盘重建内存/cache | reload_db 234–237 |
| POST /delete | 表单 name 必填 | 成功：status、message、current_count；内存找不到 name 则 404 detail | 路由 239–252；引擎 161–198 |

未提供 JSON 图片、Base64、OSS URL 输入，也没有返回 task ID、person ID、face ID、模型版本、质量、活体或可靠性状态。表单缺失/类型错误可由 FastAPI 校验，但本次没有启动服务确认实际响应。threshold 没有显式范围校验；它不应由 APP 或云台自行控制。

Java 可以用 Spring 的 HTTP 客户端构造 multipart，把图片 bytes 作为 file、服务端配置阈值作为 threshold，解析 JSON。Python 可以用 httpx/requests 发送相同表单。示意：

```text
Java -> POST http://内部算法服务:8002/recognize
Content-Type: multipart/form-data
file = 当前照片二进制
threshold = 后端策略值
响应：{"faces":[{"name":"p123","score":0.72,"bbox":[...]}]}
```

这是基于现有 API 的接入说明，不是已存在或已测试的 Java/Python 客户端。当前仓库未提供客户端实现。Java 若从 OSS 取图，应在受控后端读取并转发；现有服务自己不读 OSS URL。

认证：源码没有 token/API key、签名校验、租户隔离或权限中间件；不能证明现网是否另有网关，所以结论限定为“仓库未实现”。一旦网络可达，四个路由在应用层均未鉴权。上线前必须补服务认证、入口限制、超时/大小限制、错误协议和请求审计；普通识别调用方不应拥有 reload/delete 权限。

## 5. 人员库、特征、恢复与关键缺陷

核心证据：[FaceEngine](/home/lousuan/lansee/architecture-face-mvp-review/face-insightface-server/face_services.py:17)。

### 5.1 实际保存方式

- 默认当前工作目录的 raw_faces/ 保存原始照片；face_cache.pkl 保存按 filename 索引的 hash 与 embedding。不是 PG、OSS、Redis、SQLite 或专用向量数据库。
- 内存 `face_db[name] = embedding` 是人员搜索结构，无 ANN、Faiss/HNSW 或 SQL 索引。每张查询脸对所有人员做 np.dot，复杂度随库大小线性增长。
- MD5 是照片 bytes 的缓存失效依据，不是相似人脸去重、模型校验或安全签名。
- 启动/POST /reload 扫描小写 .jpg/.png/.jpeg；命中相同文件名和 MD5 就复用缓存，否则重新提特征。模型版本未进入缓存键，替换模型后可能沿用旧特征。
- 注册完成后当前进程内存立即更新；其他进程/副本不会收到更新。每个进程 import 时各建一个引擎和独立字典。
- 重启可从照片和 pickle 恢复，但“有恢复路径”不等于可保证正确恢复。pickle 损坏没有兜底；未处理的文件读取/future 异常可中断初始化。

### 5.2 稳定 ID 与多照片问题

`_process_one_image` 第 42 行把文件 stem 按下划线切割，只取第一段。注册却用完整 name 作为内存 key。例：注册 name=member_001，当前内存 key 是 member_001；重启读取 member_001.jpg 后 key 变为 member。轻量表达式验证确认这个转换，未运行人脸模型。

同人 personA_1.jpg、personA_2.jpg 可能都留在缓存，但初始化第 81 行反复赋值 `new_face_db[name] = embedding`，最终只有一个特征；as_completed 的完成顺序决定最终保留哪张，不能视为多图聚合。register 相同 name、相同扩展名直接覆盖；不同扩展名则残留多文件，下次加载又相互覆盖。

因此 name 至多是受严格限制时可临时使用的外部 key，不能作为已经可靠实现的稳定 person ID；没有独立单张 face ID。count 是内存 key 数量，不等于持久化图片数或真实人数。业务字段不能直接绑定姓名、文件名或 Unknown。

### 5.3 写入、删除与并发

- register 第 98 行先写磁盘，再验证图片。无法解码会留下坏文件；同名无脸上传可能覆盖再删除原图，而旧内存特征尚存。缓存写失败可能发生在内存更新之后，无回滚。
- delete 先删内存，再查磁盘和改缓存；中途失败可能部分删除。带下划线 name 的磁盘匹配与注册 key 不一致，可能返回成功但实际删除 0 文件，重启后又出现截断的人员。
- search 推理阶段持锁，但遍历 face_db 不持锁；注册、删除、重载没有覆盖整个生命周期的一致性锁。单 Uvicorn 进程中 async 路由里的同步计算会阻塞事件循环，不能据此把竞态认定为每次必现；在线程调用、多 worker 或外部文件改动场景下仍无正确并发保证。
- reload 使用自己的全量扫描/写回，没有与在线写入的完整事务。多进程共用同一 pickle 也没有进程锁。
- 注册无业务幂等键、唯一人员约束或先搜后注册的原子控制；重复点击、超时重试、两台设备同时发现同一新人均可能重复建档。
- name 未做路径安全校验，直接拼入文件路径；存在路径穿越/非预期文件覆盖的代码风险。没有用真实写入攻击去复现。
- .gitignore 忽略 raw_faces/，未忽略 face_cache.pkl；误提交生物特征缓存存在风险。

### 5.4 备份与删除要求

仓库没有备份/恢复演练、加密、留存或删除队列实现。若仅为受控 PoC，至少固定持久卷，维护可信只读模型版本，禁止非可信 pickle 输入，并在停止写入的一致时点备份照片与版本信息。生产应把人员/照片/特征元数据放入可靠存储，索引作为可重建派生物，而非继续把 pickle 当事务数据库。

删除应覆盖人员模板、单照片引用、索引、OSS 按策略保留的照片及备份到期处理；撤销 account 的查看授权与删除 member 人脸模板是不同业务动作，不自动联动扩大删除范围。以上为待实现建议。

## 6. 分数、质量、未知人与活体

`search` 对归一化 embedding 做点积，即余弦相似度。默认严格 `max_sim > 0.45` 才返回 name，等于阈值仍是 Unknown。score 不是概率，不可解释为“45% 可信”。只保留最高分，不返回次高候选或排名列表；低于阈值也仍返回最高分，但隐藏候选 name。空库时初值 -1 配 Unknown；无脸是空数组。

照片模糊、角度大、光线差、未登记或人员库异常都可能导致未匹配，现有协议不能区分。app.py 中“0.4~0.5”注释没有本项目评测支撑。阿里云与本地恰好都出现 0.45，不能因此共用阈值、误识率或质量策略。

当前注册取最大脸，没有单脸确认；search 不限制业务目标脸。现有代码未判定清晰度、曝光、遮挡、偏航/俯仰/滚转，也未将模型检测分数输出。InsightFace 旧版底层能提供检测与关键点，并有姿态相关能力，但这不能算本服务已实现质量准入。官方旧版模型包和接口背景见 [v0.7 说明](https://raw.githubusercontent.com/deepinsight/insightface/v0.7/python-package/README.md) 与 [FaceAnalysis 源码](https://raw.githubusercontent.com/deepinsight/insightface/v0.7/python-package/insightface/app/face_analysis.py)；它们为版本家族参考，不冒称锁定 0.7.3 的本地已安装源码。

现有代码无活体判定、RGB 防伪模型、视频挑战、随机动作或请求新鲜度验证。app.py 读取摄像头并画框的示例同样不是活体检测。官方当前主线已公布较新 Server 和可选 liveness addon，但本地 uv.lock 是 0.7.3，构造器也没有启用 addon，不能将上游新增能力算进当前仓库。[官方当前说明](https://github.com/deepinsight/insightface/tree/master/python-package)

建议业务适配层明确区分：MATCH、NO_MATCH_CANDIDATE、UNCERTAIN、QUALITY_REJECTED、LIVENESS_REJECTED、ENGINE_UNAVAILABLE；这些是建议状态，不是现有 API。只有在设备照片质量、活体/采集真实性、库就绪和重复检查等前提满足后，才能评估可靠新人。低分本身永远不是可靠新人证明。

## 7. 模型来源、许可与部署

### 7.1 模型与商用边界

本地 face_services.py 第 28 行及 app.py 第 10 行指定 buffalo_l。uv.lock 锁定 insightface 0.7.3；pyproject 只是 >=0.7.3，未使用锁文件重新解析可能升级，需固定发布依赖。

官方旧版模型表把 buffalo_l 列为 SCRFD-10GF 检测、ResNet50@WebFace600K 识别、2d106/3d68 关键点及年龄性别，包体积约 326MB。这是官方包说明，不是本机实际权重或运行内存测量。[官方旧版模型说明](https://raw.githubusercontent.com/deepinsight/insightface/v0.7/python-package/README.md)

与锁文件版本一致的 [InsightFace 0.7.3 发布说明](https://pypi.org/project/insightface/0.7.3/) 明确区分：库代码 MIT；提供的预训练模型包括自动和手动下载均限非商业研究。当前 [官方仓库许可说明](https://raw.githubusercontent.com/deepinsight/insightface/master/README.md) 也明确 buffalo_l 等识别模型需另行解决授权。

本次未检查用户全局 ~/.insightface 模型目录、未下载权重；因此只验证了代码配置的模型名，无法证明现网 ONNX 的文件哈希、来源、是否被替换或是否有额外许可。本仓库也没有 LICENSE 文件或商用模型授权材料。不能凭 Python 包 MIT 标签认定产品商用权重已获许可。商业 MVP 使用前需确认实际权重和授权范围，或采用明确可用的自有/获授权模型；本任务没有联系任何许可方。

### 7.2 推荐部署形态

**应以独立同步算法服务供 Java 调用。** 当前 FaceEngine 理论上可被 Python 引用，但不是干净的库入口：import face_services 会创建 FastAPI app、加载模型、建目录和重建数据库。放入 Celery Worker 会令每个进程各持模型/索引，造成资源重复和索引不一致。若未来要作为库复用，须先拆开引擎、存储和服务启动；本次未实施。

身份准入（测肤定位、APP 授权核验、护理开始/恢复）走 Java -> 同步算法调用 -> Java 决策。异步 Worker 继续做测肤分析、结果图生成，以及未来可异步执行的索引修复/清理；它不能让身份准入排队等待。数据变更若异步同步索引，身份链路须识别尚未可见的状态，不能把未就绪误判为新人。

| 项目 | 证据与结论 |
|---|---|
| Python | pyproject 要求 >=3.12；未发现更细的运行环境配置 |
| 推理依赖 | ONNX Runtime、InsightFace、OpenCV、NumPy；无需因本代码额外部署训练框架 |
| CPU/GPU | 配置 CUDA、CPU provider，但依赖只有 onnxruntime 1.24.4，无 onnxruntime-gpu；不能据 provider 字符串认定实际在用 GPU |
| GPU 补齐 | 需匹配 GPU runtime、驱动、CUDA/cuDNN，并验证实际 provider；官方兼容说明见下 |
| 并发 | 初始化开 8 线程，但模型推理被同一锁串行化；HTTP async 中仍直接执行同步计算 |
| 存储 | raw_faces/、face_cache.pkl 跟随工作目录；容器若无持久卷，生命周期结束可能丢库 |
| 模型获取 | 旧版库可自动下载；交付应使用已核验、获授权、固定哈希的离线模型，不能依赖首次启动临时下载 |
| 容器/监控 | 无 Dockerfile、健康检查、指标、启动编排和资源上限 |
| 性能/容量 | CPU/GPU 型号、RSS、显存、QPS、p50/p95/p99、最大人数和冷启动时间均未知；日志打印初始化耗时不是基准报告 |

GPU 判断依据：[0.7.3 安装说明](https://pypi.org/project/insightface/0.7.3/) 和 [ONNX Runtime CUDA 官方文档](https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html)。不能将上游新 Server 的容量宣传或公开数据集准确率套用于这个 Python 字典实现。

## 8. 相对阿里云的取舍与最小缺口

| 维度 | 本仓库自托管 | 阿里云路径 |
|---|---|---|
| 当前完成度 | 检测/识别原型；身份库与服务工程需补 | 核心建库、人员/照片、搜索和两图比较 API 已具备 |
| 维护 | 自己承担模型、库一致性、备份、认证、扩容和故障恢复 | 平台维护引擎；自己仍承担适配、权限、参考照、失败处理和设备验证 |
| 成本 | 推理机器/存储、许可、开发运维与评测成本 | API 调用及相关云资源、接入与评测成本 |
| 控制权 | 可自管照片、特征、模型版本和位置，但当前实现尚无完善控制机制 | 服务能力和可用配置受提供方约束，模型变更需关注 |
| 可替换性 | 自管稳定人员引用及模型版本后较易控制迁移 | 保留 member 映射和参考照可减少迁移耦合，不能假定可导出供应商 embedding |
| 商用前提 | 实际权重许可必须明确 | 适用服务条款与已开通能力须落实 |
| 真实表现 | 未验证 | 同样未在我们的设备上验证 |

没有调用量、设备并发、合同与资源测量，无法给出价格、盈亏平衡点或“自托管更便宜”的结论。

自托管进入 MVP 前的最小补齐范围：

1. 独立稳定 person ID 与 photo/face ID，完整多模板、按人员核验、读取/删除/更新语义，停止文件名推导身份。
2. 可靠持久化、模型/特征版本、原子变更、恢复与删除机制；清晰的索引可见性和单写入口。
3. 单脸、质量与采集真实性准入，Top K/歧义信息和可校准阈值；无脸/坏图/不确定/不可用分开。
4. 基于业务操作幂等与受控注册串行化/并发协调的重复检查。唯一 ID 只防相同 ID 重复，不防同一个人获得不同 ID。
5. 服务认证、输入安全与统一错误；补健康、资源限制和可观测性。
6. 模型权利确认、跨设备 PoC 与故障演练。

阿里云 AddFace 提供可选类内一致性与类间重复阈值；类间检查只针对每个 EntityId 第一张照片，默认不设置则不执行。它不免除业务幂等、失败补偿与并发验证。[AddFace 官方参数](https://help.aliyun.com/zh/viapi/developer-reference/api-trlvh9)

## 9. MVP 推荐接法与数据架构影响

### 9.1 三条同步业务链路

**云台测肤：** 业务后端确认唯一当前任务及采集上下文 -> 质量/采集真实性准入 -> 在业务允许的人员检索范围做 1:N -> 可靠匹配时绑定 member；不确定时要求重拍或进入既定确认流程。仅可靠确认新人时才可创建。新建流程应有幂等键、在当前注册边界内的并发协调、提交前再次去重和失败恢复；注册尚未可见时不得返回“全库无此人”。

**APP 长期查看授权：** 手机号登录得到 account -> 当前刷脸定位已有 member -> 完成规定核验 -> Java 建立 account 对 member 的长期可撤销查看授权。无匹配或不确定均不创建 member，也不创建授权；没有返回成员列表让客户端绕过核验选择。每次访问资料仍检查有效授权，撤销后历史授权立即失效。

**护理开始/恢复：** Java 从方案确认预期 member -> 以该 member 的 person ID 或可信参考照核验当前照片 -> 通过后准入；失败、不确定、服务不可用则不继续。阿里云适配实现为当前照片与该 member 参考照 CompareFace；多参考照的选择/聚合须预先约定，不能无限尝试直到某张通过。不能先全库搜索后把其他成员的高分结果替换预期 member。

云台持续追踪和换人判断仍由端侧实现；后端处理开始、恢复或业务约定事件的照片，不逐帧处理。成员资料权限不从云台绑定账号继承；云台只取唯一当前测肤任务及结果，人脸命中不开放历史资料。

### 9.2 PG 宽表与 OSS

业务 member_id 保持独立且稳定；算法人员引用只作映射，不是 account、手机号或权限凭证。

| 信息 | 建议落点/语义 | 与当前设计关系 |
|---|---|---|
| member_id | 业务成员主标识 | 保持不变 |
| identity_namespace + face_subject_ref | 命名空间应包含引擎/库作用域；ref 指向算法 person | 可沿用现有命名 |
| face_person_id | 如统一名称，应仍保留 namespace/provider/library 的消歧语义 | 不宜把全球唯一性默认为厂商保证 |
| 单照片 face_id / reference_photo_ref | 独立于 person，可按 member 宽表 JSONB 列表保存必要引用或沿用既有照片结构 | 阿里云 FaceId 不能写进 person 引用字段 |
| 注册状态/版本 | pending/ready/failed/deleting 等受控状态及引擎版本 | 尚未 ready 不能当可靠搜索库成员状态 |
| 核验记录 | 业务操作、预期/命中 member、结果、策略版本、时间与照片引用；只存必要内容 | 分数用于审计，不承担权限语义 |
| 查看授权 | account/member 与撤销状态由现有业务授权机制维护 | 不新增因引擎而来的角色或访问能力 |

这不要求为了算法增加 JOIN：按 member_id 直接读取其宽表字段；按 namespace/person_ref 建普通索引定位 member；唯一约束只对有效映射按实际建模设置。多照片具体结构须由业务主设计确定，本报告不修改表结构。特征留算法存储即可，业务 PG 不必因该原型引入 pgvector，也不必将 embedding 填入 member 宽表。

OSS 继续存原图、结果图、核验图及按需保留的参考照。采用 CompareFace 的成员必须有可用可信参考照，这是明确的数据前提；“只存算法人员 ID”不足以调用两图比较。保留对象 key/版本及用途，不把临时签名 URL 当长期主键。Java 控制读写与临时访问，算法服务只收到本次必要照片。重拍失败不得把失败照自动替换参考照。

PG 与远程算法注册不应假装是一个原子事务：用 pending/ready 状态、幂等操作和补偿/对账保证最终一致。补偿可以由 Worker 执行，但当前用户身份操作应同步明确成功、失败或待重试，不能因异步尚未建库而自动重复建人。

## 10. 小规模 PoC 与验收清单（尚未执行）

先解决测试用途与模型权利，使用取得同意的专用样本；以下规模是建议，不是现有样本量。本次未采集或上传任何人脸。

| 测试组 | 建议设计 | 记录与验收重点 |
|---|---|---|
| 跨设备 | 30–50 人，每人 Android/云台各 3–5 张，不同日期；注册/查询照片分开 | 双向跨设备 1:N 与指定人员 1:1；分别统计误接纳、误拒绝、拒拍与不确定 |
| 场景变化 | 常规/暗光/逆光，偏转与俯仰，眼镜、遮挡、素颜/日常妆/护理前后 | 各条件单独结果，不能只报总平均；大角度与坏图须拒拍而非建新人 |
| 库外与相似人员 | 留出从未登记人员，加入相似外貌的不同人；逐步扩大图库 | Top 1/Top 2 差距、库外拒绝、误建档率；阈值使用独立验证集 |
| 多脸/无人脸/坏图 | 单脸、多脸、空画面、错误编码及极端尺寸 | 统一错误与质量状态；不注册最大路人脸 |
| 活体/重放 | 同意样本的纸照、屏幕照片、屏幕播放视频、旧请求重发 | 区分图像活体与请求新鲜度；失败不建档/不授权/不开始护理 |
| ID/照片生命周期 | 下划线 ID、一人多照、同名不同扩展名、单照片替换/删除、重启 | 映射不变化、模板可控、删除不复活；本原型已知缺陷应先修复 |
| 注册一致性 | 重复点击、超时重试、两设备同人并发、写入失败、重载交错 | 不重复 member、不丢旧模板；待就绪状态不走新人分支 |
| 权限回归 | account != member，多账号既有授权、撤销、云台换绑定 | 不因换绑定获得历史资料；APP 入口永不自动建档 |
| 性能与恢复 | 在指定 CPU/GPU 上逐级小规模库、少量并发，测冷/热启动和重启 | 实际 provider、RSS/显存、端到端 p50/p95/p99、超时、索引可见时间 |
| 故障与迁移 | 算法不可用、库为空但业务有映射、模型更新、备份恢复 | 失败关闭身份准入；版本隔离；旧特征不能混用新模型 |

真实权重推理与压力测试需要另行执行；先小规模、限制并发，未达资源预算不扩大。业务需在 PoC 前确定允许误接纳风险与时间预算，不能事后为通过测试调低阈值。30–50 人不足以证明万分之一等级的误识率，结果只适合发现问题和筛选接法。阿里云和自托管用同一批合规样本、相同分组与指标比较，不比较厂商宣传值。

## 11. 完成情况

已完成仓库定位、隔离评审、代码/路由/持久化静态核查及官方模型许可/API 复核。运行环境、真实权重文件、额外商业许可、真实设备表现、容量延迟与故障恢复均仍待验证。没有修改业务代码或澜皙网页，没有上线、合并、推送或触达第三方。

采纳建议前的决策顺序：先确认供应方案可用权利与设备 PoC，再确定身份适配协议和人员引用，最后单独安排实施。当前证据支持“本仓库可作自托管原型参考，不能直接作为 MVP 身份准入服务”。
