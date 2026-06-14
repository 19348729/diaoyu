"""
充电宝保活模块 (Power Bank Keep-Alive)
=======================================
普通充电宝有「小电流保护」机制：当负载电流长时间低于阈值
（通常 50~100mA）时，充电宝会自动断电。

ESP32 在低功耗模式下（BLE 广播 + 深度休眠），平均电流仅
~20~30mA，触发充电宝断电保护。

本模块通过以下策略维持足够电流：
  【方案B - 主手段】WiFi 射频常开：启动时开启 STA 射频并关闭省电模式，
      射频持续工作让整机电流稳定在 ~80~120mA。充电宝的小电流保护判的是
      一段时间窗口内的「平均电流」，唯有持续高电流才能稳定压住阈值，
      靠偶发尖峰（如周期性扫描）摊到平均后几乎为 0，并不可靠。
  【辅助】CPU 忙循环脉冲：长睡眠切片，片段间隙满载跑一小段，叠加余量。
  【兜底】若射频常开初始化失败，自动退回「周期性 WiFi 扫描踢脚」。
"""

import time
import machine


# ── 保活参数 ──
_PULSE_INTERVAL_MS = 2000      # CPU 脉冲间隔（毫秒），同时作为切片睡眠粒度
_PULSE_DURATION_MS = 60        # 每次 CPU 脉冲持续时间（毫秒）

# WiFi 保活（方案B：射频常开为主，扫描踢脚为兜底）
_WIFI_KICK_INTERVAL = 15       # 兜底模式：每隔多少次 CPU 脉冲踢一次脚
_wifi_persistent_ok = False    # enable_persistent_wifi() 成功后置 True（射频已常开）

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


def enable_persistent_wifi():
    """方案B：开启 STA WiFi 射频并常驻（不连接任何 AP），关闭省电模式。

    WiFi 射频持续工作时整机电流稳定在 ~80~120mA，足以让充电宝检测到的
    「平均电流」高于小电流保护阈值，从而不断电。不连接 AP、不收发业务数据，
    与 BLE 主链路共存（ESP32 BLE/WiFi 射频时分复用，互不影响功能）。

    关键：必须关闭 WiFi 省电模式（PM_NONE），否则射频会自动 modem-sleep
    把电流降回 20~30mA，保活失效。

    成功返回 True 并置位 _wifi_persistent_ok；失败返回 False，
    主循环会自动退回周期性 WiFi 扫描踢脚兜底。
    """
    global _wifi_persistent_ok
    try:
        import network
        sta = network.WLAN(network.STA_IF)
        ap = network.WLAN(network.AP_IF)
        if not sta.active():
            sta.active(True)
        # 关闭 AP，避免多余开销
        try:
            if ap.active():
                ap.active(False)
        except Exception:
            pass
        # 关闭省电模式 → 射频保持全功率（保活成败的关键）
        try:
            sta.config(pm=sta.PM_NONE)
        except Exception:
            # 个别固件无 PM_NONE 常量，退而尝试数值 0（禁用省电）
            try:
                sta.config(pm=0)
            except Exception:
                pass
        _wifi_persistent_ok = True
        print("[保活] WiFi 射频常开已启用（方案B），已关闭省电模式")
        return True
    except Exception as e:
        _wifi_persistent_ok = False
        print("[保活] WiFi 射频常开启用失败，退回周期性踢脚: {}".format(e))
        return False


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

            # WiFi 踢脚仅作兜底：射频常开未生效时才周期性扫描拉电流
            if (not _wifi_persistent_ok) and (pulse_count % _WIFI_KICK_INTERVAL == 0):
                _wifi_kick()
