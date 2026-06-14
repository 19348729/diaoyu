"""
充电宝保活模块 (Power Bank Keep-Alive)
=======================================
普通充电宝有「小电流保护」机制：当负载电流长时间低于阈值
（通常 50~100mA）时，充电宝会自动断电。

ESP32 在低功耗模式下（BLE 广播 + 深度休眠），平均电流仅
~20~30mA，触发充电宝断电保护。

本模块采用「激进保活」策略，让平均电流稳定压住充电宝阈值：
  1. 将长睡眠（如60秒）切割为短片段（默认2秒）
  2. 每个片段结束执行一次 CPU 忙循环（"脉冲"），拉高瞬时电流作底
  3. ★核心★ 每个片段都触发一次 WiFi 全信道扫描（_WIFI_KICK_INTERVAL=1）：
     扫描本身阻塞约 1.5~2.5s、射频满功率 ~150~250mA，且扫完不关射频
     （_WIFI_KEEP_RADIO_ON），使 WiFi 近乎常开 → 平均电流冲到 ~120~180mA。

说明：空闲（仅 BLE 广播）时整机电流仅 ~20~30mA，远低于充电宝小电流保护
阈值（50~100mA）。靠每 30s 一次的稀疏脉冲摊到平均后几乎为 0，压不住；
唯有让射频近乎常开、持续高电流，才能稳定维持充电宝供电（代价是更费电、
芯片发热）。若此软件方案在你的充电宝上仍不稳，最终方案是硬件加假负载电阻。
"""

import time
import machine


# ── 保活参数（激进模式：WiFi 近乎常开）──
_PULSE_INTERVAL_MS = 2000      # CPU 脉冲间隔（毫秒），同时作为切片睡眠粒度
_PULSE_DURATION_MS = 150       # 每次 CPU 脉冲持续时间（毫秒），加大以抬高底电流
_WIFI_KICK_INTERVAL = 1        # 激进：每次脉冲(~2s)都扫描一次，射频近乎常开
_WIFI_KICK_ENABLED = True      # 启用 WiFi 扫描踢脚（最有效的保活手段）
_WIFI_KEEP_RADIO_ON = True     # 激进：扫描后不关闭 STA 射频，保持常驻拉高平均电流

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
    """触发一次 WiFi 全信道扫描产生大电流脉冲（激进保活核心）。

    sta.scan() 为阻塞调用，全信道扫描期间（~1.5~2.5s）射频满功率运行，
    电流可达 ~150~250mA。激进模式下每 ~2s 调用一次且扫完不关射频
    （_WIFI_KEEP_RADIO_ON=True），使 WiFi 近乎常开，平均电流持续高位。
    与 BLE 广播/连接共存（射频时分复用，不影响功能）。
    """
    try:
        import network
        sta = network.WLAN(network.STA_IF)
        if not sta.active():
            sta.active(True)
            time.sleep_ms(50)  # 让射频启动
        # 阻塞式全信道扫描：射频满功率，是平均电流的主要来源
        try:
            sta.scan()
        except Exception:
            pass
        # 激进模式：保持射频常驻；非激进时扫完关闭以省电
        if not _WIFI_KEEP_RADIO_ON:
            sta.active(False)
    except Exception as e:
        print("[保活] WiFi 踢脚失败: {}".format(e))


def keepalive_sleep(total_ms, tick_callback=None):
    """替代 time.sleep_ms() 的保活版本。

    将长睡眠拆分为短片段，每个片段之间插入电流脉冲，
    确保充电宝检测到足够的平均电流不会断电。

    Args:
        total_ms: 总休眠时间（毫秒），与 time.sleep_ms() 语义相同
        tick_callback: 短片段间隙调用的回调函数（常用于驱动后台任务）
    """
    if total_ms <= 0:
        return

    remaining = total_ms
    pulse_count = 0

    while remaining > 0:
        # 睡眠一个片段
        sleep_chunk = min(remaining, _PULSE_INTERVAL_MS)
        
        if tick_callback:
            # 细分睡眠以快速响应回调（如 BLE 快闪）
            chunk_remaining = sleep_chunk
            while chunk_remaining > 0:
                step = min(chunk_remaining, 50)
                time.sleep_ms(step)
                tick_callback()
                chunk_remaining -= step
        else:
            time.sleep_ms(sleep_chunk)
            
        remaining -= sleep_chunk

        # 如果还有剩余时间，执行保活脉冲
        if remaining > 0:
            _cpu_busy_pulse(_PULSE_DURATION_MS)
            pulse_count += 1

            # 周期性 WiFi 踢脚（更强力的保活）
            if _WIFI_KICK_ENABLED and (pulse_count % _WIFI_KICK_INTERVAL == 0):
                _wifi_kick()
