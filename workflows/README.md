# 流程编排定义（`workflows/`）

- 用途：四条线各自的流程描述与端到端流程，说明每一步交给哪个 skill、什么条件下推进。
- 不放什么：不重复写 Skill 内部逻辑（那份在 skill 的 README.md）。

## 计划内容

- README.md（流程清单与触发方式）
- 四条线流程文件 + 端到端流程文件

## 维护提示

- 改流程必须同步重新生成受影响的 archify 图（规格 §15）。
- 任何增删改都要同步更新 `docs/directory-and-files.md`（R-L2-09）。
