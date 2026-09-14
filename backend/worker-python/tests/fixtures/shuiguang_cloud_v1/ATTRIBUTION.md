# shuiguang_cloud_v1 联调资料（用户提供，合同草稿）

- 来源：用户于 2026-09-14 明确授权用于 D 包真实 AI 方案接口联调的三份本地资料（精确路径授权，仅读取这三份；监督已核验原始 SHA256）。
- 性质：**接口合同草稿 + 结果样本**。`response_example.json` 是 shuiguang_cloud_v1 成功响应样本（数量与分数来自当前网页样本；task_id/图片 ID 为联调示例）；**云端算法服务尚未实现**——本样本**不是**算法在线运行证据，示例分数（如 17.6）不得固定用于新照片。
- 原始文件 SHA256（提供时监督核验值，本目录副本已核对一致）：
  - response_example.json: f533781f07867f6eb93dd9a3d46f1937111dfe6a940b7cebba30551edc52cb6f
  - response_models.py（此处存为 response_models.reference.py，仅作参考文档，**不得 import/执行**）: c6ac30dd90f38f1c4a941efaec01cca7c63903620dde6a3885d221b62e7b9413
  - 字段说明.md: dcba1490c10e1fdab2da1eae724052a6f0ffe926ce54f5e117e42b538b5059ee
- 必须保留的语义（用户指令）：score 越高表现越明显；null=不可评估且不同于 0；三视图不可求和；左右以受检者本人为准；surface_gloss 沿用 v2_oiliness_tendency 口径（含油光与卟啉证据），不得描述成纯油光总分；样本不含标注图 URL，仅 views 图片 ID。
- 本目录不记录任何绝对下载路径；不进入运行配置或生产代码。
