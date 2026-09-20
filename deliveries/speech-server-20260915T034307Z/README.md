# K7 常驻服务器语音服务

状态：部署包准备中；未登录服务器、未部署、未切换板端地址。
目标优先 10.3.3.170。2026-09-15 只读检查 SSH 返回 Ubuntu OpenSSH，18085 业务接口可达，但 8000 拒绝连接。10.3.3.68 同样 SSH 可达、8000 拒绝连接。不能排除其他地址/端口部署。

## 构建包

在统一项目执行 `python tools/package_speech_server.py`。它只复制指定源码，不复制 .env、日志、录音、模型或虚拟环境，并生成每个文件的 SHA256。交付目录见脚本输出。

## 服务器启动

需先确认 SSH 登录账号/密钥和服务器具有 Docker Compose；不要覆盖 18085 业务服务。
解包到独立目录。将现有 speech-service 的有效配置通过已验证 SSH 私密传输到 `speech.env`，权限设为 600，不能放入镜像或 Git。桥容器不接收云端密钥。

```sh
export K7_BIND_IP=10.3.3.170
docker compose config --quiet
docker compose build
docker compose up -d
docker compose ps
curl --fail http://127.0.0.1:8000/health
```

8000 只绑定服务器本机；8001 只绑定指定内网地址。当前 K7S1 是单板调试协议、无 TLS/设备认证，不得映射公网；部署前检查实际网络/容器防火墙策略允许设备网段且拒绝非可信来源。面向公网产品仍需板端 TLS/设备认证，不能宣称生产安全完成。

服务使用现有阿里云配置；流式入口 `/asr/stream` 默认 paraformer-realtime-v2，不是批量 `/asr`。桥默认不启用 echo-test，TTS 播放请求文本。

## 验收和切换

health 成功仅代表进程在线，不代表云端凭据有效。还须验证 WebSocket ready/partial/final/completed、TTS 返回 16k 单声道 S16LE PCM、K7 从目标服务器上传并实播、停止 Windows 桥后仍成功。确认服务器链路后再将板端目标从 10.3.1.125 改为服务器地址。没有这些证据不能标记独立部署通过。

撤回本次新增容器用 `docker compose down`，保留原 Windows 服务可恢复测试。不要操作其他项目容器。部署语音网关不等于把整机流程搬上服务器：云台/相机/命令流程应在 openvela 板端运行。
