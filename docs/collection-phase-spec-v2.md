# UX 竞品洞察工具
## 素材搜集阶段完整方案 v2

> **融合说明**：v2 保留了 collection-phase-spec（我的方案）的场景网格 + 映射卡 + 格子状态机骨架，移植了 v1 的产品实体归一化、领域词表、多轮搜索策略、主张分层、AI 重建机制、完整 adapter 列表和持续更新机制。
>
> **核心取舍**：场景网格是第一公民（产品向坐标看齐），v1 的"产品来源地图"降级为去重索引；v1 的"全局五轮搜索"改为格子内微阶段；v1 的主观主张分流到 L3 Insight 而非 L1 Observation；AI 重建标记为 inferred、权重为 0、不影响饱和判定。

---

## 0. 核心原则

### 0.1 基础假设

首版产品只依赖公开网络和公开可访问材料，不将以下条件作为产品成立的前提：

- 用户拥有竞品真实账号
- 竞品提供试用或演示沙盒
- 厂商愿意合作并开放资料
- 用户愿意主动贡献登录后页面

试用账号、用户贡献和厂商合作只能作为未来增强资料深度的渠道（Tier B），不能成为基础搜集能力的依赖。

### 0.2 阶段边界

从用户输入产品品类/名称/任务开始，到输出一份可供后续 UX 分析使用的 `Evidence Pack` 结束。

**负责**：发现候选产品、建立来源索引、多轮多渠道搜索、证据化与分层标注、覆盖缺口驱动补搜、AI 重建辅助理解、输出覆盖报告。

**不负责**：最终判断谁的设计最好、直接形成我司设计方案、将 AI 推测当成竞品事实、将营销宣传当成真实产品体验。

### 0.3 对"搜全、搜准"的定义

- **全 = 对场景网格的覆盖率，且空洞显式可见**。采集前先把场景网格全部枚举成格子，"空"就从"没人知道该有"变成地图上一块显式空白。
- **准 = 可溯源、带版本与时间戳，区分 observed / claimed / inferred**。每条证据都能回答"谁在什么版本、什么时间、通过什么渠道看到的"。

采不到就诚实标空，永远优于伪造覆盖。

---

## 1. 阶段输入与输出

### 1.1 支持的输入方式

1. **输入产品品类**：如"AI 合同审查""企业预算与预测工具"
2. **输入已知产品**：如"Anaplan"，系统扩展同类产品和任务标杆
3. **输入具体任务**：如"复杂模型配置""财务审批流程"

可选补充：目标用户角色、重点业务任务、平台/终端、地区和语言、资料时间范围、已知竞品、希望支持的设计决策。

### 1.2 最终输出：Evidence Pack

1. 候选竞品与标杆产品池（含跨行业标杆，归一化实体）
2. 每个产品的产品身份、模块、旧名称和关联关系
3. 来源索引（SourceRegistry）
4. 页面截图、视频关键帧、PDF 页面、交互 demo 截图
5. 每份证据的来源、版本、时间、evidence_type
6. 场景网格覆盖矩阵（含三种"空"语义）
7. 重复、冲突、过期和待验证资料
8. 必要时的 AI 重建低保真页面（明显标注）
9. 搜索覆盖报告（范围、停止原因、未覆盖项）

---

## 2. 端到端流程

```
M0 产品实体注册
  → 理解输入 → 领域词表 → 候选产品发现 → 实体归一化
M1 场景网格初始化
  → JTBD × 旅程阶段 × 页面/状态 网格 → 映射卡
M3 采集引擎（格子驱动，多轮采集）
  → 格子进队列 → 查询扩展（词表驱动）→ adapter fan-out
  → AI 相关性打分 → 去重排序 → shortlist
M4 素材确认与标注
  → 人工 accept → Observation（中性）→ Claim 分层
M5 覆盖看板
  → 覆盖矩阵 → 缺口驱动补搜 → 搜索报告
AI 重建（按需，仅在有文档无页面时触发）
持续更新（FRESHNESS_DECAY 后子流程）
```

---

## 3. M0 · 产品实体注册

**目的**：在采集开始前建立统一产品实体，解决 B 端产品频繁改名、收购、模块拆分导致的重复和漏收问题。M1 场景网格的竞品轴引用 M0 的稳定 ID。

### 3.1 候选产品发现

来源：行业目录（G2/Capterra）、分析报告、会议奖项参展商、产品对比文章、收购融资新闻、应用市场集成列表、已有团队知识库。

候选分组：直接竞品 / 间接竞品 / 跨行业任务标杆 / 待核验候选 / 已排除产品（保留排除原因）。

### 3.2 产品实体归一化

```
CompetitorEntity {
  competitor_id         // 稳定主键（只增不改）
  canonical_name        // 当前主名称
  aliases[]             // 旧名称、缩写、地区名称
  parent_company
  products[]            // 子产品/模块列表
  official_domain
  help_center_domain
  video_channels[]      // YouTube 频道等
  app_store_pages[]
  acquired_from         // 收购前名称（若有）
  valid_from / valid_to // 名称有效时间范围
}
```

归一化解决：同产品因不同名称被重复收录、只搜新名称漏掉旧资料、产品名与公司名不一致、功能隐藏在子产品中。

### 3.3 领域词表（DomainLexicon）

两级维护，直接作为 M3 查询扩展的输入：

| 级别 | 维护者 | 内容 |
|---|---|---|
| 品类级（Category Vocab） | Research Lead | 通用任务词、角色词、行业术语、页面状态标准词 |
| 项目级（Project Vocab） | 本项目负责人 | 特定产品旧名称、客户自定义术语、本次新发现同义词 |

词表字段：`term / type(task/role/ui_state/product_alias) / language / valid_for_competitors[] / source`

---

## 4. M1 · 场景网格管理（L2）

**目的**：定义可比较的场景坐标系。产品向坐标看齐，绝不反过来——否则 N 张网格、零可比性。

### 4.1 三轴坐标系

```
场景格子 = JTBD（用户任务）× 旅程阶段 × 关键页面/状态
```

**JTBD 轴**：8–15 个顶层用户任务，用意图语言写（"为新成员分配访问权限"，不是"权限管理"）。慢变量，改动需 steward 或 2 人复核。

**旅程阶段轴**：通用骨架（首次配置 / 日常使用 / 异常处理 / 规模化管理），按品类改写。慢变量。

**页面/状态轴**：只枚举"有意义的 UX 时刻"（承重格），不做笛卡尔积。快变量，可轻量 ADD。

### 4.2 粒度规则

拆成两格须三条同时成立：用户目标/情绪不同 + 失败面不同 + 设计对策不同。最硬判据：**拆格前先写出对标评分问题；若新旧格共用同一问题，不拆**。

视觉/布局变体、纯取值变化、交互子态一律合并。

### 4.3 格子 ID 与版本

ID 只增不改、永不复用。变更走封闭词表：ADD / SPLIT / MERGE / DEPRECATE / REDEFINE，每次进版本 vN + changelog。

JTBD 轴和旅程阶段轴变更高门槛（steward 或 2 人复核），页面/状态轴 ADD 轻量审批。

### 4.4 跨行业标杆的纳入时机

JTBD 轴播种时预留"跨行业候选"标记，等本品类 v1 冻结后专门一轮 ADD 批量引入。期间用未映射收件箱承接跨行业信号。

### 核心数据对象

```json
GridCell {
  cell_id,               // 永久唯一，只增不改
  jtbd,                  // 意图语言
  journey_stage,         // 枚举
  page_state,            // 具体 UX 时刻
  value_score,           // 0-1，采集优先级权重
  version,
  status                 // ACTIVE / DEPRECATED
}
```

---

## 5. M2 · 映射卡（L2）

**目的**：每个格子的意图定义，是唯一跨层契约——L2 用它对齐，L1 用它打分和裁决。缺映射卡的格子不进采集队列。

### 5.1 三要素

- **意图定义**（1 行）：用户在这个格子里试图完成什么
- **纳入/排除标准**：哪些截图算命中、哪些不算（文字 + 示例）
- **锚点截图**：1 张参照产品代表截图，是 AI 打分和人工裁决的视觉参照

### 5.2 SPLIT 时的继承

坐标 SPLIT 时，子格各自继承父格映射卡并修改。Asset 不动（屏级锚定），按新映射卡把旧格 Observation 重新裁决进子格；旧格衍生的 Claim 标 stale 并重算，不静默平移。

```json
MappingCard {
  cell_id,
  intent_definition,
  inclusion_criteria,
  exclusion_criteria,
  anchor_screenshot,    // asset_id
  version,
  created_by,
  reviewed_by
}
```

---

## 6. M3 · 采集引擎（L1）

**目的**：对着格子自动采集、AI 过滤，产出候选素材 shortlist。AI 管过滤，人管入库裁决。

### 6.1 格子状态机

```
UNPROBED → QUEUED → PROBING → SHORTLIST_READY
                ↑               ↓（人工裁决后）
            QUEUED ← STALE    PARTIAL / SATURATED / REJECTED_EMPTY
                               RECONSTRUCTED（仅在有文档、无截图时）
                ↑（FRESHNESS_DECAY 把 SATURATED 打回）
```

**入队触发**（任一即入队）：
- `NEW_CELL`（格子新建）
- `COVERAGE_GAP`（战略格长期 PARTIAL）
- `FRESHNESS_DECAY`（核心功能 30d / 权限法务类 90d / 稳定功能 120d）
- `UPSTREAM_INVALIDATION`（changelog watcher 检测版本更新）
- `MANUAL_PIN`（人工强制优先）
- `CONTRADICTION`（多份素材相互矛盾）

**出队优先级（可配置权重）**：
```
0.30·战略权重 + 0.25·缺口比 + 0.20·鲜度衰减 + 0.10·可采性
− 0.10·近期探测惩罚 − 0.05·预期成本
```

### 6.2 Probe Cycle（一轮采集，四个微阶段）

v1 的"五轮搜索"被重构为每格内部的微阶段（sub-phases），而非全局串行。格子状态字段增加 `current_sub_phase`：

| 微阶段 | 对应 v1 搜索轮次 | 触发条件 |
|---|---|---|
| DISCOVER_SOURCES | 第一、二轮 | 格子首次启动 |
| DEEP_COLLECT | 第三轮（按任务深搜） | DISCOVER_SOURCES 完成 |
| STATE_SWEEP | 第四轮（按页面状态补搜） | PARTIAL 格子持续探测 |
| VERIFY_FRESHNESS | 第五轮（版本验证） | FRESHNESS_DECAY 触发 |

**一次 probe cycle 的具体步骤**：
1. **查询扩展**（全自动）：格子坐标 + 领域词表（品类级+项目级）→ 多语义查询包（同义词/意图词/竞品命名差异/版本词/来源定向词）
2. **Adapter 并行 fan-out**（全自动，单源熔断）
3. **AI 相关性打分**（全自动）：对照映射卡意图定义+锚点截图，按 rubric 打 0–1 分，< 0.55 直接丢
4. **去重+排序**（全自动）：感知哈希折叠复用图为 canonical，按版本新鲜度排序
5. **输出 top-8 shortlist** 推送 M4

**饱和判定（四条 AND，外置配置）**：
- 独立来源数 ≥ target（Tier A:3 / Tier B-only:2 / Tier C:永不饱和）
- 有素材在鲜度窗内
- 连续 2 轮 net_new = 0
- coverage_confidence ≥ 0.75
- claimed 和 ai_reconstructed 不计入独立来源数

### 6.3 八个 Adapter

| Adapter | Tier | 定位机制 | 产出 | 合规处置 |
|---|---|---|---|---|
| **帮助文档/知识库** | A | `site:help.*` → sitemap → 页内锚点切分 | 目标区域截图+HTML快照 | `third_party_official`；对外缩略+署名+深链 |
| **交互式 demo**（Navattic/Storylane/Arcade） | A | iframe 域名/脚本签名 → 驱动 player 逐步截图 | 有序 step 截图（共享 demo_session_id）+tooltip 文案 | `embedded_third_party`；只存缩略+player链接；标 `capture_context=guided_demo` |
| **官方视频** | A | 字幕时间轴→章节→VLM 认屏 | 关键帧（timestamp+transcript 摘要） | `copyrighted_marketing`；不存整片；缩略帧+深链 |
| **PDF 与文档** | A | 站内搜索+filetype:pdf → 全文解析 | 页级文本+页面图片+表格+流程图 | `third_party_official`；图片继承文档来源与页码 |
| **更新日志/Changelog** | A | 官方域名 changelog 页面 | 功能变化+版本+涉及模块 | `third_party_official`；自动触发 VERIFY_FRESHNESS |
| **单张图片** | A | 图片搜索+竞品名+任务词 | OCR文案+页面结构描述+来源 | 来源不完整时必须标`completeness: PARTIAL` |
| **文章与评测** | A/C | 第三方博客/测评 | 产品事实候选+作者观点+截图 | 标注`author_type: INDEPENDENT/SPONSORED`；观点不能升级为事实 |
| **试用号实时截图** | **B** | 人工注册（凭证入 vault）+自动导航脚本 | 真实当前 UI 截图（product_version 精确） | `self_captured_under_tos`；PII 遮罩；最高价值证据 |

**来源索引表（SourceRegistry）**：降级自 v1 的"产品来源地图"，作为去重工具。结构：`{source_url → {competitor_id, discovered_at, supporting_cells[]}}`。probe cycle 采集前查此表避免重复抓取，不驱动采集流程。

### 6.4 Asset 数据对象

```json
Asset {
  asset_id,              // 不可变
  cell_id,
  competitor_id,         // 引用 CompetitorEntity
  source_url,
  captured_at,
  product_version,
  rights_status,         // self_captured_under_tos / third_party_official /
                         // embedded_third_party / copyrighted_marketing / unknown
  media_disposition,     // original / thumbnail_only / link_only
  evidence_type,         // observed / claimed / inferred / ai_reconstructed
  capture_context,       // guided_demo / live_trial / doc_illustration / marketing
  native_step,           // 产品原生流程步骤名（保留上下文，对齐用 journey_stage）
  native_step_index,
  mapped_journey_stage,  // 映射到的标准旅程阶段
  completeness,          // FULL_PAGE / PARTIAL_EXCERPT / INFERRED_FROM_DOC / AI_RECONSTRUCTED
  checksum,
  supersedes,            // 旧版本 asset_id（版本链）
  ai_score,
  is_superseded          // 旧版本标记，保留可回溯
}
```

**存储合规规则（采集前置守卫，确定性映射）**：

| rights_status | media_disposition | 备注 |
|---|---|---|
| self_captured_under_tos | original（已遮罩） | 内部全量，对外需二次法务确认 |
| third_party_official | 内部 original / 对外 thumbnail_only | 缩略+署名+深链 |
| embedded_third_party | thumbnail_only | step 缩略+player 链接 |
| copyrighted_marketing | link_only+低分缩略帧 | 缩略帧短存供打分，用完回收 |
| unknown | link_only + rights_review=needs_human | 阻断展示 |

---

## 7. M4 · 素材确认与标注（L1）

**目的**：人工硬闸门 + 中性事实标注 + Claim 分层。没有人工 accept，任何素材不得进证据库。

### 7.1 Shortlist 审核界面

- 按格子分组展示 top-8 候选，左侧映射卡（意图定义+锚点截图）始终可见
- 每条候选显示：截图预览、来源 URL、采集时间、版本、AI 打分理由、evidence_type 标记
- 操作只有三个：Accept / Reject / Flag（送人工复议）
- **人不搜索、不翻原始结果**，只在 AI 给的 8 条上判断
- claimed 和 ai_reconstructed 素材视觉降级（灰底+"声称"/"重建"角标），Accept 时系统警告并强制确认
- 采纳率实时显示，低于 40% 触发"查询质量警告"

### 7.2 Observation（中性标注）

Accept 后强制填写（或 AI 预填草稿，人工校验）。只记事实，不含判断。

**合法字段**：`surface_confirmed / ui_elements_present / labels_verbatim（逐字不译）/ control_states / role_options_shown / sequence_context / capture_context / native_step / mapped_journey_stage`

**禁止字段**：任何评价性词语（"直观""复杂""优秀"）。编辑器对判断词做软校验拦截。

### 7.3 Claim 分层（新增，在 Observation 之上）

v1 的五类主张按中性/主观分流：

| Claim 类型 | 归属层 | 说明 |
|---|---|---|
| `OBSERVED_FACT` | L1 Observation 附属 | 界面/行为的直接描述，中性 |
| `SOURCE_STATEMENT` | L1 Observation 附属 | 来源文档原话引用，中性 |
| `ANALYTICAL_INTERP` | L3 Insight | 研究者对现象的解释，主观 |
| `RESEARCH_HYPOTHESIS` | L3 Insight | 尚待验证的推断，主观 |
| `DESIGN_RECOMMENDATION` | L3 Insight | 指向设计建议，主观 |

**引用链**：`Asset → Observation（中性）→ Claim(L1 类型) → Insight（L3，跨格综合）`

```json
Observation {
  observation_id,
  asset_id,              // 回指原始素材（不可变引用）
  cell_id,
  competitor_id,
  surface_confirmed,
  ui_elements_present,   // 数组
  labels_verbatim,       // 逐字文案，不诠释
  control_states,
  role_options_shown,
  sequence_context,
  capture_context,
  native_step,
  mapped_journey_stage,
  accepted_by,
  accepted_at,
  claims[]               // 附属 OBSERVED_FACT / SOURCE_STATEMENT
}
```

---

## 8. M5 · 覆盖看板与搜索报告

**目的**：让完整度可测、空洞自己现形。不是统计报表，是驱动采集行为的操作界面。

### 8.1 覆盖矩阵

行 = 场景格子，列 = 竞品。每格颜色区分**三种"空"语义**（必须一眼分清）：

| 状态 | 着色 | 含义 |
|---|---|---|
| SATURATED | 绿 | 已充分（≥3 独立 observed 来源 + 版本新鲜） |
| PARTIAL | 黄 | 薄弱（1-2 来源 / 单一来源 / 仅 claimed） |
| **覆盖空洞**（矩阵留洞） | 灰白 | 该品类无产品做到 → **特性，保留，是网格价值** |
| **REJECTED_EMPTY** | 红斜线 | 找过采不到 → 采集极限，停止浪费探测预算 |
| **未映射屏**（收件箱） | 橙感叹号 | 产品有、网格无 → **债务，必须清** |
| RECONSTRUCTED | 橙边框 | AI 重建，有文档无截图 |
| 墙后不可得 | 灰条纹 | Tier C，只能 claimed |

格子悬停：独立来源数 / 最新采集时间 / evidence_type 构成 / probe_cycles 数。

### 8.2 搜索覆盖报告（从 v1 §15 移植）

每轮搜集完成后生成：

- **搜索范围**：用户输入、领域词表、产品类型、时间/地区/语言、已检查来源组、搜索轮次和停止原因
- **产品覆盖**：候选总数、已确认、待核验、已排除（含排除原因）、直接/间接/跨行业分布
- **证据覆盖**：各产品页面/视频/PDF/文字证据数量、核心任务覆盖率、真实 observed 占比、仅营销/文字的产品
- **未覆盖项**：未找到页面的产品和任务、只有文档无视觉证据的流程、来源冲突的事实、无法确认的版本

### 8.3 操作入口

- 手动触发某格重新采集（MANUAL_PIN）
- 标记某格"不采集"（战略优先级低 / 永久墙后），进 REJECTED_EMPTY
- 未映射收件箱：批量裁决"ADD 新格 / SPLIT 现有格 / out-of-scope 忽略"
- 缺口驱动补搜：系统根据 PARTIAL 格子生成具体查询，明确是"补齐权限编辑页的 B 产品证据"而非"继续搜一些资料"

---

## 9. AI 重建机制

**触发条件**：格子状态 WALLED 且存在相关文档 Asset（有文字描述但无截图/录屏）。

**可生成内容**：用户旅程、业务流程图、页面信息架构、字段和操作清单、灰度低保真线框、待验证问题清单。

**展示分层（三类内容绝不混合）**：
- `Observed`：真实页面、录屏、视频帧
- `Reconstructed`：基于文档事实生成的低保真页面（明显橙色边框 + "AI 重建，非竞品原始界面"水印）
- `Proposed`：后续分析阶段为内部产品生成的设计方案

**重建规则**：
- 低保真或蓝图视觉，避免伪装成真实截图
- 每个关键区块关联原始文档段落
- 明确区分文档事实和 AI 推测
- **不计入真实页面覆盖率，不计入饱和判定**（ai_reconstructed 权重为 0）
- 保留生成时间、来源文档和假设版本

```json
AIReconstruction {
  reconstruction_id,
  cell_id,
  source_assets[],         // 生成依据的文档 Asset 列表
  fidelity_level,          // LOW / MEDIUM（不允许 HIGH）
  generated_at,
  model_version,
  human_review_status,     // PENDING / REVIEWED / REJECTED
  confirmed_facts[],       // 文档明确描述的字段/步骤/规则
  ai_inferences[],         // AI 推测的布局/控件/信息组织
  unverified_items[]       // 文档未明确的反馈/异常/交互细节
}
```

**降级路径**：后续找到真实截图，格子从 RECONSTRUCTED 回到 QUEUED 重新采集，AI 重建存档保留。

---

## 10. 持续更新

FRESHNESS_DECAY 触发后的子流程（嵌入现有状态机，不是平行机制）：

```
FRESHNESS_DECAY 触发
  → 格子进入 CHECKING 状态
  → 重新抓取来源 → 生成新 Asset
  → diff(新 Asset, 最近旧 Asset)
      ├─ 无变化 → 更新 freshness_timestamp，回到 SATURATED
      ├─ 小幅变化 → 标记 VERSION_DELTA，附旧/新对比
      └─ 重大变化 → 标记 VARIANT，旧证据存档，新证据重走 Claim 评估
  → 若 Claim 依赖的 Observation 来源 Asset 已更新
      → 该 Claim 状态改为 NEEDS_REVIEW
      → L3 Insight 若引用该 Claim，同步标记
```

**原则**：旧 Asset 不删除，只存档（`is_superseded: true`）。格子"当前证据"始终指向最新 Asset，历史可溯。

---

## 11. 核心数据对象汇总

```
CompetitorEntity        // M0：产品实体（含别名、旧名称、域名树）
DomainLexicon          // M0：领域词表（品类级+项目级）
GridCell               // M1：场景格子（JTBD × 阶段 × 状态）
MappingCard            // M2：格子的意图定义+锚点截图
SourceRegistry         // M3：来源去重索引表（source_url → supporting_cells）
Asset                  // M3：不可变原始素材（带版本链）
Observation            // M4：中性标注（禁止判断词）
Claim                  // M4：主张分层（中性类型附在 Observation，主观类型在 L3）
AIReconstruction       // M9：AI 重建产物（独立对象，不参与饱和判定）
SearchReport           // M5：搜索覆盖报告
RefreshEvent           // M10：更新事件
```

---

## 12. Web 端功能页面

| 页面 | 对应模块 | 功能要点 |
|---|---|---|
| **产品实体注册页** | M0 | 候选产品列表、实体归一化、别名/旧名称编辑、接受/排除/合并 |
| **场景网格初始化页** | M1 | JTBD+阶段+状态轴定义、格子 ADD/SPLIT、版本 changelog、未映射收件箱 |
| **映射卡编辑页** | M2 | 意图定义表单、纳入排除标准、锚点截图上传、inter-rater 抽查 |
| **采集监控页** | M3 | 队列状态、probe cycle 进度、adapter 状态、来源索引查看 |
| **素材审核页** | M4 | Shortlist 审核（accept/reject/flag）、Observation 标注表单、Claim 分类 |
| **覆盖矩阵页** | M5 | 格子×竞品矩阵（三种空着色）、悬停详情、下钻到 Asset/Observation |
| **搜索报告页** | M5 | 范围/产品覆盖/证据覆盖/未覆盖项、导出 Evidence Pack |
| **异步任务中心** | 跨模块基础设施 | 任务队列（queued/running/review_required/failed/completed），阶段性结果查看 |
| **AI 重建审核页** | M9 | 重建产物展示（橙色边框）、文档依据关联、approve/reject |

---

## 13. MVP 范围与验收

### 13.1 MVP 聚焦

**品类**：法律科技（合同管理）或财务规划（预算/预测），Web 端产品优先，最近一年资料优先。

**功能包含**：
- M0：产品实体归一化、领域词表（品类级+项目级）
- M1：场景网格（1 个品类、1 个 JTBD、5-10 个格子）、映射卡
- M2：映射卡（含锚点截图、inter-rater 轻量检查）
- M3：采集队列（状态机+入队触发）、**帮助文档+交互式 demo 两个 adapter**、AI 打分、去重
- M4：Shortlist 审核界面、Observation 标注（判断词软拦截）、Claim 分层（L1 类型）
- M5：覆盖矩阵（三种空着色）、搜索报告
- M9：可选的 AI 重建（1-2 个墙后格子试验）
- 异步任务中心（基础版）

**暂缓 Phase 2**：
- 完整 8 个 adapter（PDF、更新日志、试用号等留 Phase 2）
- SPLIT/MERGE/DEPRECATE 完整变更流程
- Changelog watcher（UPSTREAM_INVALIDATION 触发）
- 未映射收件箱完整治理工作流
- 持续更新完整子流程

### 13.2 验收标准

- [ ] 1 个品类网格 v1 冻结（含已知空洞标注）
- [ ] 每格有映射卡，3 个战略格已做 inter-rater 抽查
- [ ] 帮助文档+交互式 demo 两个 adapter 各跑通至少 3 个格子
- [ ] Observation 中性标注合格率（判断词零出现）
- [ ] 覆盖矩阵三种空语义可一眼区分
- [ ] 战略格 SATURATED，其余 PARTIAL 即可放行 L3
- [ ] AI 重建产物明显标注、不计入覆盖率

---

## 14. 时间估算（3 人团队）

基于我的方案"3 人 12-14 周"，移植 v1 模块后调整：

| 新增/扩展项 | 工作量增量 | 说明 |
|---|---|---|
| M0 产品实体归一化 | +2 周 | CompetitorEntity 完整层级、别名/旧名称维护、归一化逻辑 |
| 领域词表（品类级+项目级） | +1 周 | 词表 CRUD、两级维护、与查询扩展集成 |
| Claim 分层 | +1.5 周 | Observation 之上加 Claim 表、五类主张分流、L1/L3 分工 |
| AI 重建机制 | +2 周 | AIReconstruction 对象、低保真渲染、文档依据关联、降级路径 |
| Adapter 扩充（PDF/图片/文章/Changelog） | +1.5 周 | 四个新 adapter（试用号留 Phase 2） |
| 持续更新子流程 | +1 周 | CHECKING 状态、diff 逻辑、Claim 传播 |
| Web 页面扩充 | +1.5 周 | 产品实体注册页、AI 重建审核页 |

**v2 总工时**：12-14 周（原估算）+ 10.5 周（新增）= **22-24 周**

**3 人并行后**：约 **16-18 周**（4-4.5 个月）

**关键路径**：M0 产品实体归一化 → M1 网格初始化 → M3 采集引擎（adapter 并行开发）→ M4 审核+标注 → M5 看板。AI 重建可与 M4 并行。

### 14.1 最快验证切片（4-6 周，2 人）

砍到极简：
- 1 个品类、1 个 JTBD、5 个格子
- 手工建 1 个 CompetitorEntity（简化归一化流程）
- 帮助文档 adapter 只做 1 个竞品
- AI 打分用 Claude Vision API 简单 rubric，不做精细调优
- M4 只要 accept/reject，Observation 纯手填，不做 Claim 分层
- M5 静态覆盖矩阵，不做交互
- 跳过 AI 重建

验证核心价值假设："证据锚定的中性标注 → 覆盖矩阵暴露空洞"。

---

## 15. 关键风险

1. **产品实体归一化的持续维护成本**（v1 移植带来）：B 端产品收购频繁，CompetitorEntity 表会不断膨胀。缓解：只归一化重点产品，长尾产品简化处理。

2. **交互式 demo adapter 脆弱性**（我的方案已有风险）：Navattic/Storylane 平台可能改 DOM 或加反爬。缓解：先手动捕获，等帮助文档跑通后再自动化。

3. **AI 重建误导用户**（v1 移植带来）：低保真页面若视觉不够明显，用户可能误当真实截图。缓解：强制橙色边框+水印+不计入覆盖率+单独视图区隔。

4. **Claim 分层增加学习成本**（v1 移植带来）：Observation → Claim → Insight 三层，用户可能困惑"该在哪层记录什么"。缓解：编辑器嵌入字段级提示、提供标注模板。

5. **未映射收件箱债务累积**（场景网格机制固有）：产品不断出新 UI，网格跟不上演进。缓解：设 SLA（未映射屏 > N 天自动提醒品类 owner）、定期批量裁决。

---

## 16. v1 对照表

| v1 章节 | v2 对应位置 | 处理方式 | 说明 |
|---|---|---|---|
| §0 核心原则 | §0 | 融合 | 保留 v1 基础假设+我的"全且准"重定义 |
| §1 输入输出 | §1 | 完整移植 | v1 的 Evidence Pack 结构保留 |
| §2 端到端流程 | §2 | 重构 | 改为 M0-M5 五模块流程 |
| §3 理解输入 | §3 M0（新增） | 移植+扩展 | v1 的领域词表移到 M0，作为 M3 输入 |
| §4 候选产品发现 | §3.1 M0 | 完整移植 | v1 候选分组保留 |
| §5 产品身份归一化 | §3.2 M0（新增） | 完整移植 | CompetitorEntity 完整层级，我的方案核心扩展 |
| §6 产品来源地图 | §6.3 SourceRegistry | 降级 | 改为去重索引表，不驱动采集 |
| §7 多轮搜索策略 | §6.2 Probe Cycle 微阶段 | 重构 | 全局五轮 → 格子内四微阶段 |
| §8 素材证据化 | §6.3 Adapter 表 | 完整移植+扩展 | v1 的 PDF/图片/文章/Changelog 全部加入 |
| §9 证据分类与可信度 | §6.4 Asset、§7.3 Claim | 融合 | v1 的来源等级 A/B/C/D/E 映射到 Tier A/B/C + evidence_type |
| §10 主张级核验 | §7.3 Claim 分层 | 重构 | 五类主张分流：中性入 L1 Observation 附属，主观入 L3 Insight |
| §11 去重聚类版本 | §6.2 step 4 | 完整移植 | 感知哈希+版本链（supersedes）保留 |
| §12 覆盖矩阵 | §8.1 M5 | 融合 | v1 七维矩阵压缩为场景格子×竞品，状态机编码质量 |
| §13 AI 重建机制 | §9（新增独立章节） | 完整移植+约束 | 加强"不计入饱和"约束、独立对象、降级路径 |
| §14 搜索停止条件 | §8.1 饱和判定 | 融合 | v1 软停止条件 → 格子 SATURATED 硬判据 |
| §15 搜索覆盖报告 | §8.2 M5 | 完整移植 | v1 报告结构保留 |
| §16 Web 端功能页面 | §12 | 对应整合 | v1 七页面映射到 M0-M5+异步任务中心 |
| §17 核心数据对象 | §11 | 融合 | v1 对象保留（ProductEntity/DomainLexicon/SourceProfile/ReconstructionArtifact），我的方案对象保留（GridCell/MappingCard/Asset/Observation） |
| §18 持续更新 | §10（新增独立章节） | 完整移植 | 嵌入 FRESHNESS_DECAY 子流程 |
| §19-23 MVP/指标/风险 | §13-15 | 融合 | MVP 扩展包含 v1 模块、风险增加 v1 移植项 |

**未移植项（判断为冗余或与核心机制冲突）**：
- v1 §6 完整"产品来源地图"驱动逻辑（与格子状态机冲突，降级为索引）
- v1 覆盖矩阵的"产品流程步骤"维度（与跨产品对齐冲突，保留为 Observation 元数据）
- v1 的全局五轮串行搜索（与独立 probe cycle 冲突，改为格子内微阶段）

---

**v2 文档结束。完整方案已写入 `/Users/xzb/Claude/Projects/HW-LRS/collection-phase-spec-v2.md`。**
