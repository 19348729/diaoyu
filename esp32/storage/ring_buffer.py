"""
环形缓冲区模块 (Ring Buffer)
===============================
用于在 BLE 断连期间缓存传感器采样数据。
支持写入游标和同步游标的独立管理，实现重连后精准补传。

数据记录格式（v2）：
    (timestamp, t_water, t_air, p_local)
"""

from config import RING_BUFFER_CAPACITY
import os
import struct


class RingBuffer:
    """定长环形缓冲区，满时自动覆盖最旧数据。

    数据记录格式（元组）：
        (timestamp, t_water, t_air, p_local)

    游标设计：
        write_cursor:  下一个写入位置（持续递增取模）
        sync_cursor:   已同步到小程序的位置
        total_written: 累计写入总条数（用于判断是否发生过覆盖）
    """

    def __init__(self, capacity=None, persistent=False, filepath="/ring.bin"):
        self._capacity = capacity or RING_BUFFER_CAPACITY
        self._buffer = [None] * self._capacity
        self._write_cursor = 0      # 下一个写入位置
        self._sync_cursor = 0       # 已同步位置
        self._total_written = 0     # 累计写入总数
        self._count = 0             # 当前有效数据条数
        
        self._persistent = persistent
        self._filepath = filepath
        if self._persistent:
            self._load_from_flash()

    def _load_from_flash(self):
        try:
            try:
                os.stat(self._filepath)
            except OSError:
                self._save_header()
                return

            with open(self._filepath, 'rb') as f:
                header = f.read(12)
                if len(header) == 12:
                    self._write_cursor, self._sync_cursor, self._total_written = struct.unpack('<III', header)
                    self._count = min(self._total_written, self._capacity)
                    
                    for i in range(self._capacity):
                        f.seek(12 + i * 16)
                        data = f.read(16)
                        if len(data) == 16:
                            ts, tw, ta, pl = struct.unpack('<Ifff', data)
                            tw = None if tw == -999.0 else tw
                            ta = None if ta == -999.0 else ta
                            pl = None if pl == 0.0 else pl
                            self._buffer[i] = (ts, tw, ta, pl)
        except Exception as e:
            print("[RingBuffer] 恢复数据失败:", e)

    def _save_header(self):
        if not self._persistent:
            return
        try:
            mode = 'r+b'
            try:
                os.stat(self._filepath)
            except OSError:
                mode = 'w+b'
            with open(self._filepath, mode) as f:
                f.seek(0)
                f.write(struct.pack('<III', self._write_cursor, self._sync_cursor, self._total_written))
        except Exception as e:
            print("[RingBuffer] 保存Header失败:", e)

    def _save_record(self, pos, timestamp, t_water, t_air, p_local):
        if not self._persistent:
            return
        try:
            tw = t_water if t_water is not None else -999.0
            ta = t_air if t_air is not None else -999.0
            pl = p_local if p_local is not None else 0.0
            with open(self._filepath, 'r+b') as f:
                f.seek(12 + pos * 16)
                f.write(struct.pack('<Ifff', timestamp, tw, ta, pl))
        except Exception as e:
            print("[RingBuffer] 保存记录失败:", e)

    @property
    def capacity(self) -> int:
        """缓冲区总容量。"""
        return self._capacity

    @property
    def count(self) -> int:
        """当前有效数据条数。"""
        return self._count

    @property
    def unsent_count(self) -> int:
        """未同步的数据条数。"""
        if self._total_written == 0:
            return 0
        # 如果发生过覆盖，且 sync_cursor 指向的数据已被覆盖
        if self._total_written > self._capacity:
            # 最旧的有效数据位置
            oldest_valid = self._total_written - self._capacity
            if self._sync_cursor < oldest_valid:
                # sync_cursor 指向的数据已被覆盖，重置到最旧有效位置
                self._sync_cursor = oldest_valid
        return self._total_written - self._sync_cursor

    def write(self, timestamp: int, t_water, t_air, p_local):
        """写入一条传感器数据。

        Args:
            timestamp: 时间戳（Unix 秒）
            t_water:   水温 (℃)，可为 None
            t_air:     气温 (℃)，可为 None
            p_local:   本地气压 (hPa)，可为 None
        """
        pos = self._write_cursor % self._capacity
        self._buffer[pos] = (timestamp, t_water, t_air, p_local)
        self._write_cursor = (self._write_cursor + 1) % self._capacity
        self._total_written += 1
        if self._count < self._capacity:
            self._count += 1
            
        if self._persistent:
            self._save_record(pos, timestamp, t_water, t_air, p_local)
            self._save_header()

    def get_unsent(self, max_count=None, offset=0) -> list:
        """获取未同步的数据列表。

        Args:
            max_count: 最多返回条数（用于分批发送），None 表示全部
            offset: 偏移量，用于跳过已发送但尚未确认的数据

        Returns:
            [(timestamp, t_water, t_air, p_local), ...]
        """
        n = self.unsent_count - offset
        if n <= 0:
            return []

        if max_count is not None:
            n = min(n, max_count)

        result = []
        for i in range(n):
            # 计算实际缓冲区索引
            logical_pos = self._sync_cursor + offset + i
            actual_pos = logical_pos % self._capacity
            data = self._buffer[actual_pos]
            if data is not None:
                result.append(data)

        return result

    def mark_sent(self, count: int):
        """标记已成功同步的条数，推进同步游标。

        Args:
            count: 已确认发送成功的条数
        """
        self._sync_cursor = min(
            self._sync_cursor + count,
            self._total_written,
        )
        self._save_header()

    def mark_all_sent(self):
        """将所有已写入的数据标记为已同步（用于首次连接跳过历史）。"""
        self._sync_cursor = self._total_written
        self._save_header()

    def get_latest(self) -> tuple:
        """获取最新一条数据（用于实时推送）。

        Returns:
            (timestamp, t_water, t_air, p_local) 或 None
        """
        if self._total_written == 0:
            return None
        pos = (self._write_cursor - 1) % self._capacity
        return self._buffer[pos]

    def get_status(self) -> dict:
        """获取缓冲区状态信息（用于状态查询指令回复）。

        Returns:
            {
                "capacity": int,
                "count": int,
                "unsent": int,
                "total_written": int,
            }
        """
        return {
            "capacity": self._capacity,
            "count": self._count,
            "unsent": self.unsent_count,
            "total_written": self._total_written,
        }

    def clear(self):
        """清空缓冲区（一般不需要，仅用于测试或重置）。"""
        self._buffer = [None] * self._capacity
        self._write_cursor = 0
        self._sync_cursor = 0
        self._total_written = 0
        self._count = 0
