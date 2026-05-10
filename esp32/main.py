"""
ESP32 钓鱼传感器主程序 (Main Entry)
=====================================
初始化所有模块，运行主采集-通信循环。

主循环逻辑（每 5 秒一轮）：
  1. 读取三层水温
  2. 读取气压
  3. 生成时间戳
  4. 写入环形缓冲区
  5. 根据 BLE 连接状态决定发送策略：
     - 已连接且已对表 → 发送实时数据
     - 已连接但未对表 → 等待对表指令
     - 未连接 → 数据留在缓冲区
  6. 历史数据采用手动拉取模式：由小程序下发 CMD_PULL_HISTORY
     主动拉取，每次回发一批（最多 BLE_BATCH_SIZE 条）。
"""

import time
import gc

from config import SAMPLE_INTERVAL_SEC
from sensors.temperature import TemperatureSensor
from sensors.pressure import PressureSensor
from storage.ring_buffer import RingBuffer
from utils.time_sync import TimeSync
from ble.service import BLEService


def main():
    print("=" * 40)
    print("FishProbe ESP32 传感器系统")
    print("=" * 40)

    # ── 1. 初始化各模块 ──
    time_sync = TimeSync()
    ring_buffer = RingBuffer()
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
        print("[系统] 警告: 温度传感器初始化失败，将仅采集气压数据。")
    if not press_ok:
        print("[系统] 警告: 气压传感器初始化失败，将仅采集温度数据。")

    print("\n[系统] 初始化 BLE...")
    ble_service.init()

    print("\n[系统] 启动完成！开始采集循环 (间隔: {}秒)".format(SAMPLE_INTERVAL_SEC))
    print("[系统] 等待小程序连接并对表...\n")

    # ── 2. 主循环 ──
    sample_count = 0

    while True:
        loop_start = time.ticks_ms()

        # ── 2.1 采集传感器数据 ──
        temps = temp_sensor.read_all() if temp_ok else {
            "t_bottom": None, "t_mid": None, "t_surface": None, "t_diff": None
        }
        press = press_sensor.read() if press_ok else {"p_local": None, "t_env": None}

        # ── 2.2 生成时间戳 ──
        timestamp = time_sync.now()

        # ── 2.3 写入环形缓冲区 ──
        ring_buffer.write(
            timestamp,
            temps["t_bottom"],
            temps["t_mid"],
            temps["t_surface"],
            press["p_local"],
        )

        sample_count += 1

        # ── 2.4 控制台调试输出（每10次输出一次状态） ──
        if sample_count % 10 == 1:
            _print_status(
                sample_count, timestamp, temps, press,
                ble_service, ring_buffer, time_sync,
            )

        # ── 2.5 BLE 数据发送策略 ──
        # 注意：历史数据补传改为"手动拉取模式"，由小程序主动下发
        # CMD_PULL_HISTORY 指令触发，主循环只负责发送实时数据。
        if ble_service.is_connected and ble_service.is_time_synced:
            # 清除重连标志（不再自动补传，仅保留状态）
            if ble_service.just_reconnected:
                unsent = ring_buffer.unsent_count
                if unsent > 0:
                    print("[系统] 重连后待补 {} 条，等待小程序手动拉取".format(unsent))
                ble_service.clear_reconnect_flag()

            # 仅发送实时数据
            success = ble_service.send_realtime(
                timestamp,
                temps["t_bottom"],
                temps["t_mid"],
                temps["t_surface"],
                press["p_local"],
            )
            if success:
                # 实时发送成功，免 ACK 确权，直接标记这 1 条已处理
                ring_buffer.mark_sent(1)

        # ── 2.6 内存回收（每100次执行一次） ──
        if sample_count % 100 == 0:
            gc.collect()

        # ── 2.7 精确等待（扣除采集耗时） ──
        elapsed = time.ticks_diff(time.ticks_ms(), loop_start)
        sleep_ms = max(0, SAMPLE_INTERVAL_SEC * 1000 - elapsed)
        if sleep_ms > 0:
            time.sleep_ms(sleep_ms)


def _print_status(count, timestamp, temps, press, ble, buf, ts):
    """打印调试状态信息。"""
    cal = "已校准" if ts.is_calibrated else "未校准"
    conn = "已连接" if ble.is_connected else "未连接"
    synced = "已对表" if ble.is_time_synced else "未对表"

    tb = "{:.2f}".format(temps["t_bottom"]) if temps["t_bottom"] is not None else "--"
    tm = "{:.2f}".format(temps["t_mid"]) if temps["t_mid"] is not None else "--"
    ts_val = "{:.2f}".format(temps["t_surface"]) if temps["t_surface"] is not None else "--"
    pl = "{:.2f}".format(press["p_local"]) if press["p_local"] is not None else "--"
    td = "{:.2f}".format(temps["t_diff"]) if temps["t_diff"] is not None else "--"

    print("[#{:>5}] ts={} | 水底:{}℃ 1米:{}℃ 水面:{}℃ 温差:{}℃ | 气压:{}hPa | BLE:{}/{} 时钟:{} 缓存:{}/{}".format(
        count, timestamp,
        tb, tm, ts_val, td, pl,
        conn, synced, cal,
        buf.unsent_count, buf.count,
    ))


# MicroPython 入口
main()
