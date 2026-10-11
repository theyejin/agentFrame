# 运营控制台（`dashboard/`）

- 用途：本地可访问的多人任务管理页面（L3），以及 L2 要求的执行轨迹报告页。
- 不放什么：不放业务逻辑实现（页面只调用本地数据与 Agent 接口）。

## 计划内容

- index.html（控制台首页）
- pages/（文案生成/分镜/图片/视频/发布/数据各功能页）
- build-log.html（执行轨迹报告页）
- assets/（样式与脚本，代码保留注释）

## 维护提示

- WP-08 / WP-11 落地；页面代码必须保留注释（R-L2-08），改动同步更新本目录 README 与 `docs/directory-and-files.md`。
- 任何增删改都要同步更新 `docs/directory-and-files.md`（R-L2-09）。
