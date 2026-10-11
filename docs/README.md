# 文档区（`docs/`）

- 用途：存放需求规格、讨论留痕、Skill 与目录设计、以及《目录及文件说明》。
- 不放什么：不放代码实现、不放运行期产物。

## 文件一览

| 文件 | 用途 |
| ---- | ---- |
| `requirements-spec.md` | **唯一需求来源**（冻结基线，条款编号 R-xx-xx / C-xx / AC-x） |
| `discussion-record.md` | 讨论留痕，9 字段节点 N001…（过程可追溯） |
| `skill-roster.md` | Skill 岗位名册：18 个执行岗位 + 7 个支撑件 |
| `skill-readme-contract.md` | 每个 skill 的 SKILL.md / README.md 必填模板与机器可判定校验词汇表 |
| `directory-structure-plan.md` | 目录结构提案与分步落地顺序（已确认，见 N005） |
| `directory-and-files.md` | **《目录及文件说明》正式版**，随增删改同步（R-L2-09） |

## 维护提示

- 需求条款变更：先追加讨论节点，再改 `requirements-spec.md` §0.1 修订记录。
- 文件增删：同步 `docs/directory-and-files.md`。
