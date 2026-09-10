# 本项目工作约定

用户于 2026-09-10 明确指定：后续工作只在 `contest2026_483_yuanxinshixisheng` 项目内进行。

- 后端工作目录为 `backend/`，当前后端设计唯一维护位置为 `backend/doc/`。
- 开始后端工作先阅读 `backend/doc/README.md`，以及任务涉及的技术、数据、详细设计和已确认决策。
- Markdown/draw.io 是文档源，`backend/doc/site/` 是文档网站源码，`backend/doc/web/` 是构建后的静态网页。
- 当前文档只保留每类最新版本；不要新建“第几版”快照目录或编辑器备份。历史使用 Git 追溯。
- 不继续编辑 openvela 外层旧文档目录，不为本项目实现修改 ai-skin-backend 或 ai-skin-backend-v2。
- 网站归本项目 Git 管理，不在 site 内创建嵌套仓库；不把整个本项目推到 Sites 的源码仓库。确需发布时从已提交版本导出 site 子目录到独立临时发布目录。
- 遵守已有分支协作规则；不要覆盖用户未提交文件。本次迁移不改变现有分支、不自动推送或发布。
