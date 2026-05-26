"""
ESP32 钓鱼传感器主程序 (Main Entry)
=====================================
初始化所有模块，运行主采集-通信循环。

硬件版本: v2（单水温 DS18B20 + BMP280 气温/气压 + 可选 ESP32-B 水下声呐）

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
  7. 水下声呐数据：在 keepalive_sleep 的 tick_callback 中以 ~50ms 节拍
     非阻塞轮询 ESP-NOW，收到一帧即立刻通过 BLE CMD_SONAR_DATA 转发。
     声呐数据不入 ring_buffer（量大且强实时，无需历史补传）。

充电宝保活：
  采用 keepalive_sleep 替代 time.sleep_ms，在长睡眠期间
  周期性产生 CPU 脉冲和 WiFi 射频脉冲，维持充电宝供电。
"""

import time
import gc

from config import SAMPLE_INTERVAL_SEC
from sensors.temperature import TemperatureSensor
from sensors.pressure import PressureSensor
from storage.ring_buffer import RingBuffer
from utils.time_sync import TimeSync
from utils.keepalive import keepalive_sleep
import utils.keepalive as _ka  # 用于关闭 WiFi 踢脚（避免与 ESP-NOW 冲突）
from ble.service import BLEService
from sonar.receiver import SonarReceiver
from utils.buzzer import BuzzerManager


def _enable_sta_for_espnow():
    """启用 STA WiFi 并关闭 AP，仅供 ESP-NOW 使用（不连接任何 AP）。

    ESP-NOW 协议依赖 WiFi 射频。STA 保持 active(True) 但不连接 AP，
    通信信道默认 1，与 ESP32-B 端 esp-hcrs04.py 默认信道一致。
    ⚠ 不同 MicroPython 固件不连 AP 时默认信道可能不一，这里显式锁定为 1。
    """
    try:
        import network
        sta = network.WLAN(network.STA_IF)
        ap = network.WLAN(network.AP_IF)
        if not sta.active():
            sta.active(True)
        if ap.active():
            ap.active(False)
        try:
            sta.config(channel=1)
        except Exception as e:
            print("[系统] 锁定 STA channel=1 失败（继续运行）: {}".format(e))
        print("[系统] WiFi STA 已开启（用于 ESP-NOW），AP 已关闭")
    except Exception as e:
        print("[系统] 启用 STA 失败（ESP-NOW 可能不可用）: {}".format(e))


def main():
    print("=" * 40)
    print("FishProbe ESP32 传感器系统 (v2 + 水下声呐)")
    print("=" * 40)

    # ── 0. 启用 STA WiFi（供 ESP-NOW 使用）──
    _enable_sta_for_espnow()

    # 关闭 keepalive 内的 WiFi 踢脚：它会反复 active(True/False)，
    # 而 ESP-NOW 需要 STA 常驻 active，二者冲突。
    _ka._WIFI_KICK_ENABLED = False

    # ── 1. 初始化各模块 ──
    time_sync = TimeSync()
    ring_buffer = RingBuffer(persistent=True)
    ble_service = BLEService(time_sync, ring_buffer)
    temp_sensor = TemperatureSensor()
    press_sensor = PressureSensor()
    sonar = SonarReceiver()
    buzzer = BuzzerManager()

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

    print("\n[系统] 初始化 ESP-NOW 声呐接收器...")
    sonar_ok = sonar.init()
    if not sonar_ok:
        print("[系统] 警告: ESP-NOW 不可用，将不上报水下声呐数据（不影响主链路）。")

    print("\n[系统] 初始化蜂鸣器报警系统...")
    buzzer.init()

    # ── 主循环 tick: 既处理 BLE 快闪 Dump，又轮询 ESP-NOW 声呐 ──
    def tick_callback():
        # BLE 快闪历史 Dump
        ble_service.process_fast_dump()
        # ESP-NOW 声呐：非阻塞收一帧并立刻 BLE 转发
        if sonar.initialized:
            pkt = sonar.poll(timeout_ms=0)
            if pkt is not None:
                # 提取边缘节点判断的告警等级，触发本地物理声音警报
                alarm_level = pkt.get("alarm_level", 0)
                buzzer.trigger(alarm_level)

                # 只有在蓝牙连接且对齐时钟后，才向手机小程序转发实时声呐帧
                if ble_service.is_connected and ble_service.is_time_synced:
                    ble_service.send_sonar(
                        time_sync.now(),
                        pkt["distance_cm"],
                        pkt["baseline_cm"],
                        pkt["status"],
                        pkt["fish_event"],
                        alarm_level,
                    )
        # 轮询非阻塞蜂鸣器状态机，平滑切换声音状态
        buzzer.tick()

    print("\n[系统] 启动完成！开始采集循环 (间隔: {}秒)".format(SAMPLE_INTERVAL_SEC))
    print("[系统] 充电宝保活模式已启用（脉冲间隔 2 秒，WiFi 踢脚已禁用以兼容 ESP-NOW）")
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
                ble_service, ring_buffer, time_sync, sonar,
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
        # 传入 tick_callback 用于后台处理 BLE 快闪 Dump + ESP-NOW 声呐转发
        elapsed = time.ticks_diff(time.ticks_ms(), loop_start)
        sleep_ms = max(0, SAMPLE_INTERVAL_SEC * 1000 - elapsed)
        if sleep_ms > 0:
            keepalive_sleep(sleep_ms, tick_callback=tick_callback)


def _print_status(count, timestamp, t_water, t_air, p_local, ble, buf, ts, sonar=None):
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
    # 声呐链路统计：rx=收到的合法帧数, drop=丢弃的非法帧数, last=距上次收包多少秒
    if sonar is not None and sonar.initialized:
        st = sonar.get_status()
        last_recv_ms = st.get("last_recv_ms", 0)
        if last_recv_ms:
            ago_ms = time.ticks_diff(time.ticks_ms(), last_recv_ms)
            ago = "{}s前".format(ago_ms // 1000)
        else:
            ago = "从未"
        print("        └─ 声呐: rx={} drop={} 最近收包={} dist_cm={} baseline_cm={}".format(
            st.get("packets", 0), st.get("dropped", 0), ago,
            st.get("last_distance_cm"), st.get("last_baseline_cm"),
        ))


# MicroPython 入口
main()
