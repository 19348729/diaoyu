"""
声呐 ESP-NOW 接收器（ESP32-B 岸上主板端）
==========================================
- 通过 espnow 模块以非阻塞方式收取 ESP32-A 边缘节点广播的 10 字节声呐包
- ESP32-A 已在边缘端完成基准锁定、动态阈值、双轨鱼讯判定
- 岸上只需解码、状态映射，并通过 BLE 转发给小程序

注意:
  - 使用前需保证 STA WiFi 已 active(True)（ESP-NOW 依赖 WiFi 射频）
  - 仅接收帧长 = 10 且 XOR 校验通过的合法包
"""

import time

from sonar.protocol import (
    decode_sonar_packet, SONAR_PKT_LEN,
    ALARM_NONE, ALARM_BOTTOM_FISH, ALARM_MID_FISH,
    DIST_INVALID, STATUS_OK, STATUS_COMM_FAIL,
)


class SonarReceiver:
    """ESP-NOW 声呐数据接收器（岸上 ESP32-B 端）。

    接收 ESP32-A 的 10 字节帧，解码后提供与 BLE 层兼容的数据接口。
    """

    def __init__(self):
        self._espnow = None
        self._initialized = False

        # 最新一帧数据
        self._last_distance_cm = None
        self._last_baseline_cm = None
        self._last_alarm_level = ALARM_NONE
        self._last_recv_ms = 0
        self._packet_count = 0
        self._dropped_count = 0

    def init(self) -> bool:
        """初始化 ESP-NOW（要求 STA WiFi 已 active）。"""
        try:
            import espnow  # MicroPython 内置
            self._espnow = espnow.ESPNow()
            self._espnow.active(True)
            # 部分 MicroPython 固件接收广播帧也需要显式 add_peer(broadcast)
            try:
                self._espnow.add_peer(b'\xff\xff\xff\xff\xff\xff')
                print("[Sonar] 已添加广播 peer (FF:FF:FF:FF:FF:FF)")
            except OSError as e:
                # ESP_ERR_ESPNOW_EXIST 等错误可忽略
                print("[Sonar] add_peer(broadcast) 跳过: {}".format(e))
            # 打印本机 STA MAC 与 WiFi 信道，便于和 ESP32-A 比对
            try:
                import network, binascii
                sta = network.WLAN(network.STA_IF)
                mac = binascii.hexlify(sta.config('mac'), ':').decode()
                ch = sta.config('channel')
                print("[Sonar] STA MAC={} channel={}".format(mac, ch))
            except Exception as e:
                print("[Sonar] 读取 MAC/channel 失败: {}".format(e))
            self._initialized = True
            print("[Sonar] ESP-NOW 接收器已启动（10 字节帧协议，XOR 校验）")
            return True
        except Exception as e:
            print("[Sonar] ESP-NOW 初始化失败: {}".format(e))
            self._initialized = False
            return False

    def deinit(self):
        if self._espnow is not None:
            try:
                self._espnow.active(False)
            except Exception:
                pass
        self._initialized = False

    @property
    def initialized(self) -> bool:
        return self._initialized

    @property
    def packet_count(self) -> int:
        return self._packet_count

    def poll(self, timeout_ms: int = 0):
        """非阻塞收一帧（timeout_ms=0 立即返回）。

        Returns:
            dict 形如:
              {
                "distance_cm": float|None,   # 当前水深 cm
                "baseline_cm": float|None,   # 基准水深 cm (由 ESP32-A 锁定)
                "status": int,               # STATUS_OK 或 STATUS_COMM_FAIL
                "fish_event": bool,           # alarm_level > 0
                "alarm_level": int,           # 0=无鱼 1=底层拱窝 2=中层截杀
              }
            没有新包时返回 None。
        """
        if not self._initialized or self._espnow is None:
            return None

        try:
            host, msg = self._espnow.recv(timeout_ms)
        except Exception:
            # 偶发异常静默吞，等下一轮
            return None

        if not msg:
            return None
        if len(msg) != SONAR_PKT_LEN:
            self._dropped_count += 1
            # 前 5 次异常帧打印，便于排查
            if self._dropped_count <= 5:
                try:
                    import binascii
                    src = binascii.hexlify(host, ':').decode() if host else "?"
                    print("[Sonar] 丢弃异常长度帧 len={} src={} (#{})"
                          .format(len(msg), src, self._dropped_count))
                except Exception:
                    print("[Sonar] 丢弃异常长度帧 len={} (#{})".format(
                        len(msg), self._dropped_count))
            return None

        pkt = decode_sonar_packet(bytes(msg))
        if pkt is None:
            self._dropped_count += 1
            if self._dropped_count <= 5:
                print("[Sonar] 解码/校验失败 #{}".format(self._dropped_count))
            return None

        self._packet_count += 1
        now_ms = time.ticks_ms()
        self._last_recv_ms = now_ms
        self._last_alarm_level = pkt["alarm_level"]

        # 前 5 帧 + 之后每 50 帧打印一次，确认链路活着且不刷屏
        if self._packet_count <= 5 or self._packet_count % 50 == 0:
            alarm_labels = {0: "无鱼", 1: "底层拱窝", 2: "中层截杀"}
            print("[Sonar] RX #{} base={}mm cur={}mm alarm={} ({})".format(
                self._packet_count,
                pkt["base_depth"], pkt["current_depth"],
                pkt["alarm_level"],
                alarm_labels.get(pkt["alarm_level"], "?")))

        if pkt["valid"]:
            # 有效帧：转换为 cm 并更新缓存
            dist_cm = pkt["current_depth"] / 10.0
            base_cm = pkt["base_depth"] / 10.0
            self._last_distance_cm = dist_cm
            self._last_baseline_cm = base_cm

            return {
                "distance_cm": dist_cm,
                "baseline_cm": base_cm,
                "status": STATUS_OK,
                "fish_event": pkt["alarm_level"] > 0,
                "alarm_level": pkt["alarm_level"],
            }
        else:
            # 无效帧（current_depth == 0xFFFF）：传感器故障
            self._last_distance_cm = None
            return {
                "distance_cm": None,
                "baseline_cm": pkt["base_depth"] / 10.0 if pkt["base_depth"] > 0 else self._last_baseline_cm,
                "status": STATUS_COMM_FAIL,
                "fish_event": False,
                "alarm_level": ALARM_NONE,
            }

    def get_status(self) -> dict:
        return {
            "initialized": self._initialized,
            "packets": self._packet_count,
            "dropped": self._dropped_count,
            "last_recv_ms": self._last_recv_ms,
            "last_distance_cm": self._last_distance_cm,
            "last_baseline_cm": self._last_baseline_cm,
            "last_alarm_level": self._last_alarm_level,
        }
