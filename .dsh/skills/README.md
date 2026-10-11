# Skill 模块（DSH 技能根目录）（`.dsh/skills/`）

- 用途：25 个可独立执行的 skill（18 个执行岗位 + 7 个支撑件），每个只做一件事：输入 → 处理 → 输出。
- 不放什么：不放流程判断（属于 Agent）、不放跨 skill 编排逻辑。

## 计划内容

- 每个 skill 一个目录，目录内固定三个文件：SKILL.md（DSH 自动发现的入口，带 name/description frontmatter）、README.md（给人看的通俗说明，按 docs/skill-readme-contract.md 九段模板）、run.py（实现入口）

## 维护提示

- **本目录是 DSH 的 skill 发现根目录**（2026-10-12 已实测：放入目录并写好 SKILL.md 后，会话技能目录即刻可见）。改名会失去自动化发现能力。
- 任何增删改都要同步更新 `docs/directory-and-files.md`（R-L2-09）。
