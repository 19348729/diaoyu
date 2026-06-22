"""
充电宝保活模块（高功耗模式 Power Bank Keep-Alive）
=====================================================
普通充电宝有「小电流保护」机制：负载电流长期低于阈值
（通常 50~100mA）时会自动断电。BLE 广播只能提供 ~25~30mA，必然被断。

本模块为经实测验证可用的旧固件保活逻辑，与 main.py / config.py 配合实现多重保活：
  1. main.py 启动时拉升 CPU 主频到 240MHz（+~20mA 基线）
  2. main.py 启动时 WiFi STA 常驻 active（+~50~70mA 基线，最有效的软件手段）
  3. 本模块在长睡眠中用纯 CPU 忙循环（全程不调 time.sleep_ms，避免进入
     light-sleep），让 CPU 持续跑满 240MHz，电流 ~80~100mA，稳住充电宝
  4. 周期性 WiFi 扫描踢脚，产生瞬态 ~200mA 电流尖峰

与现固件快闪 Dump 兼容：忙循环中按节流周期回调 tick_callback，
驱动 BLE 后台任务（process_fast_dump），不影响离线数据同步。

所有可调参数集中在 config.py 的 KEEPALIVE_* 字段。
"""

import time
import machine

from config import (
    KEEPALIVE_PULSE_INTERVAL_MS,
    KEEPALIVE_PULSE_DURATION_MS,
    KEEPALIVE_WIFI_KICK_INTERVAL,
    KEEPALIVE_WIFI_KICK_ENABLED,
    KEEPALIVE_WIFI_ALWAYS_ON,
    KEEPALIVE_BUSY_LOOP_MODE,
    KEEPALIVE_WIFI_KICK_INTERVAL_MS,
)


# 忙循环中回调 tick_callback 的最小间隔（毫秒）：
# 既能及时驱动快闪 Dump，又不至于淹没 BLE notify 队列。
_TICK_INTERVAL_MS = 20

# 用于保活脉冲的 GPIO（选一个未使用的 GPIO 配置为输出）
# GPIO12 通常是可用的通用 IO，设为输出并反复翻转产生额外电流
_KEEPALIVE_PIN = None  # 延迟初始化


def _get_keepalive_pin():
    """获取保活用 GPIO 引脚（延迟初始化）。"""
    global _KEEPALIVE_PIN
    if _KEEPALIVE_PIN is None:
        try:
            # 使用 GPIO12 作为保活引脚（确保未被传感器占用）
            # config.py 中使用了 GPIO32(DS18B20), GPIO2(SDA), GPIO15(SCL)
            _KEEPALIVE_PIN = machine.Pin(12, machine.Pin.OUT)
            _KEEPALIVE_PIN.value(0)
        except Exception as e:
            print("[保活] GPIO12 初始化失败: {}".format(e))
            _KEEPALIVE_PIN = False  # 标记为不可用
    return _KEEPALIVE_PIN if _KEEPALIVE_PIN is not False else None


def _cpu_busy_pulse(duration_ms):
    """执行一次 CPU 忙循环脉冲，拉高瞬时电流。

    通过快速翻转 GPIO + 纯计算密集循环让 CPU 满载运行，
    消耗约 80~120mA 持续 duration_ms 毫秒。
    """
    pin = _get_keepalive_pin()
    start = time.ticks_ms()
    counter = 0

    while time.ticks_diff(time.ticks_ms(), start) < duration_ms:
        # 纯 CPU 计算（产生真实负载）
        counter += 1
        x = counter * 7 + 13
        x = x ^ (x >> 3)
        x = (x * 31) & 0xFFFF

        # GPIO 翻转（产生额外 IO 电流）
        if pin and (counter & 0x3F) == 0:  # 每64次翻转一次
            pin.value(counter & 0x40)


def _wifi_kick():
    """在 WiFi STA 已常驻的前提下，执行一次扫描产生额外电流尖峰。

    扫描期间 WiFi 射频会从空闲态 ~50~70mA 瞬间提升到 ~180~250mA，
    产生明显电流尖峰。若 WiFi 未常驻（低功耗模式）则需先 active，
    扫描后再关闭。
    """
    try:
        import network
        sta = network.WLAN(network.STA_IF)
        opened_temporarily = False
        if not sta.active():
            sta.active(True)
            opened_temporarily = True
            time.sleep_ms(100)
        try:
            sta.scan()
        except Exception:
            pass
        # 仅在原本未开启的情况下才关闭，避免破坏常驻状态
        if opened_temporarily:
            sta.active(False)
    except Exception as e:
        print("[保活] WiFi 踢脚失败: {}".format(e))


def keepalive_sleep(total_ms, tick_callback=None, is_connected=None):
    """替代 time.sleep_ms() 的保活版本。

    根据 KEEPALIVE_BUSY_LOOP_MODE 选择两种策略：
      - True  ：纯 CPU 忙循环 + 周期性 WiFi 踢脚，全程不调 time.sleep_ms，
               避免进入 light-sleep，CPU 持续跑在 240MHz，电流 ~80~100mA，
               能稳住充电宝（推荐，已实测可用）。
      - False ：原高占空比脉冲模式（节电，但可能仍被断电）。

    Args:
        total_ms: 总休眠时间（毫秒），与 time.sleep_ms() 语义相同
        tick_callback: 睡眠期间周期性调用的回调（用于驱动 BLE 快闪 Dump 等后台任务）
        is_connected: 可调用对象，返回当前 BLE 是否已连接。已连接时跳过 WiFi 扫描
                      踢脚——WiFi/BLE 共用天线，连接期间的阻塞扫描会挤占 BLE 时隙
                      导致连接监督超时断连（CPU 忙循环保活照常，不影响 BLE 中断）。
    """
    if total_ms <= 0:
        return

    if KEEPALIVE_BUSY_LOOP_MODE:
        _busy_loop_keepalive(total_ms, tick_callback, is_connected)
    else:
        _pulse_keepalive(total_ms, tick_callback, is_connected)


def _kick_allowed(is_connected):
    """是否允许执行 WiFi 扫描踢脚：未启用/未常驻或 BLE 已连接时一律禁止。"""
    if not (KEEPALIVE_WIFI_KICK_ENABLED and KEEPALIVE_WIFI_ALWAYS_ON):
        return False
    # 已连接时禁止扫描，避免抢占 BLE 天线时隙导致断连
    if is_connected:
        try:
            if is_connected():
                return False
        except Exception:
            pass
    return True


def _busy_loop_keepalive(total_ms, tick_callback=None, is_connected=None):
    """纯 CPU 忙循环保活。

    不调 time.sleep_ms，仅用 ticks_diff 轮询计时，让 ESP32 始终维持
    CPU 高负载状态。BLE 交互基于中断，不受影响；快闪 Dump 这类需主循环
    驱动的后台任务，通过按节流回调 tick_callback 推进。
    """
    pin = _get_keepalive_pin()
    start = time.ticks_ms()
    last_kick = start
    last_tick = start
    counter = 0

    while time.ticks_diff(time.ticks_ms(), start) < total_ms:
        # 纯 CPU 计算（让 240MHz 主频跑满）
        for _ in range(2000):
            counter += 1
            x = counter * 7 + 13
            x = x ^ (x >> 3)
            x = (x * 31) & 0xFFFF

        # GPIO 翻转（额外小电流）
        if pin:
            pin.value(counter & 1)

        now = time.ticks_ms()

        # 驱动 BLE 后台任务（快闪 Dump），按节流避免淹没 notify 队列
        if tick_callback and time.ticks_diff(now, last_tick) >= _TICK_INTERVAL_MS:
            tick_callback()
            last_tick = now

        # 周期性 WiFi 踢脚（仅在 WiFi 常驻且未连接时生效）
        if (
            _kick_allowed(is_connected)
            and time.ticks_diff(now, last_kick) >= KEEPALIVE_WIFI_KICK_INTERVAL_MS
        ):
            _wifi_kick()
            last_kick = time.ticks_ms()


def _pulse_keepalive(total_ms, tick_callback=None, is_connected=None):
    """原脉冲保活（节电模式，保留作为备选）。"""
    remaining = total_ms
    pulse_count = 0

    while remaining > 0:
        sleep_chunk = min(remaining, KEEPALIVE_PULSE_INTERVAL_MS)
        if tick_callback:
            # 细分睡眠以快速响应回调（如 BLE 快闪）
            chunk_remaining = sleep_chunk
            while chunk_remaining > 0:
                step = min(chunk_remaining, _TICK_INTERVAL_MS)
                time.sleep_ms(step)
                tick_callback()
                chunk_remaining -= step
        else:
            time.sleep_ms(sleep_chunk)
        remaining -= sleep_chunk

        if remaining > 0:
            _cpu_busy_pulse(KEEPALIVE_PULSE_DURATION_MS)
            pulse_count += 1

            if _kick_allowed(is_connected) and (pulse_count % KEEPALIVE_WIFI_KICK_INTERVAL == 0):
                _wifi_kick()
