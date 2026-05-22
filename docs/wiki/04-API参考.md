# 04 API 参考

所有 API 实现在 [`server.py`](file:///d:/diaoyu/diaoyu/server.py)，应用挂载于 `https://<host>/api/...`。生产域名示例：`https://ks.gzbaoge.com`。

约定：

- 所有需要用户身份的接口通过请求头 `X-OpenID` 透传微信 openid；缺失时多数接口回退到 `test_openid_user_001`，部分（历史 / 会话）会返回 401。
- 内容协商：请求体均为 `application/json`，由 Pydantic 校验。
- Swagger 文档：`/docs`；ReDoc：`/redoc`。

## 4.1 系统类

### `GET /health`
健康检查，[`server.py` 行 126](file:///d:/diaoyu/diaoyu/server.py)。
返回：`{"status":"ok","timestamp":<ts>,"version":"1.0.0"}`

### `GET /api/fish-types`
列出所有支持鱼种与水层。[`server.py` 行 136](file:///d:/diaoyu/diaoyu/server.py)。

## 4.2 预测类

### `POST /api/predict`
主预测接口。[`server.py` 行 903](file:///d:/diaoyu/diaoyu/server.py)。

**请求体**（[`PredictRequest`](file:///d:/diaoyu/diaoyu/server.py)）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `fish_type` | str | `"auto"` 或 `FISH_PROFILES` 中的鱼种名 |
| `sensors[]` | array | 传感器时序，至少 1 条；含 `timestamp`、`t_water`/`t_air` 或 `t_bottom/t_mid/t_surface`、`p_local` |
| `lat`/`lng`/`altitude` | float | 经纬度与海拔 |
| `user_inventory` | dict? | 可选，前端预聚合的装备库；不传则后端从 DB 查询 |

**响应**（`PredictResponse`）核心字段：

- `recommended_fish` / `recommended_fishes[]`：主推荐与全鱼种排行榜
- `bite_index` (0–100) / `do_trend` / `confidence`
- `report_stage`：`instant` / `brief` / `standard` / `full`
- `tactical_tags[]`：参见 [`tags.py`](file:///d:/diaoyu/diaoyu/domain/tags.py)
- `time_period_advice` / `season_note`
- `weather_info`、`solunar_info`、`tactical_advice`

**副作用**：若 `X-OpenID` 有效，写入 `prediction_history` 表（[`server.py` 行 1010-1029](file:///d:/diaoyu/diaoyu/server.py)）。

### `POST /api/predict/weather`
纯天气模式预测，无需传感器数据。[`server.py` 行 1043](file:///d:/diaoyu/diaoyu/server.py)。

请求：`fish_type` + `lat` + `lng`。
特点：置信度固定 30%，`report_stage="weather_only"`，气温由 `hourly_forecast[0]` 提供，水温通过 [`AirToWaterConfig.estimate_water_temp`](file:///d:/diaoyu/diaoyu/domain/constants.py) 推算。

## 4.3 预报类

### `GET /api/forecast/today`
今日 24h 鱼情。[`server.py` 行 1121](file:///d:/diaoyu/diaoyu/server.py)。

参数：`lat`、`lng`、`fish_type`（默认鲫鱼）。
返回：`hourly_scores[]`、`best_windows[]`（top 3 的 2 小时滑动窗口）、`daily_summary`。
实现：[`FishingForecastService`](file:///d:/diaoyu/diaoyu/domain/forecast.py)。

### `GET /api/forecast/3day`
未来 3 天日历。[`server.py` 行 1157](file:///d:/diaoyu/diaoyu/server.py)。
返回每日评分、`best_day` 与对比文案。

## 4.4 数据上报与拉取

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/sensor/realtime` | 单条传感器实时上报，写入 `sensor_records` |
| POST | `/api/sensor/history` | 批量上报历史数据 |
| GET | `/api/sensor/records?limit=1440` | 拉取最近的传感器记录，按时间升序返回 |

需要 `X-OpenID`。源码：[`server.py` 行 1188-1286](file:///d:/diaoyu/diaoyu/server.py)。

## 4.5 用户与日志

### `POST /api/login`
微信登录。[`server.py` 行 1296](file:///d:/diaoyu/diaoyu/server.py)。
- 入参：`{"code": "<wx_code>"}`；`code == "test"` 直接返回测试 openid。
- 内部调用：`https://api.weixin.qq.com/sns/jscode2session`。
- 副作用：upsert `users` 表。

### `GET /api/history/logs?limit=20`
返回当前 openid 的预测历史，按 `created_at` 倒序。[`server.py` 行 1331](file:///d:/diaoyu/diaoyu/server.py)。

## 4.6 钓鱼会话

### `POST /api/session/save`
[`server.py` 行 1399](file:///d:/diaoyu/diaoyu/server.py)。把一次出钓汇总写入 `fishing_sessions`。若未传 `location_name`，调用 LBS 反解。

请求字段（节选）：`start_time / end_time / duration_min / data_points / lat / lng / t_water_* / t_air_* / p_start / p_end / p_trend / weather_text / wind_desc / bite_index_max / bite_index_avg / recommended_fish`。

### `GET /api/session/list?limit=20`
按时间倒序列出 openid 的所有会话。[`server.py` 行 1457](file:///d:/diaoyu/diaoyu/server.py)。

## 4.7 数字钓箱（装备库）

所有装备类接口前缀 `/api/inventory/`，统一通过 `X-OpenID` 隔离用户私有数据。

### 鱼竿（[`server.py` 行 147–366](file:///d:/diaoyu/diaoyu/server.py)）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET  | `/api/inventory/rods` | 公共品牌库（多级级联）；空时自动同步 `domain.rods.ROD_DATABASE` 种子 |
| POST | `/api/inventory/rod` | 录入到用户钓箱；`is_custom=true` 时调用 `RodVerificationService` 大模型核验，校验通过自动收录到 `public_rods` |
| GET  | `/api/inventory/rod/{id}` | 详情 |
| PUT  | `/api/inventory/rod/{id}` | 修改 |
| DELETE | `/api/inventory/rod/{id}` | 删除 |
| GET  | `/api/inventory/rods/user` | 用户全部鱼竿 |

### 主线、子线双钩、浮漂

- 主线：`/api/inventory/mainline[/{id}]`、`/api/inventory/mainlines/user`（[`server.py` 行 376-468](file:///d:/diaoyu/diaoyu/server.py)）
- 子线双钩：`/api/inventory/sublinehook[/{id}]`、`/api/inventory/sublinehooks/user`（[`server.py` 行 479-575](file:///d:/diaoyu/diaoyu/server.py)）
- 浮漂：`/api/inventory/float[/{id}]`、`/api/inventory/floats/user`（[`server.py` 行 587-693](file:///d:/diaoyu/diaoyu/server.py)）

均提供完整 CRUD + 用户列表。

### 饵料（[`server.py` 行 706-853](file:///d:/diaoyu/diaoyu/server.py)）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/inventory/bait` | 录入饵料 |
| POST | `/api/inventory/bait/old-three` | 一键添加"老三样"（野战蓝鲫 / 九一八 / 速攻 2 号） |
| GET/PUT/DELETE | `/api/inventory/bait/{id}` | 单条 CRUD |
| GET | `/api/inventory/baits/public` | 公共饵料库（按 category → brand → name 聚合） |
| GET | `/api/inventory/baits/user` | 用户饵料 |

## 4.8 V2 智能救场

### `POST /api/v2/rescue`
[`server.py` 行 1512](file:///d:/diaoyu/diaoyu/server.py)。

入参 `RescueRequest`：传感器时序、用户主观症状（[`symptom_tags.py`](file:///d:/diaoyu/diaoyu/domain/symptom_tags.py)）、鱼种 / 钓法 / 饵料上下文、装备库。

流程：
1. `_to_reading` 兼容 V1/V2 → 构造 `SensorTimeSeries`
2. `FishingEngine.evaluate(series)` → `metrics + 物理 tags`
3. `MasterKBRetriever.search(target_fish, t_water, pressure_state)` → 召回 Top-3 大师秘籍（RAG）
4. `PrescriptionService.generate_prescription(...)` → 将检索结果注入 user prompt → 通义千问 → JSON 处方

返回：`engine_metrics` / `engine_tags` / `prescription{diagnosis, prescriptions[], references[], confidence_note}`。

其中 `references[]` 为 LLM 根据 RAG 参考引用的大师，单元素形如 `{master, title, url}`，详见 [10-大师知识库RAG](./10-大师知识库RAG.md)。

### `GET /api/v2/poster/{session_id}`
[`server.py` 行 1560](file:///d:/diaoyu/diaoyu/server.py)。读取 `fishing_sessions` 行，根据 `bite_index_avg` 划分 `catch_level`（爆护 / 稳赚 / 惨淡 / 空军），交由 [`PosterGenerator`](file:///d:/diaoyu/diaoyu/domain/poster.py) 生成海报数据。

## 4.9 错误码与错误响应

FastAPI 默认错误体格式：`{"detail": "<msg>"}`。

常见状态码：

| 状态 | 触发条件 |
|------|---------|
| 400 | `fish_type` 不在 `FISH_PROFILES` 中 |
| 401 | 受保护接口未传 `X-OpenID` |
| 404 | 装备记录或会话不存在 / 无权访问 |
| 502 | 天气 API 不可用（`/api/forecast/today` 等） |
