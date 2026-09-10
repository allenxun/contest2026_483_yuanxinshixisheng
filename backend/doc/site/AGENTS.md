# 文档站点范围

站点唯一可编辑源码位于本项目 `backend/doc/site/`，上级 Markdown/draw.io 是内容来源。使用 Sites 技能维护；构建后自动导出 `backend/doc/web/`，原目录冻结不再编辑。

本站归本项目 Git 管理，不初始化嵌套仓库。托管发布应从已提交的 site 子目录导出独立临时站点工作区，不能推送本项目的完整 Git 树到 Sites。保留现有 project_id 和访问范围；用户要求迁移或编辑不代表自动发布。
