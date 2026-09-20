# RK3576三功能项目交接包 — V0.0.1

交接日期：2026-09-07。面向同事及同事电脑上的Codex。目标环境：**Windows + WSL2 Ubuntu 22.04，Python 3.10**。

> 这是可继续开发的电脑端基线与板端迁移参考包，不是已验收的RK3576固件或一键板端安装包。当前状态：`PC_FUNCTIONAL_BASELINE / RK3576_NOT_DEPLOYED`。

## 1. 同事应该拿哪个文件夹

**只复制整个本交付文件夹。不要同时复制原项目、原实验目录或整个D盘，也不要只拿其中的网页。** 本包未压缩，约83MiB级别，最终文件数和大小以 `manifests/package_files.json` 为准。

包内已经包含运行所需的模型权重和代码，不包含虚拟环境、安装wheel、训练数据、个人摄像头照片、私有账号密码、Git仓库、编译缓存。安装依赖首次需要联网；模型文件无需重新下载。Windows浏览器拿摄像头，WSL本地推理，不需要云服务。

同事Codex按顺序阅读：

1. 本README：环境、运行、操作和排错。
2. `TECHNICAL_HANDOFF.md`：模块、模型契约、状态机、已知风险和RK3576技术路线。
3. `CODEX_START_PROMPT.md`：可直接粘贴的接手提示词。
4. `VALIDATION.md`：本次打包验证及尚未完成的验收。
5. `manifests/source_inventory.json`：原始来源、未提交快照及哈希。

## 2. 当前到底实现了什么

| 负责人描述 | 本包真实能力 | 边界 |
|---|---|---|
| 目标检测 | V5旧医美仪器检测框、V5接触点、接触点脸部分区 | 不保证新外观仪器有效；2D落点不证明物理接触 |
| 拍照 | 角度达标、画面质量与稳定门禁后，左右各保存一张触发帧；支持重拍 | 没有真实云台控制，当前由人转头/手持摄像头模拟 |
| 人脸识别 | YuNet人脸检测、空间锁定、FSA-Net角度估计；设备模式含MediaPipe分区 | **没有身份注册、特征库或1:1/1:N身份认证** |
| RK3576部署 | 附旧RK3568 C++、转换工具和模型导出参考 | **尚未完成RK3576模型转换、实板运行或稳定性验收** |

功能模块不等于神经网络数量：PC运行含设备、接触点、YuNet、FSA-Net、MediaPipe五个模型文件；拍照本身是业务状态机，不是单独一个“拍照模型”。

两种页面模式互斥：①人脸自动拍照；②旧仪器检测+七区叠加。当前不是目标检测和自动拍照同时并行；后续是否需要同时运行，应由负责人确认性能和行为要求。

## 3. 目录

```text
交付包根目录/
  README.md                    使用指南（本文件）
  TECHNICAL_HANDOFF.md          技术路线、接口及剩余工作
  CODEX_START_PROMPT.md         给同事Codex的提示词
  VALIDATION.md                打包验证边界
  VERSION                     0.0.1
  setup.sh / start.sh           独立WSL环境安装/启动
  启动_WSL.ps1 / 打开网页.cmd  Windows入口
  requirements-*.txt           CPU/CUDA安装入口与原环境快照
  pc_demo/
    server.py                  本机HTTP服务
    lab/                       模型组合、角度滤波、拍照门禁、七区
    vendor/                    原有目标检测/人脸角度源码快照
    web/                       独立联调页
    models/                    五个PC模型和哈希
    tests/                     13项Python回归及JS显示测试
    tools/                     真实模型烟测
    captures/                  运行后生成；本包不携带个人照片
  rk3568_reference/            历史板端参考，禁止直接当RK3576发布包
  docs/source_notes/           有用的历史说明；绝对路径仅用于追溯
  licenses/                   已找到的YuNet/FSA-Net许可证原文
  manifests/                  文件来源、模型与环境、包校验清单
  tools/                      环境检查、包完整性验证
```

## 4. 首次安装：先明确自己在哪个终端

### 4.1 Windows PowerShell：确认WSL

```powershell
wsl --list --verbose
```

确认目标发行版是WSL2，名称可能是 `Ubuntu-22.04`、`Ubuntu` 或自定义名称。下面脚本默认 `Ubuntu-22.04`，实际不同就替换。不要误进入其他发行版改环境。

建议将包复制到 `D:\RK3576_Handoff` 等便于输入的目录；目录也支持中文。WSL中D盘对应 `/mnt/d/`。不必把摄像头USB透传到WSL，因为摄像头由Windows浏览器采集。

### 4.2 Ubuntu 22.04终端：基础依赖

以下系统包安装应由同事确认授权后执行，不要在未知服务器上照抄：

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip libgl1 libegl1 libglib2.0-0 libportaudio2
cd /mnt/d/RK3576_Handoff
python3 --version
python3 tools/verify_package.py
```

预期Python 3.10。最后一条只用标准库，可在安装模型依赖前验证拷贝是否完整。

### 4.3 选择一种环境，不要混装CPU/GPU版ORT

**无NVIDIA GPU或先排通依赖：**

```bash
bash setup.sh cpu
```

CPU可用于功能/接口检查；设备模型速度可能较慢，实时拍照的帧间隔门禁仍有效，因此不能据CPU慢速运行推断板端性能。

**有NVIDIA GPU且WSL能看到GPU：**

```bash
nvidia-smi
bash setup.sh cuda
```

CUDA入口使用 `onnxruntime-gpu[cuda,cudnn]==1.23.2`；驱动仍需要宿主Windows提供。不要在WSL中盲目安装或覆盖内核显示驱动。两种入口都会建立**本包根目录 `.venv`**，不依赖原作者环境，也不修改系统Python。

`setup.sh`发现已有`.venv`会拒绝继续，以免混装。若安装中断，先查看错误，再由同事Codex在明确路径内修复该独立环境；不要删除整个交付目录，不要覆盖原作者工作目录。

依赖版本来自实测环境。`requirements-wsl-cuda-observed.txt`是完整依赖闭包和NVIDIA包快照，**不是首次安装推荐命令**：原环境存在两个OpenCV发行包，因此标准安装入口只选opencv-contrib-python，避免重复覆盖cv2。顶层安装入口固定版本，但传递依赖未形成新机器已验证的通用锁；没有伪造uv.lock。同事首次成功安装后应记录实际依赖并生成该平台锁文件。若源站无某版本/架构wheel，停止并报告，不得悄悄升级全套包。

官方依赖参考：[ONNX Runtime CUDA说明](https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html)。

### 4.4 启动

在Ubuntu终端、包根目录：

```bash
bash start.sh
```

或在Windows PowerShell、包根目录：

```powershell
.\启动_WSL.ps1 -Distribution Ubuntu-22.04
```

保持启动窗口开启，看到 `Uvicorn running on http://127.0.0.1:8876` 后，在 **Windows Edge/Chrome** 打开：

<http://127.0.0.1:8876/>

Windows原生Python路线暂未验收，不是首选。若PowerShell脚本被策略拦截，可直接使用Ubuntu终端的 `bash start.sh`，不要为了运行一个脚本全局放宽系统执行策略。Ctrl+C停止服务；没有安装开机自启或后台守护服务。

## 5. 页面怎么用

### 人脸自动拍照

1. 选择“人脸自动拍照”，选择摄像头并允许权限，点“开启摄像头”。先单人正面锁定。
2. 输入“目标侧转角度”和“允许误差”。例如目标30°、误差±5°，左右分别接受25–35°。点“应用参数·新一轮”才生效。
3. 默认45°±5°、稳定500ms、俯仰/歪头±12°。高级设置可调倾斜上限与稳定时间；不要只看Yaw而忽略拒拍提示。
4. 缓慢转头，或让摄像头绕头部移动并持续朝向人脸；在目标附近停留。仅旋转镜头朝向不等于改变观察侧脸角度。
5. 数字每秒显示一次；实际推理、进度和拍照每帧处理。稳定值采用中值+EMA；展开“原始角度诊断”可查看模型原始输出。
6. 当前原始帧和稳定值都达标才保存，避免滤波滞后误拍。左右各一次，可单侧重拍。
7. 照片/元数据在 `pc_demo/captures/<会话ID>/`。保存的是上传到推理服务的同一JPEG，含raw_pose、pose、实际参数和帧哈希。

“应用参数”或重置会开始新一轮并清空当前预览，不删除磁盘照片；刷新恢复默认设置。左右符号必须实拍核对，目前负Yaw标为本人左侧。空间锁定不是身份识别，丢脸超过350ms或检测歧义需要手动重置；多个网页同时开启会使旧会话失效。

曾经出现持续拒拍的原因之一：俯仰估计超过12°；一次300帧记录中246帧因此被挡住。先调整摄像头高度，确需接受更大倾斜再主动调高级设置。滤波不能纠正角度模型的系统偏差。

### 旧仪器检测及脸部七区

1. 切换“旧仪器检测”，让旧仪器及单个人脸出现在画面中。
2. 可开关分区叠加、468关键点、接触点显示。颜色对应额头、眼周、鼻、本人左/右脸颊、嘴周、下巴。
3. 接触点落区依据未镜像原图；自拍镜像只改变绘制。
4. 额头上缘沿脸轴扩展，内部区域连续覆盖，眼睛开口和嘴唇排除。**不是精确皮肤/发际线分割**，刘海、遮挡、侧脸仍可能误覆盖。
5. 没有皮肤诊断、产品推荐或注射位置建议。未来皮肤算法需单独接入，几何分区不能直接作为医疗美容治疗安全区域。

## 6. 测试

在包根目录、Ubuntu终端：

```bash
.venv/bin/python tools/check_environment.py
.venv/bin/python -m unittest discover -s pc_demo/tests -v
.venv/bin/python pc_demo/tools/smoke.py
```

可选真实人脸图片（自行提供，有授权且不上传）：

```bash
.venv/bin/python pc_demo/tools/smoke.py /path/to/face.jpg
.venv/bin/python pc_demo/tools/smoke_regions.py /path/to/face.jpg /tmp/face-regions-check.png
```

若安装了Node，可执行无第三方依赖的显示刷新测试：

```bash
node pc_demo/tests/test_angle_display.mjs
```

真实模型烟测中的空白设备图只验证无目标和模型可运行，不代替旧仪器正样本精度测试。包里没有私人人脸样例或金标准图片，不能直接复现历史数据集精度指标。

## 7. 常见故障

| 现象 | 检查与处理 |
|---|---|
| 网页打不开 | 先确认终端服务未退出；Windows `curl.exe http://127.0.0.1:8876/health`；WSL `ss -ltnp 'sport = :8876'`。地址必须http、本机8876，不是https或旧8090端口 |
| 端口被占用 | 查具体PID，确认是不是本系统；不要杀全部Python/WSL进程。可临时 `LAB_PORT=8877 bash start.sh` 并手动打开8877地址；默认Windows打开网页入口仍为8876 |
| 页面有但摄像头没反应 | 使用Windows Edge/Chrome，允许网站和系统摄像头权限，关闭其他占用程序；15秒后应出现超时说明 |
| 页面是旧版 | Ctrl+F5刷新并重新开启摄像头，当前预览会清空但磁盘照片仍保留 |
| CUDA不生效 | 看 `/health` 实际provider，不只看 `nvidia-smi`；CPU回退不能宣称GPU运行。检查ORT/CUDA/cuDNN版本与加载日志 |
| 无法拍照 | 看进度下拒拍原因；逐项查目标/容差、pitch/roll、清晰度、脸尺寸、帧间隔、过期、失锁、当前原始角度 |
| CPU机器稳定进度总清零 | 有效帧间隔可能超过350ms；先测真实耗时，调整实验策略需记录，不能直接删除全部门禁冒充通过 |
| 模型哈希错误 | 重新核对包完整性及模型文件，不要直接改SHA256绕过验证 |
| 部分第三方版本无法安装 | 保存完整报错，核实Python3.10/平台/PyPI源；只在独立环境做有记录的兼容修复 |

## 8. 版本、授权与交接边界

V0.0.1是负责人要求的新软件基线，V5是模型训练谱系，不是第五个软件发布版本。实验V2–V8不直接转成软件大版本。未来纯修复递增末位、兼容功能增加中位、架构不兼容增加首位；是否正式发布与打标签，必须先通过验收。

本包仅供授权同事内部研发。许可证原文与来源说明一并保留；模型训练数据、上游权重与商业分发授权仍需项目方复核。本包不表示已完成全部对外分发合规审核。

本轮未修改原数据提取/采集/审查页面；它们不属于同事运行联调的必要依赖，因此没有重复打包。如后续需要重新训练，再单独申请数据、标注、checkpoint和训练代码，不能从本包虚构出来。
