"""
时间同步管理模块 (Time Synchronization)
========================================
负责接收小程序校准时间，维护 ESP32 内部绝对时间戳。
使用 time.ticks_ms() 做高精度相对计时，避免依赖不可靠的 time.time()。
"""

import time


class TimeSync:
    """时间同步管理器。

    工作原理：
        1. 小程序通过 BLE 发送当前 Unix 时间戳（秒级）
        2. ESP32 记录收到时的 ticks_ms 作为基准锚点
        3. 之后通过 ticks_diff 计算当前绝对时间
    """

    def __init__(self):
        self._calibrated = False
        self._base_unix = 0         # 校准时收到的 Unix 时间戳（秒）
        self._base_ticks = 0        # 校准时的 ticks_ms 值
        self._boot_ticks = time.ticks_ms()  # 开机时的 ticks_ms，用于未校准时的相对计时

    @property
    def is_calibrated(self) -> bool:
        """是否已完成时间校准。"""
        return self._calibrated

    def calibrate(self, unix_timestamp: int) -> None:
        """接收小程序发来的 Unix 时间戳进行校准。

        Args:
            unix_timestamp: Unix 时间戳（秒），由小程序从手机系统时间获取
        """
        self._base_unix = unix_timestamp
        self._base_ticks = time.ticks_ms()
        self._calibrated = True
        print("[TimeSync] 校准完成: Unix={}, 本地ticks={}".format(
            unix_timestamp, self._base_ticks))

    def now(self) -> int:
        """获取当前时间戳（Unix 秒）。

        Returns:
            已校准：返回绝对 Unix 时间戳
            未校准：返回自开机以来的秒数（相对时间）
        """
        if self._calibrated:
            elapsed_ms = time.ticks_diff(time.ticks_ms(), self._base_ticks)
            return self._base_unix + elapsed_ms // 1000
        else:
            # 未校准时返回开机相对秒数
            elapsed_ms = time.ticks_diff(time.ticks_ms(), self._boot_ticks)
            return elapsed_ms // 1000

    def now_ms(self) -> int:
        """获取当前时间戳（毫秒精度）。

        Returns:
            已校准：返回绝对 Unix 毫秒时间戳
            未校准：返回自开机以来的毫秒数
        """
        if self._calibrated:
            elapsed_ms = time.ticks_diff(time.ticks_ms(), self._base_ticks)
            return self._base_unix * 1000 + elapsed_ms
        else:
            return time.ticks_diff(time.ticks_ms(), self._boot_ticks)

    def elapsed_since_boot_sec(self) -> int:
        """返回自开机以来经过的秒数（不依赖校准）。"""
        return time.ticks_diff(time.ticks_ms(), self._boot_ticks) // 1000

    def boot_relative_to_unix(self, t_boot: int) -> int:
        """把「开机相对秒」换算成真实 Unix 时间戳。

        对表之前采集的数据，其时间戳是 now() 返回的开机相对秒（见 now()）。
        校准后即可反推开机时刻对应的真实 Unix（boot_epoch），
        从而把对表前的历史数据放回真实时间轴。

        Args:
            t_boot: 记录写入时的开机相对秒
        Returns:
            真实 Unix 时间戳；未校准时原样返回（无映射可用）
        """
        if not self._calibrated:
            return t_boot
        # 校准时刻的开机相对秒 = 校准 ticks 与开机 ticks 之差
        calib_boot_sec = time.ticks_diff(self._base_ticks, self._boot_ticks) // 1000
        # 开机时刻(开机相对秒=0)对应的真实 Unix
        boot_epoch_unix = self._base_unix - calib_boot_sec
        return boot_epoch_unix + t_boot
