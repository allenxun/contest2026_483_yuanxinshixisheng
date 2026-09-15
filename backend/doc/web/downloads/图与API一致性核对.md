# 图与 API 一致性核对

本轮已同步测试需求决策 D01-1—D01-7：先查询后主动绑定、原账号解绑、云台唯一当前任务、重启/跨次恢复、受理新任务立即替换、先停止收尾再测肤。

## 当前有效文件

- 后端模块图-V4-五模块.drawio
- 后端用例图-V8-APP与云台控制.drawio
- 后端流程图-V4-APP与云台控制.drawio
- 后端组件图-V5-部署式运行视图.drawio
- 后端API接口设计-V1-五模块与流程对应.md
- 测试场景清单-V1-五模块与双控制.md
- 测试需求决策记录.md

## 当前数量与接口变化

五模块共 27 个对外 HTTP API：M1 3 个、M2 8 个、M3 6 个、M4 9 个、M5 1 个。新增 M2-A07 绑定状态查询、M2-A08 原账号解绑、M3-A06 恢复云台当前任务。M3-A04 只向授权 APP 开放；云台 M3-A03/A05 与 M4-A03/A04/A08 均受当前任务约束，历史执行只保留最小对账能力。

## 实际图中位置

| API | 流程图页/节点 | 用例图页/节点 |
| --- | --- | --- |
| M1-A01 | 05/request | 01/faceaccess |
| M1-A02 | 05/view | 01/faceaccess |
| M1-A03 | 05/revoke_grant | 01/revoke_access |
| M2-A01 | 00/authreq；01/request | 02/auth |
| M2-A02 | 01/beat | 02/beat |
| M2-A03 | 01/reply | 01/device；02/beat |
| M2-A04 | 00/caps；07/capabilities | 02/caps；03/device |
| M2-A05 | 07/capabilities | 02/caps；03/device |
| M2-A06 | 00/network；01/binding_request | 01/bind_gimbal |
| M2-A07 | 00/network；01/binding_status_request | 01/bind_gimbal |
| M2-A08 | 01/unbind_request | 01/unbind_gimbal |
| M3-A01 | 00/capture；02/upload | 01/measure；02/task |
| M3-A02 | 00/capture；02/upload | 01/measure；02/task |
| M3-A03 | 02/retake；02/feedback；02/current_task_continue；03/briefreportq | 01/measure；01/briefreport；02/task |
| M3-A04 | 00/appreport；03/fullreportq | 01/fullreport |
| M3-A05 | 00/appreport；02/feedback；03/fullreportq；03/briefreportq | 01/fullreport；01/briefreport |
| M3-A06 | 02/current_task_request | 01/restore_current |
| M4-A01 | 00/appplan；03/fullplanq | 01/fullplan |
| M4-A02 | 00/appplan；03/fullplanq；06/return | 01/fullplan |
| M4-A03 | 00/register；02/current_task_continue；03/briefplanq；03/readsection；04/request；06/return；07/face；07/app_no_resume | 01/briefplan；01/appcare；02/execution；03/identity；03/execution；03/note |
| M4-A04 | 04/verifyagain；04/notes；04/revalidation_result；06/return；07/app_revalidation | 02/execution；03/revalidation |
| M4-A05 | 00/state；01/reconcile；04/sync；04/resume_existing；04/reject_resume；06/upload；07/sync；07/save；07/app_offline_continue | 01/register；02/state；03/progress |
| M4-A06 | 07/closure_confirm | 02/state；03/closure |
| M4-A07 | 01/reconcile；07/show | 03/records |
| M4-A08 | 00/recordview；03/recordq；06/show；07/show | 01/records；01/register；03/records |
| M4-A09 | 00/recordview；03/recordq；07/show | 01/records；03/records |
| M5-A01 | 01/notification_destination_request；01/binding_result | 01/notification_destination |

## 核对范围

核对 XML 节点与连线引用、27 个 API 双向图中覆盖、接口文档的实际流程节点映射、94 个测试场景及其 API 覆盖。网页从当前源文件重新导入，保留已有 Actor 透明背景及用例直线。类型与静态构建另行检查；这些检查不等于真实客户端联调或浏览器视觉验收。

## 历史文件

旧模块/组件图、“第八版”快照和编辑器备份已从当前文档集移除；只维护上列有效文件，历史通过原文档 Git 提交追溯。

## OSS 补充核对

运行组件由四个变为五个，新增 OSS，包含 Web 上传照片写入/读取和异步程序原图读取/结果图保存连线。测试 SC-C-05 覆盖三类图片、权限与保存失败，仍为 94 个场景、27 个 API。

## 本轮交叉检查：发现与补齐

1. 模块图缺少图片归属职责：补 M1 授权照片、M3 原图/结果图、M4 核验照片；OSS 仍是共享组件，不新增业务模块。
2. 测肤流程跳过 OSS：补原图保存/校验 → 分析、结果图归档 → 报告就绪，以及存储失败分支。受理后的失败不回退当前任务。
3. APP 与云台授权/执行核验照片路径不清：补流程 04/05/07 与相关用例；APP 测肤仍为非 MVP。
4. API 只泛写受控引用：补 M1-A01、M3-A01/A02/A05、M4-A03/A04 的用途、OSS 归属、结果图返回和失败约束。HTTP API 数量仍 27。
5. 模块流程对照中报告列表角色不清：明确 M3-A04 仅 APP，云台 M3-A03/A05 仅当前结果。

仍需开发落地（不要求用户逐项决策）：照片传输格式/直传协议、图片下载鉴权及已发凭证失效、通知目标与登录退出的关联。详见接口文档 6.5。此次只校验设计与数据结构，不宣称业务接口或设备行为已经实现。


## 2026-09-15 增量核对

- 当前 Java `ApiDocsCatalog` 与网页 API 清单均为 **36** 个操作：M1—M5 共 29 个，B0 基础/联调协议 7 个。
- 新增稳定编号：`M2-A09 POST /api/v1/gimbal-ai/messages`、`M3-A07 GET /api/v1/skin-assessment-tasks/{taskId}/report-narration-stream`、`B0-A01—B0-A07`。
- 用例图新增 08 页；模块图新增 02 页；流程图新增 08 页。新增页保留明确节点 ID，API 文档中的 `08/node_id` 引用已经机器校验。
- `site/scripts/import-docs.py` 提取 Java catalog 的方法/路径并与 Markdown 全量比较；catalog 再由 `ApiDocsCoverageIT` 对实际 `/v3/api-docs` 做覆盖率门禁。
