# 来源、裁剪与复现范围

只读核对了原 `E:\openvela\语音模块\openvela-voicelink` 与主仓 work-in-progress 的 llama/B0 文件名和源码/文档引用，排除模型、构建、venv、运行时和旧证据内容；未发现已有 llama/B0 源码工程。原 VoiceLink 的已有构建缓存存在，但没有把它当作 llama 运行证据。主任务方案也明确未找到既有 B0。此搜索是本地指定范围，不声称覆盖整台电脑。

官方来源为 [ggml-org/llama.cpp 的 b5046](https://github.com/ggml-org/llama.cpp/tree/b5046)，`git -c http.sslBackend=openssl ls-remote` 核对 tag 对应 `74d4f5b041ad837153b0e90fc864b8290e01d8d5`。默认 schannel 首次连接失败（SEC_E_NO_CREDENTIALS），改用 Git 支持的 OpenSSL 成功；未关闭证书校验。下载固定提交的官方 codeload 源码包 20,880,037 字节，SHA-256 `8dd9fcc7c17f972673960ffdcc7521f52de5a9ec594aa6acebd9dfd8c17c0a5c`，详见 VERSION.json。选旧固定版本作为此 B0 可复现基线，不声称为最新版本或生产推荐；升级必须重做 API/依赖核对。

源码原封保留在 vendor，含原 LICENSE（MIT，ggml authors）及第三方许可。candidate/ggml-backend-reg.cpp 从该源码派生，继承原许可；对应最小变更在 candidate/static-registry.patch，由 scripts/static_registry.py 确定性生成。没有第三方镜像、预编译 llama 库或模型权重。源码包可能含上游词表/测试资源，这些不是已部署的 Qwen 模型。

上游提交的 src/llama-arch.cpp 有 qwen2 架构入口，但本轮没有权重，不能由架构名称推断所选 Q4_K_M 文件兼容性已验证。Qwen 权重的具体 revision/SHA/许可仍由后续 B0-c 固定；不借用用户示例配置里的空字段作完成记录。

裁剪由根 CMakeLists.txt 完成：BUILD_SHARED_LIBS=OFF；CPU开启；common、examples、tests、server、curl、GPU/RPC/BLAS/llamafile/KleidiAI/OpenMP关闭；不按本机自动 native 优化。实测 39 个编译单元，不构建联网/HTTP服务。保留四个静态 archive 和 C API 链接探针。并非把所有模型架构/离线量化对象都裁掉的最小体积实现。

静态 registry 仍采用上游 C++ 容器和注册接口；load_all 仅确保静态注册初始化，load 返回 NULL 并明确记录“不支持”，路径扫描/卸载拒绝。上层应仅用静态 CPU init，注册变化不可并发发生。这些是被明确禁用的 ggml 功能，不是伪造系统调用成功。没有改 vendor 或在正式源码应用补丁。

CMake工具来自 PyPI `cmake==3.31.6`，安装在本目录 tools/python；编译器为现有 MinGW GCC/G++ 12.2.0。完整源码归档哈希是来源锁；source-manifest.json 是解包文件校验入口。源码包没有独立 .git，构建脚本设置 GIT_CEILING_DIRECTORIES 避免错误读取主项目 HEAD，所以上游日志中的 git “not a repository” 与 unknown build commit 不是编译失败，也不能拿主仓提交号冒充 llama 版本。

重新构建：当前交付无需重新下载源码；直接运行 scripts/build.py。新目录从锁定包准备时运行 scripts/prepare.py，已有源码则拒绝覆盖。如需要安装工具，使用 Python `-m pip install --no-cache-dir --no-deps --target tools/python cmake==3.31.6`。此工具安装来源和源码下载都只用于主机准备，不联系模型服务。
