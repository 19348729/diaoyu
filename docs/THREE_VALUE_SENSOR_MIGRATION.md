# 硬件改版后三值传感器全链路适配说明

> 适用场景：硬件由「四温度探头」简化为「单水温 + BMP280」后，对 ESP32 固件、BLE 协议、微信小程序、后端 API 与数据库做的同步适配。
> 涉及范围：**ESP32 固件 + 微信小程序 + 后端 FastAPI + 数据库 ORM**（全链路）。

---

## 一、业务背景

### 1.1 旧硬件（v1）— 4 值采集

| 字段 | 含义 | 来源 |
|------|------|------|
| `t_bottom` | 水底温度 ℃ | DS18B20（深水探头） |
| `t_mid`    | 水下 1 米温度 ℃ | DS18B20（中层探头） |
| `t_surface`| 水面温度 ℃ | DS18B20（浅水探头） |
| `p_local`  | 本地气压 hPa | BMP280 |

> domain 层算法以「水层温差」为主要因子，依赖 `t_bottom / t_mid / t_surface` 共同分析温跃层、热分层等。

### 1.2 新硬件（v2）— 3 值采集

| 字段 | 含义 | 来源 | 引脚 |
|------|------|------|------|
| `t_water` | 水温 ℃ | DS18B20（单探头） | GPIO13 (1-Wire) |
| `t_air`   | 气温 ℃ | BMP280 内置温度 | GPIO15 (SCL) / GPIO2 (SDA) |
| `p_local` | 本地气压 hPa | BMP280 | 同上 |

### 1.3 业务影响

- 不再具备分层水温能力 → 现场无法分析温跃层；
- 新增「气温」字段 → 可用于水气温差、昼夜温差类标签；
- 协议负载缩短 → BLE 实时帧 21B → 17B，历史每条 20B → 16B；
- 数据库需要新增列存储「水温/气温」并保留旧列向后兼容历史数据。

---

## 二、设计决策

| 决策点 | 方案 | 理由 |
|--------|------|------|
| **domain 层是否改动** | **不改动**，保持 `SensorReading(t_bottom, t_mid, t_surface, p_local)` | 算法分布在 analyzers/services/forecast 多个模块，改动面太大；新硬件只有单一水温，可在边界层降级映射 |
| **降级映射策略** | `t_bottom = t_mid = t_surface = t_water` | 三层取同值后温差为 0，温跃层相关因子自然失效，但热水/冷水主分支仍正常工作 |
| **数据库迁移** | 新增 `t_water / t_air` 列；旧列 `t_bottom / t_mid / t_surface` 保留为 nullable | 历史数据不丢失；旧设备如继续在网也可写入旧列 |
| **API schema** | `SensorDataIn` 新旧字段并存，全部 Optional | 兼容老版本小程序，保证灰度过渡期 |
| **BLE 协议版本** | 直接重写帧布局，**不做兼容层** | ESP32 与小程序为强配对发布，强制对齐成本最低 |

---

## 三、协议变更汇总

### 3.1 BLE 实时帧（CMD_REALTIME_DATA = 0x01）

| 项目 | 旧（v1）| 新（v2）|
|------|---------|---------|
| 总长度 | 21 字节 | **17 字节** |
| 布局   | `<BIffff` (cmd/ts/t_bottom/t_mid/t_surface/p_local) | `<BIfff` (cmd/ts/**t_water/t_air**/p_local) |

### 3.2 BLE 历史批帧（CMD_HISTORY_DATA = 0x02）

| 项目 | 旧（v1）| 新（v2）|
|------|---------|---------|
| 头部 | `cmd(1) + count(1)` 不变 | `cmd(1) + count(1)` 不变 |
| 单条记录 | 20 字节 `<Iffff` | **16 字节** `<Ifff` |

### 3.3 HTTP API 字段

`POST /api/predict`、`POST /api/sensor/realtime`、`POST /api/sensor/history` 的 `sensor` / `sensors` / `records` 数组中：

```jsonc
{
  "timestamp": 1715404800,
  "t_water":   18.7,    // 新
  "t_air":     22.3,    // 新
  "p_local":   1013.2,
  // 以下旧字段保留，不传也可
  "t_bottom":  null,
  "t_mid":     null,
  "t_surface": null
}
```

---

## 四、ESP32 侧改动

| 文件 | 改动要点 |
|------|----------|
| `esp32/config.py` | 删除 `PIN_TEMP_DEEP/SURFACE`、`ROM_ADDR_BOTTOM/MID`；新增 `PIN_DS18B20=13`、`PIN_I2C_SDA=2`、`PIN_I2C_SCL=15` |
| `esp32/sensors/temperature.py` | 重写为单探头读取，`read()` 返回 `{"t_water": float}` |
| `esp32/sensors/pressure.py` | 字典键 `t_env` → `t_air` |
| `esp32/storage/ring_buffer.py` | 元组 `(ts, t_bottom, t_mid, t_surface, p_local)` → `(ts, t_water, t_air, p_local)` |
| `esp32/ble/protocol.py` | `encode_realtime_data` 改为 17B；`encode_history_batch` 每条 16B；`<BIfff` |
| `esp32/ble/service.py` | `send_realtime(ts, t_water, t_air, p_local)` 签名调整 |
| `esp32/main.py` | 主循环串联：`temperature.read()` → `pressure.read()` → 三值入环形缓冲 → 实时推送 |

---

## 五、小程序侧改动

| 文件 | 改动要点 |
|------|----------|
| `miniprogram/utils/protocol.js` | `decodeRealtimeData` 改为偏移 5/9/13 解三个 Float32；`decodeHistoryBatch` 单条 16B |
| `miniprogram/utils/api.js` | `reportRealtimeData / reportHistoryBatch / getPrediction` 上报字段改为 `t_water / t_air / p_local` |
| `miniprogram/utils/ble.js` | `globalData.latestData` 字段重命名为 `tWater / tAir / pLocal` |
| `miniprogram/app.js` | `globalData.latestData` 同步字段名 |
| `miniprogram/pages/index/index.js` | `data`、`_updateRealtimeDisplay`、`onTapMockData` 全部切换字段 |
| `miniprogram/pages/index/index.wxml` | 三层水温卡片改为「水温 / 气温」两列 + 气压 |
| `miniprogram/pages/history/history.js` | `summary` 使用 `tWaterMin/Max`、`tAirMin/Max`，删除 `tDiffMax` |
| `miniprogram/pages/history/history.wxml` | 摘要卡片改为水温/气温/气压；表头从 4 列压缩为 3 列 |

---

## 六、后端侧改动

### 6.1 `infrastructure/models.py` — `SensorRecord`

```python
# v2 新增
t_water = Column(Float, nullable=True, comment="水温（DS18B20）")
t_air   = Column(Float, nullable=True, comment="气温（BMP280）")
p_local = Column(Float, nullable=True, comment="本地气压 hPa")
# 旧列保留兼容
t_bottom  = Column(Float, nullable=True, comment="[兼容] 水底温度")
t_mid     = Column(Float, nullable=True, comment="[兼容] 中层温度")
t_surface = Column(Float, nullable=True, comment="[兼容] 水面温度")
```

> **数据库迁移建议**：在生产库执行
> ```sql
> ALTER TABLE sensor_records ADD COLUMN t_water FLOAT NULL;
> ALTER TABLE sensor_records ADD COLUMN t_air   FLOAT NULL;
> ```
> 旧列无需删除。

### 6.2 `server.py` — `SensorDataIn`

新旧字段并存，全部 `Optional[float]`，向下兼容老版本小程序。

### 6.3 `server.py` — `/api/predict` 降级映射

```python
def _to_reading(s: SensorDataIn) -> SensorReading:
    if s.t_water is not None:
        # v2 设备：单一水温投影到三个水层
        t_b = t_m = t_s = s.t_water
    else:
        # v1 设备：保持原值
        t_b, t_m, t_s = s.t_bottom, s.t_mid, s.t_surface
    return SensorReading(timestamp=s.timestamp,
                         t_bottom=t_b, t_mid=t_m, t_surface=t_s,
                         p_local=s.p_local)
```

### 6.4 `server.py` — `/api/sensor/realtime` 与 `/api/sensor/history`

写库时新旧列同时落地：

```python
SensorRecord(
    openid=x_openid,
    timestamp=s.timestamp,
    t_water=s.t_water,  t_air=s.t_air,  p_local=s.p_local,   # v2
    t_bottom=s.t_bottom, t_mid=s.t_mid, t_surface=s.t_surface  # v1 兼容
)
```

---

## 七、烧录与发布清单

### 7.1 ESP32 需要上传的文件

```
main.py
config.py
sensors/__init__.py
sensors/temperature.py
sensors/pressure.py
ble/__init__.py
ble/protocol.py
ble/service.py
storage/__init__.py
storage/ring_buffer.py
utils/__init__.py
utils/time_sync.py
```

> **不要**上传：`water_air_sensor.py`、`ds18b20_single_bus.py(.bak)`、`ds18b20_test/`（独立测试脚本，与主程序无关）。

### 7.2 后端发布步骤

1. 备份数据库；
2. 执行第 6.1 节的两条 `ALTER TABLE`；
3. 部署最新 `server.py / infrastructure/models.py`；
4. 重启 `gunicorn`；
5. 校验 `/health` 与 `/api/sensor/realtime`（带 `t_water/t_air` 字段）落库正常。

### 7.3 小程序发布

1. 微信开发者工具上传新版本；
2. 灰度发布或全量；
3. 老版本小程序仍可工作（后端字段兼容）。

---

## 八、验收清单

- [ ] ESP32 串口能稳定打印水温 / 气温 / 气压三个值；
- [ ] 小程序连接后实时卡片正确显示「水温 / 气温 / 气压」；
- [ ] 历史页表头 3 列，摘要显示水温/气温/气压范围；
- [ ] 后端 `sensor_records` 表中 `t_water / t_air` 有值，旧列为 NULL；
- [ ] `/api/predict` 返回 `bite_index`、`recommended_fish` 等字段不报错；
- [ ] domain 层日志中温跃层相关因子正常退化（不致命）。

---

## 九、回滚策略

若新硬件上线后出现严重问题，回滚步骤：

1. ESP32 端：刷回上一版本固件（v1 四探头版本）；
2. 小程序端：在微信后台回滚到上一审核版本；
3. 后端：保持当前版本即可（旧字段仍可写入），无需回滚 SQL。

---

*文档创建于 v2 三值传感器适配完成时；如需进一步细化，可结合 `docs/BLE_MANUAL_PULL_PATCH.md` 的手动拉取改动一并查阅。*
