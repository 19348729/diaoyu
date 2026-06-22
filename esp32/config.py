"""
全局配置常量 (Global Configuration)
====================================
集中管理所有硬件引脚、采样参数、BLE 参数、缓冲区容量等。
修改硬件接线或调整参数时只需改此文件。

硬件版本: v2（单水温 DS18B20 + BMP280）
"""

# ──────────────────────────────────────────────
#  GPIO 引脚定义
# ──────────────────────────────────────────────

# DS18B20 温度传感器 - 单探头（水温）
PIN_DS18B20 = 32            # GPIO13: 水温（1-Wire 单总线）

# BMP280 气压传感器 - I2C 软总线
PIN_I2C_SDA = 2             # GPIO2:  I2C 数据线
PIN_I2C_SCL = 15            # GPIO15: I2C 时钟线
BMP280_I2C_ADDR = 0x76      # BMP280 默认 I2C 地址（SDO 接 GND 时为 0x76，接 VCC 时为 0x77）

# ──────────────────────────────────────────────
#  采样参数
# ──────────────────────────────────────────────
SAMPLE_INTERVAL_SEC = 60         # 数据采集间隔（秒）
DS18B20_CONVERSION_MS = 750      # DS18B20 12位精度转换等待时间（毫秒）
DS18B20_MAX_RETRIES = 5          # DS18B20 读取失败最大重试次数

# ──────────────────────────────────────────────
#  环形缓冲区
# ──────────────────────────────────────────────
RING_BUFFER_CAPACITY = 2160      # 缓冲区容量（条）= 36小时 × 60分 / 1分

# ──────────────────────────────────────────────
#  BLE 参数
# ──────────────────────────────────────────────
BLE_DEVICE_NAME = "FishProbe"    # BLE 广播设备名称

# BLE GATT 服务与特征 UUID（自定义 128-bit UUID）
BLE_SERVICE_UUID = "12345678-1234-5678-1234-56789abcdef0"
BLE_TX_CHAR_UUID = "12345678-1234-5678-1234-56789abcdef1"  # ESP32 -> 小程序（Notify）
BLE_RX_CHAR_UUID = "12345678-1234-5678-1234-56789abcdef2"  # 小程序 -> ESP32（Write）

# BLE 历史数据批量发送时每批的最大条数（受 MTU 限制，设为 8 以适配 iOS 185 字节 MTU）
BLE_BATCH_SIZE = 8

# ──────────────────────────────────────────────
#  通信协议指令码
# ──────────────────────────────────────────────
CMD_TIME_SYNC = 0x01        # 对表指令（小程序 -> ESP32）
CMD_REALTIME_DATA = 0x02    # 实时数据帧（ESP32 -> 小程序）
CMD_HISTORY_DATA = 0x03     # 历史数据批量帧（ESP32 -> 小程序）
CMD_SYNC_ACK = 0x04         # 同步确认（小程序 -> ESP32）
CMD_STATUS_QUERY = 0x05     # 状态查询（小程序 -> ESP32）
CMD_STATUS_REPLY = 0x06     # 状态回复（ESP32 -> 小程序）
CMD_PULL_HISTORY = 0x07     # 手动拉取一批历史（小程序 -> ESP32，无载荷）
CMD_BULK_DUMP = 0x08        # 全量快闪拉取（小程序 -> ESP32）
CMD_DUMP_COMPLETE = 0x09    # 全量快闪结束标记（ESP32 -> 小程序）
CMD_ENTER_REALTIME = 0x0A   # 切换实时 Notify 模式（小程序 -> ESP32）

# ──────────────────────────────────────────────
#  充电宝保活参数（高功耗模式，已实测可用）
# ──────────────────────────────────────────────
# 组合策略：
#   1) CPU 主频拉满到 240MHz（基线电流 +~20mA）
#   2) WiFi STA 常驻 active（不连接 AP，仅射频开启，+~50~70mA，最有效）
#   3) 纯 CPU 忙循环（全程不睡眠）让 CPU 长期高负载
#   4) 周期性 WiFi 扫描踢脚，产生瞬态 ~200mA 电流尖峰
KEEPALIVE_CPU_FREQ_HZ = 240_000_000   # CPU 主频（240MHz 最高档）
KEEPALIVE_WIFI_ALWAYS_ON = True       # WiFi STA 是否常驻 active
KEEPALIVE_BUSY_LOOP_MODE = True       # 是否启用纯 CPU 忙循环保活（最可靠，但耗电高）
#                                       True  → 60s 全程 CPU 高负载，避免进入 light-sleep
#                                       False → 低耗电脉冲模式（但可能被充电宝断电）
KEEPALIVE_WIFI_KICK_INTERVAL_MS = 3000  # WiFi 扫描踢脚间隔（毫秒）
KEEPALIVE_WIFI_KICK_ENABLED = True    # 是否启用 WiFi 扫描踢脚
# 仅在 BUSY_LOOP_MODE=False 时生效的占空比脉冲参数
KEEPALIVE_PULSE_INTERVAL_MS = 500     # 每隔多久执行一次 CPU 脉冲（毫秒）
KEEPALIVE_PULSE_DURATION_MS = 200     # 每次脉冲持续时间（毫秒）
KEEPALIVE_WIFI_KICK_INTERVAL = 20     # 兼容旧字段（脉冲模式下每多少次脉冲踢一次）
