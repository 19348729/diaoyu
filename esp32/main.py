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

充电宝保活（方案B：WiFi 射频常开）：
  启动时调用 enable_persistent_wifi() 开启 STA 射频并关闭省电模式，
  整机电流稳定在 ~80~120mA，让充电宝检测到的平均电流高于小电流保护
  阈值，从而不断电。睡眠仍用 keepalive_sleep（CPU 脉冲叠加余量；
  若射频常开失败则自动退回周期性 WiFi 扫描踢脚兜底）。
"""

import time
import gc

from config import SAMPLE_INTERVAL_SEC
from sensors.temperature import TemperatureSensor
from sensors.pressure import PressureSensor
from storage.ring_buffer import RingBuffer
from utils.time_sync import TimeSync
from utils.keepalive import keepalive_sleep, enable_persistent_wifi
from ble.service import BLEService


def main():
    print("=" * 40)
    print("FishProbe ESP32 传感器系统 (v2)")
    print("=" * 40)

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

    # ── 充电宝保活（方案B）：开启 WiFi 射频常开，拉高平均电流防断电 ──
    print("\n[系统] 启用充电宝保活（WiFi 射频常开）...")
    enable_persistent_wifi()

    # ── 主循环 tick: 处理 BLE 快闪 Dump ──
    def tick_callback():
        ble_service.process_fast_dump()

    print("\n[系统] 启动完成！开始采集循环 (间隔: {}秒)".format(SAMPLE_INTERVAL_SEC))
    print("[系统] 充电宝保活：WiFi 射频常开 + CPU 脉冲（间隔 2 秒）")
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
        # 在睡眠期间周期性产生电流脉冲，防止充电宝小电流保护断电
        # 传入 tick_callback 用于后台处理 BLE 快闪 Dump
        elapsed = time.ticks_diff(time.ticks_ms(), loop_start)
        sleep_ms = max(0, SAMPLE_INTERVAL_SEC * 1000 - elapsed)
        if sleep_ms > 0:
            keepalive_sleep(sleep_ms, tick_callback=tick_callback)


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
