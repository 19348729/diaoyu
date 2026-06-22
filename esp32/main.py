"""
ESP32 钓鱼传感器主程序 (Main Entry)
=====================================
初始化所有模块，运行主采集-通信循环。

硬件版本: v2（单水温 DS18B20 + BMP280 气温/气压）

主循环逻辑（每 60 秒一轮）：
  1. 读取水温（DS18B20）
  2. 读取气温和气压（BMP280）
  3. 生成时间戳
  4. 写入环形缓冲区
  5. 根据 BLE 连接状态决定发送策略：
     - 已连接且已对表 → 发送实时数据
     - 已连接但未对表 → 等待对表指令
     - 未连接 → 数据留在缓冲区
  6. 历史数据采用手动拉取模式：由小程序下发 CMD_PULL_HISTORY
     主动拉取，每次回发一批（最多 BLE_BATCH_SIZE 条）。

充电宝保活（高功耗模式，已实测可用）：
  1. 启动时拉升 CPU 主频到 240MHz（基线电流 +~20mA）
  2. 启动时 WiFi STA 常驻 active（不连接 AP，仅射频，+~50~70mA，最有效）
  3. keepalive_sleep 用纯 CPU 忙循环替代 time.sleep_ms，全程不进 light-sleep，
     CPU 持续高负载 ~80~100mA，并周期性 WiFi 扫描踢脚产生 ~200mA 尖峰，
     稳定压住充电宝小电流保护阈值。参数集中在 config.py 的 KEEPALIVE_* 字段。
"""

import time
import gc
import machine

from config import (
    SAMPLE_INTERVAL_SEC,
    KEEPALIVE_CPU_FREQ_HZ,
    KEEPALIVE_WIFI_ALWAYS_ON,
    KEEPALIVE_BUSY_LOOP_MODE,
)
from sensors.temperature import TemperatureSensor
from sensors.pressure import PressureSensor
from storage.ring_buffer import RingBuffer
from utils.time_sync import TimeSync
from utils.keepalive import keepalive_sleep
from ble.service import BLEService


def _boost_cpu_freq():
    """将 CPU 主频拉到高档（默认 240MHz）。

    ESP32 默认主频 160MHz，拉高到 240MHz 后基线电流约提升 20mA，
    同时让 CPU 忙循环产生的脉冲负载更高。
    """
    try:
        machine.freq(KEEPALIVE_CPU_FREQ_HZ)
        print("[系统] CPU 主频已设为 {} MHz".format(KEEPALIVE_CPU_FREQ_HZ // 1_000_000))
    except Exception as e:
        print("[系统] 设置 CPU 主频失败（可忽略）: {}".format(e))


def _setup_wifi_keepalive():
    """WiFi 保活设置：STA 常驻 active（不连接 AP）。

    充电宝保活的核心诉求是平均电流。WiFi STA 一旦 active，
    即使不连接 AP，射频也会持续消耗 ~50~70mA，是最有效的
    软件保活手段。AP 模式则保持关闭以避免多余辐射。
    """
    try:
        import network
        sta = network.WLAN(network.STA_IF)
        ap = network.WLAN(network.AP_IF)
        # AP 必关
        if ap.active():
            ap.active(False)
            print("[系统] WiFi AP 已关闭")
        # STA 根据配置决定是否常驻 active
        if KEEPALIVE_WIFI_ALWAYS_ON:
            if not sta.active():
                sta.active(True)
            print("[系统] WiFi STA 已常驻开启（仅射频，不连接 AP）")
        else:
            if sta.active():
                sta.active(False)
            print("[系统] WiFi STA 已关闭（低功耗模式）")
    except Exception as e:
        print("[系统] WiFi 保活初始化失败（可忽略）: {}".format(e))


def main():
    print("=" * 40)
    print("FishProbe ESP32 传感器系统 (v2)")
    print("=" * 40)

    # ── 0. 高功耗保活初始化：CPU 拉频 + WiFi 常驻 ──
    _boost_cpu_freq()
    _setup_wifi_keepalive()

    # ── 1. 初始化各模块 ──
    time_sync = TimeSync()
    ring_buffer = RingBuffer(persistent=True)
    ble_service = BLEService(time_sync, ring_buffer)
    temp_sensor = TemperatureSensor()
    press_sensor = PressureSensor()

    print("\n[系统] 初始化传感器...")
    temp_ok = temp_sensor.init()
    press_ok = press_sensor.init()

    if not temp_ok and not press_ok:
        print("[系统] 错误: 所有传感器均初始化失败！")
        print("[系统] 请检查接线后重启。")
        return

    if not temp_ok:
        print("[系统] 警告: 水温传感器初始化失败，将仅采集气温/气压数据。")
    if not press_ok:
        print("[系统] 警告: 气压传感器初始化失败，将仅采集水温数据。")

    print("\n[系统] 初始化 BLE...")
    ble_service.init()

    # ── 主循环 tick: 处理 BLE 快闪 Dump ──
    def tick_callback():
        ble_service.process_fast_dump()

    print("\n[系统] 启动完成！开始采集循环 (间隔: {}秒)".format(SAMPLE_INTERVAL_SEC))
    mode_desc = "纯 CPU 忙循环模式（高耗电，防断电）" if KEEPALIVE_BUSY_LOOP_MODE else "高占空比脉冲模式（节电）"
    print("[系统] 充电宝保活：CPU {}MHz + WiFi {} + {}".format(
        KEEPALIVE_CPU_FREQ_HZ // 1_000_000,
        "常驻" if KEEPALIVE_WIFI_ALWAYS_ON else "关闭",
        mode_desc,
    ))
    print("[系统] 等待小程序连接并对表...\n")

    # ── 2. 主循环 ──
    sample_count = 0

    while True:
        loop_start = time.ticks_ms()

        # ── 2.1 采集传感器数据 ──
        temps = temp_sensor.read() if temp_ok else {"t_water": None}
        press = press_sensor.read() if press_ok else {"p_local": None, "t_air": None}

        t_water = temps["t_water"]
        t_air = press["t_air"]
        p_local = press["p_local"]

        # ── 2.2 生成时间戳 ──
        timestamp = time_sync.now()

        # ── 2.3 写入环形缓冲区 ──
        ring_buffer.write(timestamp, t_water, t_air, p_local)

        sample_count += 1

        # ── 2.4 控制台调试输出（每10次输出一次状态） ──
        if sample_count % 10 == 1:
            _print_status(
                sample_count, timestamp, t_water, t_air, p_local,
                ble_service, ring_buffer, time_sync,
            )

        # ── 2.5 BLE 数据发送策略 ──
        if ble_service.is_connected and ble_service.is_time_synced:
            # 清除重连标志
            if ble_service.just_reconnected:
                unsent = ring_buffer.unsent_count
                if unsent > 0:
                    print("[系统] 重连后待补 {} 条，等待小程序发起快闪拉取".format(unsent))
                ble_service.clear_reconnect_flag()

            if ble_service.is_realtime_mode():
                # 仅在开启实时模式后才主动 Notify
                success = ble_service.send_realtime(
                    timestamp, t_water, t_air, p_local,
                )
                if success:
                    ring_buffer.mark_sent(1)

        # ── 2.6 内存回收（每100次执行一次） ──
        if sample_count % 100 == 0:
            gc.collect()

        # ── 2.7 精确等待（扣除采集耗时）──
        # 使用 keepalive_sleep 替代 time.sleep_ms，
        # 在睡眠期间周期性产生电流脉冲，防止充电宝小电流保护断电。
        # tick_callback 驱动后台 BLE 快闪 Dump；is_connected 让保活在已连接时
        # 跳过 WiFi 扫描（避免抢占天线导致蓝牙断连）。
        elapsed = time.ticks_diff(time.ticks_ms(), loop_start)
        sleep_ms = max(0, SAMPLE_INTERVAL_SEC * 1000 - elapsed)
        if sleep_ms > 0:
            keepalive_sleep(
                sleep_ms,
                tick_callback=tick_callback,
                is_connected=lambda: ble_service.is_connected,
            )


def _print_status(count, timestamp, t_water, t_air, p_local, ble, buf, ts):
    """打印调试状态信息。"""
    cal = "已校准" if ts.is_calibrated else "未校准"
    conn = "已连接" if ble.is_connected else "未连接"
    synced = "已对表" if ble.is_time_synced else "未对表"

    tw = "{:.2f}".format(t_water) if t_water is not None else "--"
    ta = "{:.2f}".format(t_air) if t_air is not None else "--"
    pl = "{:.2f}".format(p_local) if p_local is not None else "--"

    print("[#{:>5}] ts={} | 水温:{}℃ 气温:{}℃ | 气压:{}hPa | BLE:{}/{} 时钟:{} 缓存:{}/{}".format(
        count, timestamp,
        tw, ta, pl,
        conn, synced, cal,
        buf.unsent_count, buf.count,
    ))


# MicroPython 入口
main()
