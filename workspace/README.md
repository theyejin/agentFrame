# 运行期工作区（`workspace/`）

- 用途：一条 topic 的全部运行期产物：文案、分镜、图片、视频工程、发布包。
- 不放什么：整个目录不入库（已在 .gitignore），里面的东西可随时删、可重建（除 artfacts 表登记的关键产物需另行备份）。

## 计划内容

- topic-<id>/copy/、storyboard/、images/、video/、publish/

## 维护提示

- 对外只以 `artifacts` 表的路径字段引用，不要写死绝对路径。
- 任何增删改都要同步更新 `docs/directory-and-files.md`（R-L2-09）。
