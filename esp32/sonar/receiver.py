"""
声呐 ESP-NOW 接收器（ESP32-A 端）
================================
- 通过 espnow 模块以非阻塞方式收取 ESP32-B 广播的距离包
- 维护近 N 秒滑动均值作为水下基线，与瞬时距离比较产生「鱼经过」事件

注意:
  - 使用前需保证 STA WiFi 已 active(True)（ESP-NOW 依赖 WiFi 射频）
  - 只接收 magic=0x5A 的合法包，其它流量直接丢弃
"""

import time

from sonar.protocol import (
    decode_sonar_packet, SONAR_PKT_LEN,
    STATUS_OK, STATUS_OUT_OF_RANGE, STATUS_TOO_NEAR, STATUS_COMM_FAIL,
)


# ── 鱼经过检测参数 ──
_BASELINE_WINDOW_SEC = 30        # 基线滑动窗口长度（秒）
_FISH_DROP_CM = 5.0              # 距离突然变小多少 cm 视为鱼经过
_FISH_HOLD_MS = 1500              # 触发后保持「fish_event=1」最少持续时间（ms）


class SonarReceiver:
    """ESP-NOW 声呐数据接收器 + 鱼经过事件检测器。"""

    def __init__(self):
        self._espnow = None
        self._initialized = False

        # 滑动窗口（环形数组）
        self._window = []  # [(ticks_ms, dist_cm), ...]

        # 最新一帧
        self._last_distance_cm = None
        self._last_baseline_cm = None
        self._last_status = None
        self._last_seq = -1
        self._last_recv_ms = 0
        self._fish_event_until_ms = 0
        self._packet_count = 0
        self._dropped_count = 0

    def init(self) -> bool:
        """初始化 ESP-NOW（要求 STA WiFi 已 active）。"""
        try:
            import espnow  # MicroPython 内置
            self._espnow = espnow.ESPNow()
            self._espnow.active(True)
            self._initialized = True
            print("[Sonar] ESP-NOW 接收器已启动（仅接收 magic=0x5A 的广播包）")
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
                "distance_cm": float|None, "baseline_cm": float|None,
                "status": int, "fish_event": bool, "seq": int,
              }
            没有新包时返回 None。
        """
        if not self._initialized or self._espnow is None:
            return None

        try:
            host, msg = self._espnow.recv(timeout_ms)
        except Exception as e:
            # 偶发异常静默吞，等下一轮
            return None

        if not msg:
            return None
        if len(msg) != SONAR_PKT_LEN:
            self._dropped_count += 1
            return None

        pkt = decode_sonar_packet(bytes(msg))
        if pkt is None:
            self._dropped_count += 1
            return None

        self._packet_count += 1
        now_ms = time.ticks_ms()
        self._last_recv_ms = now_ms
        self._last_seq = pkt["seq"]
        self._last_status = pkt["status"]

        if pkt["valid"]:
            dist_cm = pkt["distance_mm"] / 10.0
            self._last_distance_cm = dist_cm

            # 维护滑动窗口（仅纳入有效值）
            self._window.append((now_ms, dist_cm))
            self._trim_window(now_ms)

            baseline = self._calc_baseline(now_ms)
            self._last_baseline_cm = baseline

            fish_event = False
            if baseline is not None and (baseline - dist_cm) >= _FISH_DROP_CM:
                # 触发：拉长 hold 时长，防止 UI 闪烁
                self._fish_event_until_ms = time.ticks_add(now_ms, _FISH_HOLD_MS)
                fish_event = True
            else:
                fish_event = time.ticks_diff(self._fish_event_until_ms, now_ms) > 0
        else:
            # 包合法但 status 异常（超出量程 / 通信失败）
            self._last_distance_cm = None
            baseline = self._last_baseline_cm  # 保留上一基线供 UI 显示
            fish_event = False

        return {
            "distance_cm": self._last_distance_cm,
            "baseline_cm": baseline,
            "status": self._last_status,
            "fish_event": fish_event,
            "seq": self._last_seq,
        }

    def _trim_window(self, now_ms: int):
        """裁剪超过窗口长度的旧样本。"""
        cutoff = time.ticks_add(now_ms, -_BASELINE_WINDOW_SEC * 1000)
        while self._window and time.ticks_diff(self._window[0][0], cutoff) < 0:
            self._window.pop(0)
        # 防御：最多保留 60 个样本
        if len(self._window) > 60:
            self._window = self._window[-60:]

    def _calc_baseline(self, now_ms: int):
        """近 N 秒均值，作为「水底/无鱼」基线。"""
        if not self._window:
            return None
        # 至少 3 个样本才认为基线有意义
        if len(self._window) < 3:
            return self._window[-1][1]
        s = 0.0
        n = 0
        for _, d in self._window:
            s += d
            n += 1
        return s / n if n > 0 else None

    def get_status(self) -> dict:
        return {
            "initialized": self._initialized,
            "packets": self._packet_count,
            "dropped": self._dropped_count,
            "last_recv_ms": self._last_recv_ms,
            "last_distance_cm": self._last_distance_cm,
            "last_baseline_cm": self._last_baseline_cm,
        }
