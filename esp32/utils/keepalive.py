"""
充电宝保活模块 (Power Bank Keep-Alive)
=======================================
普通充电宝有「小电流保护」机制：当负载电流长时间低于阈值
（通常 50~100mA）时，充电宝会自动断电。

ESP32 在低功耗模式下（BLE 广播 + 深度休眠），平均电流仅
~20~30mA，触发充电宝断电保护。

本模块通过以下策略维持足够电流：
  1. 将长睡眠（如60秒）切割为短片段（如2秒）
  2. 每个片段间隔执行一次 CPU 忙循环（"脉冲"），持续约 50ms
  3. 脉冲期间 CPU 全速运行，拉高瞬时电流至 ~80~120mA
  4. 周期性开关 WiFi 扫描产生额外电流消耗（可选）

这样充电宝检测到的平均电流足以维持供电。
"""

import time
import machine


# ── 保活参数 ──
_PULSE_INTERVAL_MS = 2000      # 每隔多久执行一次脉冲（毫秒）
_PULSE_DURATION_MS = 60        # 每次脉冲持续时间（毫秒）
_WIFI_KICK_INTERVAL = 15       # 每隔多少次脉冲执行一次 WiFi 扫描踢脚（次数）
_WIFI_KICK_ENABLED = True      # 是否启用 WiFi 扫描踢脚（更强力的保活手段）

# 用于保活脉冲的 GPIO（选一个未使用的 GPIO 配置为输出）
# GPIO12 通常是可用的通用 IO，设为输出并反复翻转产生额外电流
_KEEPALIVE_PIN = None  # 延迟初始化


def _get_keepalive_pin():
    """获取保活用 GPIO 引脚（延迟初始化）。"""
    global _KEEPALIVE_PIN
    if _KEEPALIVE_PIN is None:
        try:
            # 使用 GPIO12 作为保活引脚（确保未被传感器占用）
            # config.py 中使用了 GPIO13(DS18B20), GPIO2(SDA), GPIO15(SCL)
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
    """短暂开启 WiFi 扫描然后关闭，产生一次较大的电流脉冲。

    WiFi 射频开启瞬间电流可达 ~180~250mA，是最有效的保活手段。
    扫描完成后立即关闭，不影响正常 BLE 运行。
    """
    try:
        import network
        sta = network.WLAN(network.STA_IF)
        sta.active(True)
        # 短暂延时让射频启动消耗电流
        time.sleep_ms(100)
        # 尝试执行一次扫描（会自动超时）
        try:
            sta.scan()
        except Exception:
            pass
        # 关闭 WiFi
        sta.active(False)
    except Exception as e:
        print("[保活] WiFi 踢脚失败: {}".format(e))


def keepalive_sleep(total_ms):
    """替代 time.sleep_ms() 的保活版本。

    将长睡眠拆分为短片段，每个片段之间插入电流脉冲，
    确保充电宝检测到足够的平均电流不会断电。

    Args:
        total_ms: 总休眠时间（毫秒），与 time.sleep_ms() 语义相同
    """
    if total_ms <= 0:
        return

    remaining = total_ms
    pulse_count = 0

    while remaining > 0:
        # 睡眠一个片段
        sleep_chunk = min(remaining, _PULSE_INTERVAL_MS)
        time.sleep_ms(sleep_chunk)
        remaining -= sleep_chunk

        # 如果还有剩余时间，执行保活脉冲
        if remaining > 0:
            _cpu_busy_pulse(_PULSE_DURATION_MS)
            pulse_count += 1

            # 周期性 WiFi 踢脚（更强力的保活）
            if _WIFI_KICK_ENABLED and (pulse_count % _WIFI_KICK_INTERVAL == 0):
                _wifi_kick()
