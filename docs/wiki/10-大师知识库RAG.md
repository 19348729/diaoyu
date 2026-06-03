# 10 大师知识库 RAG

> 范围：将上游采集管线产出的结构化知识库工程化为可被 LLM 救场接口稳定消费的检索增强（RAG）数据源。

> ⚠️ **v2 架构变更（数据源切换）**
> 旧版（v1）由 `scripts/build_master_kb.py` **正则解析渲染后的 `大师战术与配方百科全书.md`**，走
> JSON→Markdown→正则→JSONL 的有损往返，导致鱼种区 **72% 气压字段被渲染环节丢弃**、同一视频在
> 鱼种区/季节区被**重复计数**（322 条含大量重复与空战术）。
>
> 新版（v2）`build_master_kb.py` **直读上游干净结构化 JSON**
> [`data/master_kb_source.json`](file:///d:/cursor_code/diaoy/data/master_kb_source.json)
> （= 上游 `diaoyu-paqu/fishing_knowledge/knowledge_base.json` 副本，已按 bv_id 去重），
> 映射为 `data/master_kb.jsonl`。准入门槛改为「至少 1 个可执行战术 + 1 个可检索条件」（不再用 master 把关），
> 自动剔除无战术的脏记录。
>
> **效果**：源 285 → 准入 **192 条**（视频 171 + 图文攻略 21），
> **气压非空 28% → 98%**、鱼种非空 94%；新增 `source_type`(video/article) 字段区分来源。
> 重建命令不变：`python scripts/build_master_kb.py`。下文 10.2~10.5 评分/注入逻辑仍适用。

## 10.1 设计目标

| 目标 | 措施 |
|------|------|
| 让 LLM 处方"言之有物"——引用真实大师的具体线组、调漂、配方 | 多维评分召回 Top-3 注入 user prompt |
| 不污染主流程，离线生效 | 物理引擎 / Engine / 兜底链路均不依赖 KB；KB 异常时退化为纯 LLM |
| 不堆 token——只送相关条目 | 阈值 `score >= 3`；全部维度为空返回 `[]` |
| 易维护——语料更新一条命令 | 单脚本 [`scripts/build_master_kb.py`](file:///d:/diaoyu/diaoyu/scripts/build_master_kb.py) 重跑即可 |

## 10.2 全链路一图概览

```
[大师战术与配方百科全书.md]                                       原始语料 4501 行
            │
            ▼  scripts/build_master_kb.py（清洗）
[data/master_kb.jsonl]                                            322 条结构化秘籍
            │
            │  进程级单例懒加载
            ▼
[domain/master_kb.py · MasterKBRetriever]                        多维评分召回
   search(target_fish, season, t_water, pressure_state, top_k=3)
            │
            ▼  format_references_for_prompt
[references_block 文本]
            │
            ▼  build_user_prompt(..., references_block=...)
[domain/prescription.py · PrescriptionService]                   注入 + 调 LLM
   dashscope.Generation.call(model="qwen-turbo", max_tokens=1500)
            │
            ▼
[/api/v2/rescue 返回] prescription{diagnosis, prescriptions[], references[], confidence_note}
```

## 10.3 数据漏斗

| 阶段 | 数量 | 说明 |
|------|------|------|
| md 原文 | 4501 行 / ≈ 25 万字 | 三大部分：鱼种区 / 季节×气温表 / 大师饵料配比清单 |
| 解析后原始记录 | 430 条 | 第一部分（鱼种战术块）+ 第二部分（季节表格行） |
| 准入门槛过滤后 | **322 条** | `master` 非空 且（`line` 或 `recipe`非空） |
| 来源分布 | `fish: 231 / season: 91` | — |
| 季节分布 | 隆冬 30 / 初冬 22 / 初春 52 / 暮春 60 / 初夏 52 / 盛夏 69 / 晚夏秋水 37 | — |

## 10.4 数据 Schema

每条 JSONL 记录字段（见 [`build_master_kb.py`](file:///d:/diaoyu/diaoyu/scripts/build_master_kb.py)）：

| 字段 | 说明 | 示例 |
|------|------|------|
| `master` | 大师姓名 | `化绍新` |
| `title` | 战术 / 录像标题 | `初春鲫鱼搓饵守底` |
| `video_url` | 原视频/出处链接 | `https://...` |
| `source` | `fish` / `season` | — |
| `fish` | 目标鱼种 | `鲫鱼` |
| `season` | 季节标签 | `初春` |
| `temp_min` / `temp_max` | 适用气温区间 (°C) | `5` / `12` |
| `pressure_state` | `骤降` / `上升` / `稳定` / 其他 | `稳定` |
| `line` | 线组（含主线、子线、钩号） | `0.6+0.3 袖 3 号` |
| `float_setup` | 浮漂、调钓 | `调 4 钓 2` |
| `rhythm` | 抛投 / 频率 / 提竿 | `逗钓 + 等口` |
| `flavor` | 味型趋向 | `腥香` |
| `recipe` | 完整饵料配比 | `蓝鲫 40 % + 速攻 30 % + 拉丝粉 20 % + 红虫风暴 10 %` |

> 任意字段允许为空字符串，检索器会跳过空字段不参与评分加成。

## 10.5 检索评分模型

[`MasterKBRetriever.search`](file:///d:/diaoyu/diaoyu/domain/master_kb.py)：

| 维度 | 命中 | 加分 |
|------|------|------|
| 鱼种 | 完全相等 | **+5** |
| 季节 | 完全相等 | **+3** |
| 温区 | `t_water ∈ [temp_min, temp_max]` | **+3** |
| 温区 | 接近边界 ±3 °C | +1 |
| 气压 | 状态精确相等（骤降/上升/稳定） | **+2** |
| 气压 | 同族（如均属下行） | +1 |
| 完整度 | 字段非空个数 × 0.1 | 0 ~ +0.6 |

- **阈值**：`score >= 3` 才返回，避免弱关联污染 Prompt
- **无维度兜底**：当 `target_fish / season / t_water / pressure_state` 全部为空时，直接返回 `[]`
- **季节归一化**：英文 `spring/summer/autumn/winter` 与月份均可被 `_normalize_season` / `_MONTH_TO_SEASON` 映射；如果调用方未显式传 `season`，会通过 `_season_from_temp(t_water)` 用水温反推（≤5 隆冬 / ≤12 初冬 / ≤18 初春 / ≤23 暮春 / ≤28 初夏 / >28 盛夏）

## 10.6 注入 Prompt 的格式

[`format_references_for_prompt`](file:///d:/diaoyu/diaoyu/domain/master_kb.py) 输出形如：

```
【参考大师秘籍 · Top 3】
[1] 大师 化绍新 · 《初春鲫鱼搓饵守底》
   环境: 初春 / 5–12 °C / 稳定
   线组: 0.6+0.3 袖 3 号
   调漂: 调 4 钓 2
   节奏: 逗钓 + 等口
   味型: 腥香
   配方: 蓝鲫 40 % + 速攻 30 % + 拉丝粉 20 % + 红虫风暴 10 %
   视频: https://...
[2] ...
```

由 [`build_user_prompt`](file:///d:/diaoyu/diaoyu/domain/prompts.py) 拼接到 user prompt 末尾；为空则不出现该段。

## 10.7 业务流改造点

```
传感器/上下文 ─► FishingEngine.evaluate ─► metrics + 物理 tags
                                                │
                                                ▼
                          PrescriptionService.generate_prescription
                                                │
                       ┌────────────── _build_references(metrics, fish_context)
                       │  ① fish = fish_context.target
                       │  ② t_water = metrics.t_water_avg
                       │  ③ pressure_state ← metrics.delta_p_2h（≤-1 骤降 / ≥1 上升 / 其他 稳定）
                       │  ④ MasterKBRetriever.get().search(...)  Top-3
                       │  ⑤ format_references_for_prompt
                       ▼
                  references_block (str)
                       │
                       ▼
       build_user_prompt(..., references_block=references_block)
                       │
                       ▼
    dashscope.Generation.call(model="qwen-turbo", max_tokens=1500)
                       │
                       ▼
   {diagnosis, prescriptions[], references[], confidence_note}
```

`references[]` 字段由 [`SYSTEM_PROMPT_FISHING_EXPERT`](file:///d:/diaoyu/diaoyu/domain/prompts.py) 显式约束 LLM 必须填写："使用了哪几位大师"以及对应链接，便于前端展示出处。

## 10.8 重建知识库

语料更新或字段微调后，**只需一条命令**：

```powershell
cd d:\diaoyu\diaoyu
python scripts/build_master_kb.py
```

- 默认输入：项目根 `大师战术与配方百科全书.md`
- 默认输出：`data/master_kb.jsonl`
- 控制台会打印：`总条数 / 按来源 / 按季节` 三组统计
- 重启服务进程 `MasterKBRetriever` 单例自动重载


## 10.9 失败模式与降级

| 失败点 | 行为 |
|--------|------|
| 知识库文件缺失 / 损坏 | `MasterKBRetriever` 加载异常被捕获，`search` 返回 `[]`；处方流程继续走纯 LLM |
| 检索得分全部 < 3 | 返回 `[]`，user prompt 不附 references 块 |
| LLM 调用失败 / 超时 / 缺 Key | [`_fallback_prescription`](file:///d:/diaoyu/diaoyu/domain/prescription.py) 返回固定 JSON（含 `references: []`） |
| `dashscope` 输出非 JSON | 解析异常被捕获，同样走 fallback |

**结论**：RAG 是"锦上添花"——任何环节崩溃都不会阻断 `/api/v2/rescue` 的主链路。

## 10.10 后续可优化方向（未实现）

- 把检索结果按 `(fish, season, pressure_state)` 缓存，省去重复评分
- 把硬编码的评分权重抽到 [`domain/constants.py`](file:///d:/diaoyu/diaoyu/domain/constants.py) 集中调参
- 引入 embedding 召回作为粗排，再用现有规则精排，应对长尾鱼种
