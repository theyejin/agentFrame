# Skill 岗位名册（Skill Roster）

> 对应需求：R-L1-12（Skill 岗位与数量设计）、R-L1-05~09（模块化执行）、R-L1-18（交接契约写在 README 并由运行时校验）。
> 对应讨论节点：N004（2026-10-12）。
> 上游文档：`docs/requirements-spec.md`（需求唯一来源）、`docs/skill-readme-contract.md`（README 模板）、`docs/directory-structure-plan.md`（目录提案）。
> 配图：`.archify/FLOW-COPY-20261012/`、`FLOW-VISUAL-20261012/`、`FLOW-VIDEO-20261012/`、`FLOW-PUBLISH-20261012/`。

---

## 1. 岗位总数与口径

| 口径 | 数量 | 说明 |
| ---- | ---- | ---- |
| **Skill 岗位总数** | **18** | 可执行的原子能力；一个 skill 只做一件事，可被单独测试与替换 |
| 编排者工具（编排者专属调用） | 2 | `task-decomposer`、`summary-writer`，只服务编排者，不对环节开放 |
| 执行类 Skill（四条线） | 11 | 文案线 2 / 视觉线 3 / 视频线 5 / 分发数据线 3（其中 `title-cover-prep` 计入视频线，发布前准备归视频线） |
| 基础设施类 Skill | 5 | `llm-adapter`、`prompt-registry`、`artifact-recorder`、`hotspot-collector`、`table-builder`（后两者同时服务分发数据线） |
| 质量门 / 校验器 | 3 | `storyboard-validator`、`image-consistency-checker`、`publish-guard`（只做校验、不改内容，是「交接契约」的执行者） |
| 人工关口（不是 skill） | 3 | 关口① 选定文案 / 关口② 剪辑干预 / 关口③ 发布授权；由 `hitl-gate` 统一承接，不各自实现 |
| 首版落地 | **18 个全部落地** | 首版一律只实现「单条链路 + 最小字段」；扩展能力（多平台批量、多模型投票）显式推迟 |

> 结论一句话：**Skill 数量 = 18 个执行岗位 + 1 个通用关口承接器（hitl-gate）**；编排者自身不算 skill 岗位，它的两个工具单独列。

---

## 2. 命名规则（通俗、可读、可搜索）

- Skill 目录名 = `skill_id`，使用**小写英文 + 连字符**，含义一眼可猜：`copy-writer`、`storyboard-builder`、`video-exporter`。
- 每个 skill 目录内**固定三件套，文件名固定，不另起名字**（决策 D-07，N005 实测确认）：
  1. `SKILL.md` —— DSH 自动发现入口（工作区 `.dsh/skills/` 就是 DSH 的技能根目录）。必须是 YAML frontmatter + Markdown 正文：
     ```markdown
     ---
     name: <skill_id>
     description: "<一句话说明能力>。Use when <什么时候该用它>。"
     ---
     ```
     `name` 必须与目录名一致；`description` 决定编排者能否选中它，必须写清「什么时候用」。
  2. `README.md` —— 给人看的通俗说明，按 `docs/skill-readme-contract.md` 的九段模板填写（运行时校验规则也读这里）。
  3. `run.py` —— 实现入口（或 `index.ts`），便于运行时统一加载。
- 不用缩写（`cw`、`sb` 一律禁止）、不用版本号进目录名（版本进 `README.md` 的表格与 `SKILL.md` 的变更记录）。

---

## 3. 名册总表（18 个岗位）

| # | skill_id | 中文岗位名 | 归属 | 一句话职责 | 首版计划 | 已落地 |
| - | -------- | ---------- | ---- | ---------- | -------- | ------ |
| 1 | `copy-writer` | 文案生成 | 文案线 | 一套输入生成 3 套不同侧重点文案 | ✅ | ✅ 步骤 4 |
| 2 | `storyboard-builder` | 分镜拆解 | 文案线 | 选定文案 → 24 条分镜场景（6×4） | ✅ | ✅ 步骤 4 |
| 3 | `reference-image-builder` | 参考图生成 | 视觉线 | 文案 → 1–3 张风格参考图 | ✅ | ✅ 步骤 5 |
| 4 | `grid-image-builder` | 整图生成 | 视觉线 | 24 条分镜 → 6×4 整图 | ✅ | ✅ 步骤 5 |
| 5 | `image-splitter` | 图片切分 | 视觉线 | 整图 → 24 张独立图 | ✅ | ✅ 步骤 5 |
| 6 | `asset-packager` | 素材打包 | 视频线 | 图文按分镜顺序打包成工程文件夹 | ✅ | ✅ 步骤 6 |
| 7 | `image-to-video` | 图生视频 | 视频线 | 图片序列 + 文案 → 视频草稿 | ✅ | ✅ 步骤 6 |
| 8 | `auto-editor` | 自动剪辑 | 视频线 | 参数化剪辑（顺序 / 时长 / 替换） | ✅ | ✅ 步骤 6 |
| 9 | `video-exporter` | 成片导出 | 视频线 | 导出 mp4 + 封面帧 | ✅ | ✅ 步骤 6 |
| 10 | `title-cover-prep` | 发布准备 | 视频线 | 按平台模板生成标题 / 标签 / 封面 | ✅ | ✅ 步骤 6（并复用于分发数据线） |
| 11 | `browser-publisher` | 浏览器填写 | 分发数据线 | 登录并填写发布信息，**停在发布前** | ✅ | — |
| 12 | `hotspot-collector` | 热点采集 | 分发数据线 | 按周期 / 关键词搜热点并留存原始数据 | ✅ | — |
| 13 | `table-builder` | 汇总成表 | 分发数据线 | 热点分类汇总成表格 | ✅ | — |
| 14 | `feishu-sync` | 飞书同步 | 分发数据线 | 表格 / 最终文档写入飞书 | ✅ | — |
| 15 | `metrics-collector` | 指标采集 | 分发数据线 | 采集播放量 / 互动量 / 涨粉数 | ✅ | — |
| 16 | `review-reporter` | 复盘报告 | 分发数据线 | 出复盘结论与优化建议 | ✅ | — |
| 17 | `llm-adapter` | 模型适配 | 基础设施 | 统一文本 / 图像生成调用接口 | ✅ | ✅ 步骤 3 |
| 18 | `prompt-registry` | 提示词注册 | 基础设施 | 提示词入仓、按版本取用 | ✅ | ✅ 步骤 3 |
| — | `artifact-recorder` | 产物登记 | 基础设施 | 写产物表 / 步骤流水表 / 留痕 | ✅ | ✅ 步骤 4 |
| — | `hitl-gate` | 人工关口承接 | 通用 | 三类形态（选择 / 调整 / 授权）、五个关口点统一实现 | ✅ | ✅ 步骤 4 |
| — | `storyboard-validator` | 分镜校验 | 质量门 | 24 条 + 编号连续 | ✅ | ✅ 步骤 4 |
| — | `image-consistency-checker` | 图片一致性校验 | 质量门 | 24 张齐全 + 编号连续 + 分辨率一致 | ✅ | ✅ 步骤 5 |
| — | `publish-guard` | 发布红线守卫 | 质量门 | 拦下任何自动发布（C-01 / C-08） | ✅ | — |
| — | `task-decomposer` | 任务拆解 | 编排者工具 | topic → task，派单给环节 | ✅ | — |
| — | `summary-writer` | 汇总回报 | 编排者工具 | 四条线结果汇总成一条回报 | ✅ | — |

> 落地进度：**「已落地」列**记录 `.dsh/skills/` 下真实存在的目录（三件套齐全、`run.py` 可跑）。截至 WP-05 步骤 6 已落地 **16 个**：基础设施 `llm-adapter`、`prompt-registry`；文案线 `copy-writer`、`storyboard-builder`；视觉线 `reference-image-builder`、`grid-image-builder`、`image-splitter`；视频线 `asset-packager`、`image-to-video`、`auto-editor`、`video-exporter`、`title-cover-prep`；支撑件 `artifact-recorder`、`hitl-gate`、`storyboard-validator`、`image-consistency-checker`。其余 9 个（分发数据线 6 个 + 支撑件 `publish-guard`、`task-decomposer`、`summary-writer`）在 WP-07 逐步落地，未落地前不在磁盘上（避免空壳目录）。

> 计数说明：上表 18 个「岗位」指**业务执行能力**；`artifact-recorder` / `hitl-gate` / 3 个校验器 / 2 个编排者工具是**支撑件**，合计 7 个目录，因此 `.dsh/skills/` 下最终是 **25 个 skill 目录**。这个数字写进目录提案，避免后面数来数去对不上。

---

## 4. 逐个岗位职责与接口

字段口径：**输入校验**＝进场前必须满足（不满足直接退回，R-L1-18）；**完成判据**＝交给下游前必须满足；**失败处理**＝写进 README 的重试与降级策略。

### 文案线

#### 1. `copy-writer` 文案生成
- **输入**：`brief`（思路 / 选题 / 一段话 / 剧情脚本）、平台类型（Q-3 三类之一）、字数区间、`prompt_version`
- **输出**：`draft[]`，**恰好 3 套**，每套含正文 + 侧重点名 + 选择理由
- **输入校验**：brief 非空；平台类型在枚举内；字数区间可解析（如 `300-500`）
- **完成判据**：3 套侧重点互不重复；各套字数在区间内；每套能说出「为什么这样写」
- **失败处理**：模型失败 → `llm-adapter` 降级链重试（最多 3 次）；自检连续 3 次不通过 → 步骤记 `failed`、任务转 `blocked` 并写明原因，由编排者决定重试或转人工（口径以各 skill README 的「失败处理」段为准）
- **不做**：不自动替用户选稿（那是关口①）

#### 2. `storyboard-builder` 分镜拆解
- **输入**：选定文案（`copy`）、`grid = "6x4"`
- **输出**：`shot[]`，**恰好 24 条**，编号 1–24 连续，每条含场景描述 / 视觉风格 / 时长 / 拍摄提示
- **输入校验**：文案已选定（`hitl_events` 有记录）；`grid` 为 `6x4`
- **完成判据**：条数 24；编号连续无重复；24 条风格一致、场景不重复；每条时长合计与目标时长偏差 ≤10%
- **失败处理**：条数不足/超出 → 整批重生成，不允许「补几条」；风格漂移 → 记 warning 并交 `storyboard-validator` 复核

### 视觉线

#### 3. `reference-image-builder` 参考图生成
- **输入**：选定文案 + 分镜风格摘要、平台比例
- **输出**：`reference[]`，1–3 张（默认 1 张）
- **输入校验**：分镜已存在；比例已确认
- **完成判据**：图片可打开、比例正确；风格与文案调性一致（人工确认，关口在流程图上标为「风格确认」）
- **失败处理**：适配器降级链；连续失败退人工出图，不阻断后续

#### 4. `grid-image-builder` 整图生成
- **输入**：24 条分镜 + 参考图 + 比例
- **输出**：`grid_image`，6×4 共 24 格
- **输入校验**：分镜=24 条；参考图已确认
- **完成判据**：整图为 6×4 网格；每格内容能对上对应分镜编号；无空格位
- **失败处理**：整图漏格 → 整张重生成；单格不满意 → 留给下游逐张重生成

#### 5. `image-splitter` 图片切分
- **输入**：6×4 整图、网格参数
- **输出**：`shot_image[]`，24 张，命名 `shot-01.png` … `shot-24.png`
- **输入校验**：整图存在且为 6×4
- **完成判据**：恰好 24 张；命名连续；分辨率一致
- **失败处理**：切分服务不可用 → 按格坐标本地裁切兜底；仍失败 → 转人工裁切并记录

### 视频线

#### 6. `asset-packager` 素材打包
- **输入**：24 张独立图 + 选定文案 + 分镜
- **输出**：工程文件夹（图片 + 文案 + `manifest.json` 素材清单）
- **输入校验**：24 张齐全；文案存在
- **完成判据**：`manifest.json` 每行含分镜编号 → 文件名映射；文件全部存在且非零字节
- **失败处理**：缺文件 → 报出缺哪几张并退回视觉线

#### 7. `image-to-video` 图生视频
- **输入**：工程文件夹、每张时长、转场方式
- **输出**：`draft_video` 视频草稿（未剪辑）
- **输入校验**：`manifest.json` 校验通过；目标时长与平台上限兼容
- **完成判据**：草稿可播放；总时长与设定偏差 ≤5%；镜头顺序 = 分镜顺序
- **失败处理**：适配器降级链（首选服务 → 备选 → 本地 ffmpeg）；记录实际适配器

#### 8. `auto-editor` 自动剪辑
- **输入**：视频草稿、剪辑参数（顺序 / 时长 / 替换 / 字幕开关）
- **输出**：`edit_params` + 预览
- **输入校验**：草稿可读；参数为合法 JSON
- **完成判据**：参数可复现同一版本；预览与实际导出内容一致
- **失败处理**：参数非法 → 报字段级错误（哪一项不合法），不吞错

#### 9. `video-exporter` 成片导出
- **输入**：剪辑参数、成片规格（分辨率 / 码率 / 比例）
- **输出**：`final_video`（mp4）+ 封面帧
- **输入校验**：规格在平台白名单内
- **完成判据**：可播放；分辨率 / 比例正确；时长在平台上限内；封面帧可单独取用
- **失败处理**：渲染失败重试上限 2 次（写进 README），超限通知人工

#### 10. `title-cover-prep` 发布准备
- **输入**：成片、选定文案、平台模板（字数区间 / 标题写法 / 标签数量 / 封面比例）
- **输出**：`publish_package`（标题候选 / 标签 / 封面 / 简介）
- **输入校验**：平台模板存在（Q-18）；成片已导出
- **完成判据**：标题在字数区间内；标签数量符合模板；封面比例正确
- **失败处理**：模板缺失 → 拒绝执行并报「缺平台模板」，不瞎猜

### 分发数据线

#### 11. `browser-publisher` 浏览器填写
- **输入**：`publish_package`、平台登录会话
- **输出**：`pending_publish`（后台已填好，停在发布按钮前）
- **输入校验**：会话有效（过期则暂停并通知）；发布包字段齐全
- **完成判据**：页面各字段已填且与发布包一致；**未点击发布**
- **失败处理**：会话过期 → 暂停等人工；字段校验失败 → 截图留证并报错
- **红线**：任何自动点击发布的路径都必须被 `publish-guard` 拦下（C-01 / C-08）

#### 12. `hotspot-collector` 热点采集
- **输入**：关键词 / 分类、周期或自定义条件、来源白名单
- **输出**：原始热点数据（含关键词 / 时间 / 来源 / 热度）
- **输入校验**：关键词非空；周期可解析
- **完成判据**：每行带采集时间与来源；重复项已去重
- **失败处理**：需登录的来源 → 转人工授权（Q-13），不尝试绕过

#### 13. `table-builder` 汇总成表
- **输入**：原始热点数据
- **输出**：分类汇总表（Markdown / CSV 双格式）
- **完成判据**：按类分组；每行可追溯到原始来源
- **失败处理**：字段缺失 → 该行标记「数据不全」而不是丢弃

#### 14. `feishu-sync` 飞书同步
- **输入**：汇总表、目标文档 ID
- **输出**：飞书文档更新结果
- **输入校验**：应用凭证有效（C-05：密钥只从环境变量读）
- **完成判据**：文档可访问且内容与本地表一致
- **失败处理**：API 失败 → 导出本地文件兜底 + 告知人工（Q-5）

#### 15. `metrics-collector` 指标采集
- **输入**：已发布内容清单、统计周期
- **输出**：`metric[]`，三项指标 + 采集时间 + 周期
- **完成判据**：三项齐全（播放量 / 互动量=赞藏评合计 / 涨粉数）；带采集时间戳
- **失败处理**：某项取不到 → 记 `null` 并在报告里显式标注「未取到」，不用 0 冒充

#### 16. `review-reporter` 复盘报告
- **输入**：本期指标 + 历史指标 + 内容特征（类型 / 标题写法 / 发布时间）
- **输出**：复盘报告（结论 + 可执行优化建议 + 下一轮提示词修改点）
- **完成判据**：结论有数据支撑；建议可执行（能落到某个 skill 的输入上）；修改点写成新 `prompt_version`
- **失败处理**：样本量不足 → 明确写「样本不足，仅供参考」，不给确定性结论

### 基础设施（跨线共用）

#### 17. `llm-adapter` 模型适配
- **职责**：统一文本 / 图像生成调用；业务 skill 不出现具体服务名（R-L2-14）
- **接口**：`generate_text(prompt, **opts) -> str`、`generate_images(prompt, count, size) -> [artifact]`、`image_to_video(images, audio) -> artifact`
- **必须声明**：能力范围 / 是否需密钥 / 是否计费 / 失败特征 / 降级顺序（R-L2-16）
- **红线**：默认只走免费额度；可能计费的调用先经批准并设上限（C-09）

#### 18. `prompt-registry` 提示词注册
- **职责**：提示词入仓为文件（不写死在代码里），按 `prompt_version` 取用
- **输出**：`prompt_version` 字符串，随产物一起入库（R-7-03）

### 支撑件（7 个目录）

| skill_id | 职责 | 关键约束 |
| -------- | ---- | -------- |
| `artifact-recorder` | 写产物表 / 步骤流水表 / 操作留痕 | 每条含 `task_id`、`skill_id`、`model_version`、`prompt_version`、实际适配器（✅ 步骤 4 已落地） |
| `hitl-gate` | 统一实现三类关口（五个关口点） | 关口枚举 `gate1_select_copy` / `gate_visual_style` / `gate_visual_fix` / `gate2_edit_video` / `gate3_publish_auth`；一律写 `hitl_events`（✅ 步骤 4 已落地，步骤 5 扩到五个） |
| `storyboard-validator` | 校验 24 条 + 编号连续 | 只读校验，不改内容；失败必须退回（✅ 步骤 4 已落地） |
| `image-consistency-checker` | 校验 24 张 + 编号连续 + 分辨率一致 | 只出结论、不改产物、不把任务置 blocked（✅ 步骤 5 已落地） |
| 视频线本地能力 | `video.ffmpeg` 适配器 + `_shared/video.py` | 本地免费兜底：按镜序与逐镜时长合成成片、抽封面帧（✅ 步骤 6 已落地；Remotion 未接时自动降级到它） |
| `publish-guard` | 拦自动发布 | 任何发布相关写操作前必过；命中即阻断并记事件 |
| `task-decomposer` | topic → task 派单 | 编排者专属；一次派单必须能算清「派给谁、要什么、什么算完成」 |
| `summary-writer` | 四线结果汇总回报 | 只汇总，不改写下游结论 |

---

## 5. 一次执行的统一流程（每个 skill 都照这个跑）

```
① 取任务（编排者派单，带 task_id 与输入引用）
② 输入校验（本 README 的「输入校验」段）——不通过 → 退回，附缺什么
③ 执行（只走 llm-adapter 等统一接口，不直接连外部服务）
④ 自检（本 README 的「完成判据」段）——不通过 → 本 skill 内重试或整体重来
⑤ 登记产物（artifact-recorder：产物表 + 步骤流水 + 版本字段 + 实际适配器）
⑥ 交回编排者（由编排者决定下一步派给谁；skill 之间不互相调用 —— 需要复用的逻辑一律下沉到 `.dsh/skills/_shared/`，见决策 D-10）
```

人工关口（`hitl-gate`）在同一条流水里表现为「暂停 → 等人在页面上操作 → 写事件 → 继续」，
暂停期间任务状态为 `waiting_human`，页面上显示当前处理人与待办（R-8-03）。

---

## 6. 与流程图的对应关系

| 流程图 | 覆盖岗位 |
| ------ | -------- |
| `.archify/FLOW-COPY-20261012/copy-line.html` | `copy-writer`、`storyboard-builder`、`hitl-gate`(关口①)、`llm-adapter`、`prompt-registry`、`artifact-recorder` |
| `.archify/FLOW-VISUAL-20261012/visual-line.html` | `reference-image-builder`、`grid-image-builder`、`image-splitter`、`llm-adapter`、`image-consistency-checker`、`artifact-recorder` |
| `.archify/FLOW-VIDEO-20261012/video-line.html` | `asset-packager`、`image-to-video`、`auto-editor`、`video-exporter`、`title-cover-prep`、`hitl-gate`(关口②) |
| `.archify/FLOW-PUBLISH-20261012/publish-line.html` | `browser-publisher`、`publish-guard`、`hotspot-collector`、`table-builder`、`feishu-sync`、`metrics-collector`、`review-reporter`、`hitl-gate`(关口③) |
| `.archify/FLOW-OVERALL-20261012/overall-operations.html` | 四条线 + 编排者 + 适配器层 + 本地留痕的总览 |

---

## 7. 首版范围与推迟项

**首版必做（18 岗位 + 7 支撑件，全部单链路最小实现）**
- 每条线只打通「一条主链路」，不做并行多方案；
- 每处校验只做「条数 / 编号 / 分辨率 / 必填字段」四类硬校验；
- 每个适配器只接 1 个首选服务 + 1 个兜底，不做全量接入。

**显式推迟（写进 README 的「不在本版范围」段，避免误解为漏做）**
- 多平台同时发布、批量养号类能力；
- 多模型投票 / 自动择优；
- 视频模板库、字幕样式库、BGM 自动匹配；
- 热点来源的付费接口与需登录平台的全自动采集；
- 数据看板的高级图表与自定义维度分析。

---

## 8. 变更记录

| 日期 | 变更 | 来源 |
| ---- | ---- | ---- |
| 2026-10-12 | 首版：18 岗位 + 7 支撑件，命名规则、接口字段、统一执行流程、与图对应关系 | N004 |
