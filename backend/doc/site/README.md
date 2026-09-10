# 后端文档网站源码

文档源位于上级 `backend/doc/`；本目录与静态产物 `../web/` 统一归项目 Git 管理。没有嵌套 Git，不依赖原工作区目录。

## 更新和运行

```bash
npm ci
python3 scripts/import-docs.py
npm run build
```

`postbuild` 自动将公开静态产物导出到 `../web/`。本地运行：

```bash
python3 -m http.server 3000 --bind 0.0.0.0 --directory ../web
```

已有依赖无需每次安装。需要源码开发预览时使用 `npm run dev -- --host 127.0.0.1`。

十个目录：详细设计、人脸调研、技术架构、数据架构、测试清单、运行组件、五模块、用例、流程、API。文档下载及当前四份 draw.io 随静态页面打包。`lib/source-manifest.json` 记录导入依据，原文修改后必须重新导入构建。

## 托管

`.openai/hosting.json` 保留原 Sites project_id，仅迁移不发布、不改变访问权限。之后明确要求发布时，从本项目已提交内容导出此 site 子目录到临时发布工作区，按 Sites 技能推送该站点的精确源码并打包部署。不要将整个项目推到站点源码仓库，不在本目录创建嵌套 `.git`。导出目录需要同时携带旁边的文档源以便重导入；发布构建的 `postbuild` 导出仅为静态副本，不是额外站点。
