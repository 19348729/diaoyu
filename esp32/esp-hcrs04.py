# DYP-L08B50TW-V3.0 防水超声波测距 + ESP-NOW 广播 (ESP32-B)
# ============================================================
# 部署目标: ESP32-B（单板独立烧录此一个文件即可）
# 功能:
#   1. 周期性触发 DYP-L08B50TW-V3.0 测距（下降沿触发 + UART 接收）
#   2. 通过 ESP-NOW **广播**把距离发给 ESP32-A 主板
#      - 广播地址 ff:ff:ff:ff:ff:ff，无需事先配对 MAC
#      - ESP32-A 端 sonar.protocol 与本帧严格对齐（magic=0x5A 过滤）
#
# 接线说明 (30针 ESP32):
#   红   (VCC) -> 5V (VIN/VBUS)
#   黑   (GND) -> GND
#   黄   (RX)  -> GPIO 5  (触发引脚, 下降沿触发测量)
#   白   (TX)  -> GPIO 18 (UART 接收, 115200 bps)
#
# 通信方式: 下降沿触发 + UART 返回
#   1. 黄线拉低 >= 100µs 后拉高 -> 触发一次测量
#   2. 白线通过 UART 返回 4 字节: [0xFF, Dist_H, Dist_L, Checksum]
#   3. 距离(mm) = Dist_H * 256 + Dist_L
#   4. 校验和: Checksum = (0xFF + Dist_H + Dist_L) & 0xFF
#   5. 距离 = 65533mm 表示超出量程 (无目标)
#   波特率: 115200
#   注意: 两次测量间隔需 >= 1000ms, 否则返回缓存数据
#
# ESP-NOW 包结构（共 8 字节，小端序 <BBHBBH）:
#   [magic=0x5A] [ver=0x01] [distance_mm uint16] [status uint8] [seq uint8] [crc uint16]
#   status: 0=正常 1=超出量程 2=过近 3=通信失败
#   crc:    前 6 字节累加和取低 16 位

from machine import Pin, UART
import time
import struct
import network
import espnow

TRIGGER_PIN = 5
DATA_PIN = 18
UART_NUM = 2
UART_BAUD = 115200

# 测量范围 (cm)
MIN_DISTANCE = 5
MAX_DISTANCE = 200

# 超出量程标记值（厂商协议）
OUT_OF_RANGE = 65533

# ── ESP-NOW 协议常量（与 ESP32-A 端 esp32/sonar/protocol.py 一致） ──
SONAR_MAGIC = 0x5A
SONAR_VER = 0x01
DIST_INVALID = 0xFFFF

STATUS_OK = 0
STATUS_OUT_OF_RANGE = 1
STATUS_TOO_NEAR = 2
STATUS_COMM_FAIL = 3

# 广播 MAC（无需预先配对 ESP32-A）
BROADCAST_MAC = b"\xff\xff\xff\xff\xff\xff"

# 发送周期（毫秒）—— 与 DYP 厂商最小间隔一致
SAMPLE_INTERVAL_MS = 1000


# ──────────────────────────────────────────────
#  超声波测距（沿用原始逻辑）
# ──────────────────────────────────────────────
trigger = Pin(TRIGGER_PIN, Pin.OUT)
trigger.on()  # 默认高电平

uart = UART(UART_NUM, UART_BAUD, rx=DATA_PIN)

time.sleep_ms(100)


def measure_distance_mm():
    """触发测量并返回距离 (mm) 与状态。

    Returns:
        (distance_mm: int, status: int)
        通信失败 -> (DIST_INVALID, STATUS_COMM_FAIL)
        超出量程 -> (DIST_INVALID, STATUS_OUT_OF_RANGE)
        距离过近 -> (distance_mm, STATUS_TOO_NEAR)
        正常     -> (distance_mm, STATUS_OK)
    """
    # 清空接收缓冲
    while uart.any():
        uart.read()

    # 下降沿触发
    trigger.off()
    time.sleep_us(500)
    trigger.on()

    # 等待并读取 4 字节响应
    buf = bytearray()
    t0 = time.ticks_ms()
    while len(buf) < 4:
        if time.ticks_diff(time.ticks_ms(), t0) > 200:
            return DIST_INVALID, STATUS_COMM_FAIL
        chunk = uart.read(4 - len(buf))
        if chunk:
            buf.extend(chunk)

    # 验证帧头
    if buf[0] != 0xFF:
        return DIST_INVALID, STATUS_COMM_FAIL

    # 验证校验和
    checksum = (buf[0] + buf[1] + buf[2]) & 0xFF
    if buf[3] != checksum:
        return DIST_INVALID, STATUS_COMM_FAIL

    # 计算距离 (mm)
    distance_mm = (buf[1] << 8) | buf[2]

    if distance_mm == OUT_OF_RANGE:
        return DIST_INVALID, STATUS_OUT_OF_RANGE

    distance_cm = distance_mm / 10.0
    if distance_cm < MIN_DISTANCE:
        # 过近时仍把测得的距离一并发出去，便于上层告警
        return distance_mm, STATUS_TOO_NEAR

    return distance_mm, STATUS_OK


# ──────────────────────────────────────────────
#  ESP-NOW 发送
# ──────────────────────────────────────────────
def init_espnow():
    """初始化 STA + ESP-NOW，加入广播 peer。"""
    sta = network.WLAN(network.STA_IF)
    sta.active(True)
    # 不连接任何 AP；ESP-NOW 默认使用 STA 信道（信道 1）

    e = espnow.ESPNow()
    e.active(True)
    try:
        e.add_peer(BROADCAST_MAC)
    except OSError as err:
        # 已存在 peer 时 add_peer 会抛 OSError，可忽略
        msg = str(err)
        if "ESP_ERR_ESPNOW_EXIST" not in msg and "exists" not in msg:
            print("[ESP-NOW] add_peer 失败（继续运行）: {}".format(err))
    print("[ESP-NOW] 已就绪，本机 STA MAC =", _format_mac(sta.config('mac')))
    return e


def _format_mac(mac_bytes):
    return ":".join("{:02X}".format(b) for b in mac_bytes)


def _calc_crc(payload6: bytes) -> int:
    """前 6 字节累加和取低 16 位。"""
    s = 0
    for b in payload6:
        s = (s + b) & 0xFFFF
    return s


def encode_sonar_packet(distance_mm: int, status: int, seq: int) -> bytes:
    """打包一帧 8 字节 ESP-NOW 数据。"""
    if distance_mm < 0 or distance_mm > 0xFFFF:
        distance_mm = DIST_INVALID
    head = struct.pack("<BBHBB", SONAR_MAGIC, SONAR_VER,
                       distance_mm & 0xFFFF, status & 0xFF, seq & 0xFF)
    crc = _calc_crc(head)
    return head + struct.pack("<H", crc)


# ──────────────────────────────────────────────
#  主循环
# ──────────────────────────────────────────────
print("DYP-L08B50TW-V3.0 超声波测距 + ESP-NOW 广播 (ESP32-B)")
print("波特率: 115200 | 触发: 下降沿 | 周期: {}ms".format(SAMPLE_INTERVAL_MS))
print("=" * 50)

espnow_dev = init_espnow()
seq = 0

while True:
    loop_start = time.ticks_ms()

    distance_mm, status = measure_distance_mm()

    # 控制台诊断输出
    if status == STATUS_COMM_FAIL:
        print("[seq={}] 通信失败".format(seq))
    elif status == STATUS_OUT_OF_RANGE:
        print("[seq={}] 超出量程 (>{}cm)".format(seq, MAX_DISTANCE))
    elif status == STATUS_TOO_NEAR:
        print("[seq={}] 距离过近: {:.1f} cm".format(seq, distance_mm / 10.0))
    else:
        print("[seq={}] 距离: {:.1f} cm".format(seq, distance_mm / 10.0))

    # 通过 ESP-NOW 广播发送
    pkt = encode_sonar_packet(distance_mm, status, seq)
    try:
        espnow_dev.send(BROADCAST_MAC, pkt, False)  # 第三参数=sync，False 异步更省时
    except Exception as e:
        print("[ESP-NOW] 发送异常: {}".format(e))

    seq = (seq + 1) & 0xFF

    # 精确等待到下一周期
    elapsed = time.ticks_diff(time.ticks_ms(), loop_start)
    sleep_ms = SAMPLE_INTERVAL_MS - elapsed
    if sleep_ms > 0:
        time.sleep_ms(sleep_ms)
