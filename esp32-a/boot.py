# ESP32-A 边缘物联数据节点 — DYP-L08B50TW v3.0 + ESP-NOW
# ============================================================
# 部署目标: ESP32-A（单板独立烧录此一个文件即可）
# 定位: 轻量、省电、抗干扰、自适应的边缘采集节点
#
# 功能:
#   1. 通过 UART 采集 DYP-L08B50TW v3.0 超声波测距数据
#   2. 通电前 10 秒自动校准基准水深 BaseDepth
#   3. 根据 BaseDepth 动态计算自适应阈值（浅水收紧、深水放宽）
#   4. 双轨鱼讯判定引擎:
#      - 轨 A: 静态绝对值突刺（中层大鱼截杀），连续 3 帧确认
#      - 轨 B: 动态方差波动（底层鱼拱窝），20 帧标准差
#   5. 通过 ESP-NOW 广播精简 10 字节数据帧给岸上 ESP32-B
#
# 接线说明 (30 针 ESP32):
#   红   (VCC) -> 5V (VIN/VBUS)
#   黑   (GND) -> GND
#   黄   (RX)  -> GPIO 5  (触发引脚, 下降沿触发测量)
#   白   (TX)  -> GPIO 18 (UART 接收, 115200 bps)
#
# 传感器通信协议 (下降沿触发 + UART 返回):
#   1. 黄线拉低 >= 100µs 后拉高 -> 触发一次测量
#   2. 白线通过 UART 返回 4 字节: [0xFF, Dist_H, Dist_L, Checksum]
#   3. 距离(mm) = Dist_H * 256 + Dist_L
#   4. 校验和: Checksum = (0xFF + Dist_H + Dist_L) & 0xFF
#   5. 距离 = 65533mm 表示超出量程 (无目标)
#
# ESP-NOW 上行帧格式（共 10 字节，小端序 <IHHBB）:
#   [timestamp(4)] [base_depth(2)] [current_depth(2)] [alarm_level(1)] [checksum(1)]
#   alarm_level: 0=无鱼, 1=底层拱窝, 2=中层截杀
#   checksum:    前 9 字节逐字节异或

from machine import Pin, UART
import time
import struct
import math
import network
import espnow


# ──────────────────────────────────────────────
#  硬件引脚配置
# ──────────────────────────────────────────────
TRIGGER_PIN = 5           # GPIO5:  下降沿触发测量
DATA_PIN = 18             # GPIO18: UART 数据接收
UART_NUM = 2              # 使用 UART2
UART_BAUD = 115200        # 波特率


# ──────────────────────────────────────────────
#  传感器常量
# ──────────────────────────────────────────────
OUT_OF_RANGE = 65533      # 超出量程标记值（厂商协议）
DIST_INVALID = 0xFFFF     # 无效距离占位


# ──────────────────────────────────────────────
#  采样与校准参数
# ──────────────────────────────────────────────
SAMPLE_INTERVAL_MS = 100          # 采样间隔 100ms = 10fps
CALIBRATION_DURATION_MS = 10000   # 校准阶段 10 秒
CALIBRATION_MIN_SAMPLES = 10     # 校准所需最少有效帧数


# ──────────────────────────────────────────────
#  告警级别常量
# ──────────────────────────────────────────────
ALARM_NONE = 0            # 无鱼
ALARM_BOTTOM_FISH = 1     # 底层拱窝（鲤鱼/鲫鱼贴底拱窝搅局）
ALARM_MID_FISH = 2        # 中层截杀（鲢鳙/草鱼突然截杀中心波束）


# ──────────────────────────────────────────────
#  ESP-NOW 参数
# ──────────────────────────────────────────────
BROADCAST_MAC = b"\xff\xff\xff\xff\xff\xff"  # 广播 MAC，无需配对
DATA_FRAME_FMT = '<IHHBB'                    # 10 字节帧格式
DATA_FRAME_SIZE = 10                          # struct.calcsize(DATA_FRAME_FMT)


# ──────────────────────────────────────────────
#  滚动窗口与判定参数
# ──────────────────────────────────────────────
WINDOW_SIZE = 20          # 20 帧滚动窗口 ≈ 2 秒历史
CONSECUTIVE_FRAMES = 3    # 轨 A 连续帧确认阈值（排除气泡噪声）
HEARTBEAT_INTERVAL = 30   # 每 30 帧输出一次心跳诊断


# ──────────────────────────────────────────────
#  硬件初始化
# ──────────────────────────────────────────────
trigger = Pin(TRIGGER_PIN, Pin.OUT)
trigger.on()  # 默认高电平

uart = UART(UART_NUM, UART_BAUD, rx=DATA_PIN)

time.sleep_ms(100)  # 等待硬件稳定


# ──────────────────────────────────────────────
#  传感器数据采集
# ──────────────────────────────────────────────
def measure_distance_mm():
    """触发 DYP-L08B50TW 测量并返回距离 (mm)。

    Returns:
        int: 有效距离（毫米），失败或超量程返回 None
    """
    # 清空接收缓冲区
    while uart.any():
        uart.read()

    # 下降沿触发（拉低 >= 100µs 后拉高）
    trigger.off()
    time.sleep_us(500)
    trigger.on()

    # 等待并读取 4 字节响应（超时 200ms）
    buf = bytearray()
    t0 = time.ticks_ms()
    while len(buf) < 4:
        if time.ticks_diff(time.ticks_ms(), t0) > 200:
            return None
        chunk = uart.read(4 - len(buf))
        if chunk:
            buf.extend(chunk)

    # 验证帧头 (固定 0xFF)
    if buf[0] != 0xFF:
        return None

    # 验证校验和
    checksum = (buf[0] + buf[1] + buf[2]) & 0xFF
    if buf[3] != checksum:
        return None

    # 计算距离 (mm)
    distance_mm = (buf[1] << 8) | buf[2]

    # 超出量程标记
    if distance_mm == OUT_OF_RANGE:
        return None

    return distance_mm


# ──────────────────────────────────────────────
#  ESP-NOW 初始化
# ──────────────────────────────────────────────
def _format_mac(mac_bytes):
    return ":".join("{:02X}".format(b) for b in mac_bytes)


def init_espnow():
    """初始化 STA WiFi + ESP-NOW，注册广播 peer。

    Returns:
        espnow.ESPNow 实例
    """
    sta = network.WLAN(network.STA_IF)
    sta.active(True)

    # 关闭 AP（仅需 STA 模式供 ESP-NOW 使用）
    ap = network.WLAN(network.AP_IF)
    if ap.active():
        ap.active(False)

    # 显式锁定 WiFi 信道为 1，确保与岸上 ESP32-B 一致
    try:
        sta.config(channel=1)
    except Exception as err:
        print("[ESP-NOW] 锁定 channel=1 失败（继续运行）: {}".format(err))

    e = espnow.ESPNow()
    e.active(True)

    try:
        e.add_peer(BROADCAST_MAC)
    except OSError as err:
        msg = str(err)
        if "EXIST" not in msg and "exists" not in msg:
            print("[ESP-NOW] add_peer 失败（继续运行）: {}".format(err))

    try:
        ch = sta.config('channel')
    except Exception:
        ch = '?'
    print("[ESP-NOW] 已就绪，本机 STA MAC = {} channel = {}".format(
        _format_mac(sta.config('mac')), ch))
    return e


# ──────────────────────────────────────────────
#  基准水深自动锁定（通电前 10 秒）
# ──────────────────────────────────────────────
def calibrate_base_depth():
    """通电启动后前 10 秒采样，自动锁定钓点基准水深。

    逻辑:
        1. 持续触发传感器测量 ~100 帧（10s × 10fps）
        2. 剔除无效帧（通信失败、超量程）
        3. 有效帧取算术平均值 → BaseDepth
        4. 有效帧不足时使用保守默认值 1500mm

    Returns:
        int: 基准水深 BaseDepth (mm)
    """
    print("[校准] 开始基准水深校准（{}秒静默采样）...".format(
        CALIBRATION_DURATION_MS // 1000))
    samples = []
    valid_count = 0
    invalid_count = 0
    t_start = time.ticks_ms()

    while time.ticks_diff(time.ticks_ms(), t_start) < CALIBRATION_DURATION_MS:
        loop_t = time.ticks_ms()
        dist = measure_distance_mm()
        if dist is not None:
            samples.append(dist)
            valid_count += 1
        else:
            invalid_count += 1

        # 每 20 帧输出校准进度
        total = valid_count + invalid_count
        if total % 20 == 0:
            elapsed_s = time.ticks_diff(time.ticks_ms(), t_start) / 1000
            print("[校准] {:.1f}s 有效帧={} 无效帧={}".format(
                elapsed_s, valid_count, invalid_count))

        # 精确等待到下一采样周期
        elapsed = time.ticks_diff(time.ticks_ms(), loop_t)
        wait = SAMPLE_INTERVAL_MS - elapsed
        if wait > 0:
            time.sleep_ms(wait)

    # 计算基准水深
    if len(samples) < CALIBRATION_MIN_SAMPLES:
        print("[校准] ⚠ 有效帧不足（{}/{}），使用默认 BaseDepth=1500mm".format(
            len(samples), CALIBRATION_MIN_SAMPLES))
        return 1500

    base_depth = int(sum(samples) / len(samples) + 0.5)  # 四舍五入
    print("[校准] ✓ 完成！BaseDepth = {}mm（{} 有效帧 / {} 总帧）".format(
        base_depth, valid_count, valid_count + invalid_count))
    return base_depth


# ──────────────────────────────────────────────
#  灵敏度增益自适应调谐
# ──────────────────────────────────────────────
def calc_thresholds(base_depth):
    """根据基准水深动态计算双轨告警阈值。

    公式（单位：mm）:
        Th_mid   = 150 + 0.043 × (BaseDepth - 1500)  — 中层鱼跳变阈值
        SD_floor = 8.0 + 0.002 × (BaseDepth - 1500)  — 底层鱼方差告警线

    浅水收紧（防误报）、深水放宽（补灵敏度损失）。

    Args:
        base_depth: 基准水深 (mm)

    Returns:
        (th_mid: float, sd_floor: float) 单位 mm
    """
    delta = base_depth - 1500
    th_mid = 150.0 + 0.043 * delta
    sd_floor = 8.0 + 0.002 * delta

    # 保护下限：即使极浅水域也保留最低灵敏度
    th_mid = max(th_mid, 80.0)
    sd_floor = max(sd_floor, 4.0)

    print("[阈值] Th_mid = {:.1f}mm  SD_floor = {:.1f}mm  (BaseDepth={}mm)".format(
        th_mid, sd_floor, base_depth))
    return th_mid, sd_floor


# ──────────────────────────────────────────────
#  统计工具函数
# ──────────────────────────────────────────────
def calc_std_dev(window):
    """计算列表的总体标准差。

    Args:
        window: 数值列表（距离 mm）

    Returns:
        float: 标准差 (mm)，样本不足时返回 0.0
    """
    n = len(window)
    if n < 2:
        return 0.0
    mean = sum(window) / n
    variance = sum((x - mean) ** 2 for x in window) / n
    return math.sqrt(variance)


# ──────────────────────────────────────────────
#  ESP-NOW 数据帧编码
# ──────────────────────────────────────────────
def encode_data_frame(timestamp, base_depth, current_depth, alarm_level):
    """打包 10 字节 ESP-NOW 上行数据帧。

    帧格式 <IHHBB:
        timestamp(4) + base_depth(2) + current_depth(2) + alarm_level(1) + checksum(1)

    校验和: 前 9 字节逐字节异或 (XOR)

    Args:
        timestamp:     毫秒级时间戳 (time.ticks_ms())
        base_depth:    基准水深 mm
        current_depth: 当前水深 mm
        alarm_level:   0=无鱼 / 1=底层拱窝 / 2=中层截杀

    Returns:
        bytes: 10 字节数据帧
    """
    payload = struct.pack('<IHHB',
                          timestamp & 0xFFFFFFFF,
                          base_depth & 0xFFFF,
                          current_depth & 0xFFFF,
                          alarm_level & 0xFF)
    # XOR 校验和
    chk = 0
    for b in payload:
        chk ^= b
    return payload + struct.pack('B', chk)


# ──────────────────────────────────────────────
#  双轨鱼讯判定引擎
# ──────────────────────────────────────────────
class FishDetector:
    """双轨并行鱼讯判定器。

    维护 20 帧滚动窗口，每帧执行双轨判定：
        轨 A — 静态绝对值突刺（抓中层大鱼截杀）
        轨 B — 动态方差波动（抓贴底底层鱼拱窝）
    """

    def __init__(self, base_depth, th_mid, sd_floor):
        self.base_depth = base_depth
        self.th_mid = th_mid
        self.sd_floor = sd_floor

        self._window = []           # 滚动窗口（最近 WINDOW_SIZE 帧距离 mm）
        self._consecutive_mid = 0   # 轨 A 连续满足帧计数器

    def feed(self, current_depth):
        """喂入一帧新测距数据并执行双轨判定。

        Args:
            current_depth: 当前水深 mm

        Returns:
            int: alarm_level (0/1/2)
        """
        # 推入滚动窗口
        self._window.append(current_depth)
        if len(self._window) > WINDOW_SIZE:
            self._window.pop(0)

        alarm = ALARM_NONE

        # ── 轨 A: 静态绝对值突刺判定（中层大鱼） ──
        # 原理: 鱼截杀中心波束 → 距离突然变浅 → Δ = BaseDepth - CurrentDepth
        delta = self.base_depth - current_depth

        if delta >= self.th_mid:
            self._consecutive_mid += 1
            # 必须连续 3 帧以上（排除气泡等偶发单帧噪声）
            if self._consecutive_mid >= CONSECUTIVE_FRAMES:
                alarm = ALARM_MID_FISH
        else:
            self._consecutive_mid = 0

        # ── 轨 B: 动态统计方差波动判定（底层鱼） ──
        # 条件: 轨 A 未触发 + 窗口已满 + 绝对距离没有大幅度变浅
        if alarm == ALARM_NONE and len(self._window) >= WINDOW_SIZE:
            st_dev = calc_std_dev(self._window)
            if st_dev >= self.sd_floor and delta < self.th_mid:
                alarm = ALARM_BOTTOM_FISH

        return alarm

    @property
    def window_std_dev(self):
        """当前窗口标准差（调试用）。"""
        return calc_std_dev(self._window) if len(self._window) >= 2 else 0.0

    @property
    def window_size(self):
        """当前窗口帧数。"""
        return len(self._window)


# ══════════════════════════════════════════════
#  主程序入口
# ══════════════════════════════════════════════
print("=" * 54)
print("  ESP32-A 边缘物联数据节点")
print("  DYP-L08B50TW v3.0 | ESP-NOW | 自适应鱼讯判定")
print("  采样率: {}ms/帧 | 窗口: {} 帧 | 连续确认: {} 帧".format(
    SAMPLE_INTERVAL_MS, WINDOW_SIZE, CONSECUTIVE_FRAMES))
print("=" * 54)

# ── 1. 初始化 ESP-NOW ──
espnow_dev = init_espnow()

# ── 2. 基准水深校准（前 10 秒静默采样，不告警） ──
base_depth = calibrate_base_depth()
th_mid, sd_floor = calc_thresholds(base_depth)

# ── 3. 初始化鱼讯判定器 ──
detector = FishDetector(base_depth, th_mid, sd_floor)

# ── 4. 运行统计 ──
send_ok = 0
send_fail = 0
frame_count = 0
alarm_count = 0

print("\n[运行] ────── 正式运行 ──────")
print("[运行] BaseDepth={}mm Th_mid={:.1f}mm SD_floor={:.1f}mm".format(
    base_depth, th_mid, sd_floor))
print("[运行] 采样间隔={}ms 每{}帧心跳".format(
    SAMPLE_INTERVAL_MS, HEARTBEAT_INTERVAL))
print("=" * 54)

# ── 5. 主循环 ──
while True:
    loop_start = time.ticks_ms()

    dist = measure_distance_mm()

    if dist is None:
        # 传感器故障/超量程：发送无效帧保持心跳，不参与鱼讯判定
        pkt = encode_data_frame(
            time.ticks_ms(), base_depth, DIST_INVALID, ALARM_NONE)
        try:
            espnow_dev.send(BROADCAST_MAC, pkt, False)
            send_ok += 1
        except Exception:
            send_fail += 1
        frame_count += 1

        # 精确等待
        elapsed = time.ticks_diff(time.ticks_ms(), loop_start)
        wait = SAMPLE_INTERVAL_MS - elapsed
        if wait > 0:
            time.sleep_ms(wait)
        continue

    # ── 双轨判定 ──
    alarm_level = detector.feed(dist)

    # ── 编码 + ESP-NOW 广播 ──
    pkt = encode_data_frame(time.ticks_ms(), base_depth, dist, alarm_level)
    try:
        espnow_dev.send(BROADCAST_MAC, pkt, False)  # False=异步更省时
        send_ok += 1
    except Exception as e:
        send_fail += 1
        print("[ESP-NOW] 发送异常: {}".format(e))

    frame_count += 1

    # ── 鱼讯日志（仅在触发时打印，不刷屏） ──
    if alarm_level > 0:
        alarm_count += 1
        delta = base_depth - dist
        label = "底层拱窝" if alarm_level == ALARM_BOTTOM_FISH else "中层截杀"
        print("[🐟鱼讯!] #{} {} | dist={}mm Δ={}mm σ={:.1f}mm".format(
            frame_count, label, dist, delta, detector.window_std_dev))

    # ── 心跳诊断（每 30 帧约 3 秒） ──
    if frame_count % HEARTBEAT_INTERVAL == 0:
        print("[心跳] #{} dist={}mm base={}mm σ={:.1f}mm win={}/{} | ok={} fail={} alarm={}".format(
            frame_count, dist, base_depth,
            detector.window_std_dev, detector.window_size, WINDOW_SIZE,
            send_ok, send_fail, alarm_count))

    # ── 精确等待到下一采样周期 ──
    elapsed = time.ticks_diff(time.ticks_ms(), loop_start)
    sleep_ms = SAMPLE_INTERVAL_MS - elapsed
    if sleep_ms > 0:
        time.sleep_ms(sleep_ms)
