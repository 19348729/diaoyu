"""
BLE GATT 服务模块 (BLE Service)
=================================
管理 BLE 广播、GATT 服务定义、连接状态、数据收发。
基于 MicroPython 的 bluetooth 模块（aioble 不可用时回退到底层 API）。
"""

import bluetooth
import time
from micropython import const

from config import (
    BLE_DEVICE_NAME, BLE_SERVICE_UUID, BLE_TX_CHAR_UUID, BLE_RX_CHAR_UUID,
    BLE_BATCH_SIZE, CMD_TIME_SYNC, CMD_SYNC_ACK, CMD_STATUS_QUERY,
    CMD_PULL_HISTORY, CMD_BULK_DUMP, CMD_DUMP_COMPLETE, CMD_ENTER_REALTIME,
)
from ble.protocol import (
    decode_incoming, encode_realtime_data, encode_history_batch,
    encode_status_reply, encode_dump_complete,
)

# ── BLE 事件常量 ──
_IRQ_CENTRAL_CONNECT = const(1)
_IRQ_CENTRAL_DISCONNECT = const(2)
_IRQ_GATTS_WRITE = const(3)


def _uuid(uuid_str):
    """将 UUID 字符串转换为 bluetooth.UUID 对象。"""
    return bluetooth.UUID(uuid_str)


class BLEService:
    """BLE GATT 服务管理器。

    提供一个 Service 和两个 Characteristic：
        - TX (Notify): ESP32 向小程序推送数据
        - RX (Write):  小程序向 ESP32 发送指令
    """

    def __init__(self, time_sync, ring_buffer):
        """
        Args:
            time_sync:   TimeSync 实例，用于处理对表指令
            ring_buffer: RingBuffer 实例，用于获取历史数据和状态
        """
        self._ble = bluetooth.BLE()
        self._time_sync = time_sync
        self._ring_buffer = ring_buffer

        self._conn_handle = None        # 当前连接句柄
        self._tx_handle = None          # TX 特征值句柄
        self._rx_handle = None          # RX 特征值句柄
        self._connected = False         # 是否有设备连接
        self._time_synced = False       # 是否已完成对表
        self._just_reconnected = False  # 刚重连标志（用于触发历史数据补传）
        self._syncing_history = False   # 正在补传历史数据
        self._dump_offset = 0           # 快闪数据偏移量
        self._realtime_mode = False     # 实时数据推送开关

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def is_time_synced(self) -> bool:
        return self._time_synced

    @property
    def just_reconnected(self) -> bool:
        return self._just_reconnected

    def clear_reconnect_flag(self):
        self._just_reconnected = False

    def init(self):
        """初始化 BLE 并注册 GATT 服务。"""
        self._ble.active(True)
        self._ble.irq(self._irq_handler)

        # 定义 GATT 服务
        # TX: Notify (0x0010) + Read (0x0002)
        # RX: Write (0x0008) + Write No Response (0x0004)
        tx_char = (
            _uuid(BLE_TX_CHAR_UUID),
            bluetooth.FLAG_NOTIFY | bluetooth.FLAG_READ,
        )
        rx_char = (
            _uuid(BLE_RX_CHAR_UUID),
            bluetooth.FLAG_WRITE | bluetooth.FLAG_WRITE_NO_RESPONSE,
        )
        service = (
            _uuid(BLE_SERVICE_UUID),
            (tx_char, rx_char),
        )

        # 注册服务，获取特征值句柄
        ((self._tx_handle, self._rx_handle),) = self._ble.gatts_register_services((service,))

        # 设置 RX 缓冲区大小（默认可能太小）
        self._ble.gatts_set_buffer(self._rx_handle, 256)

        print("[BLE] GATT 服务已注册")
        print("[BLE]   TX handle: {}".format(self._tx_handle))
        print("[BLE]   RX handle: {}".format(self._rx_handle))

        # 开始广播
        self._start_advertising()

    def _start_advertising(self):
        """开始 BLE 广播。"""
        # 构造广播数据
        name_bytes = BLE_DEVICE_NAME.encode("utf-8")
        # AD Type: 0x01 = Flags, 0x09 = Complete Local Name
        adv_data = (
            bytes([2, 0x01, 0x06])  # Flags: General Discoverable + BR/EDR Not Supported
            + bytes([len(name_bytes) + 1, 0x09]) + name_bytes  # Complete Local Name
        )
        self._ble.gap_advertise(100_000, adv_data=adv_data)  # 100ms 间隔
        print("[BLE] 正在广播: '{}'".format(BLE_DEVICE_NAME))

    def _irq_handler(self, event, data):
        """BLE 中断事件处理。"""
        if event == _IRQ_CENTRAL_CONNECT:
            conn_handle, _, _ = data
            self._conn_handle = conn_handle
            self._connected = True
            self._time_synced = False
            self._just_reconnected = True
            self._syncing_history = False
            self._dump_offset = 0
            self._realtime_mode = False
            print("[BLE] 设备已连接 (handle={})".format(conn_handle))
            # 连接后停止广播（单连接模式）
            self._ble.gap_advertise(None)

        elif event == _IRQ_CENTRAL_DISCONNECT:
            conn_handle, _, _ = data
            self._conn_handle = None
            self._connected = False
            self._time_synced = False
            self._just_reconnected = False
            self._syncing_history = False
            self._dump_offset = 0
            self._realtime_mode = False
            print("[BLE] 设备已断开 (handle={})".format(conn_handle))
            # 断开后重新开始广播
            self._start_advertising()

        elif event == _IRQ_GATTS_WRITE:
            conn_handle, attr_handle = data
            if attr_handle == self._rx_handle:
                # 读取小程序发来的数据
                raw = self._ble.gatts_read(self._rx_handle)
                self._handle_rx_data(raw)

    def _handle_rx_data(self, raw: bytes):
        """处理从小程序收到的指令。"""
        msg = decode_incoming(raw)
        cmd = msg.get("cmd")

        if cmd is None:
            print("[BLE] 解码失败: {}".format(msg.get("error")))
            return

        if cmd == CMD_TIME_SYNC:
            # 对表指令
            timestamp = msg.get("timestamp")
            if timestamp:
                self._time_sync.calibrate(timestamp)
                self._time_synced = True
                print("[BLE] 对表完成: {}".format(timestamp))
            else:
                print("[BLE] 对表失败: {}".format(msg.get("error")))

        elif cmd == CMD_SYNC_ACK:
            # 同步确认
            count = msg.get("count", 0)
            self._ring_buffer.mark_sent(count)
            self._dump_offset = 0  # 确认后重置偏移
            print("[BLE] 同步确认: {}条".format(count))
            # 检查是否还有未发送的历史数据
            if self._ring_buffer.unsent_count == 0:
                self._syncing_history = False
                print("[BLE] 历史数据补传完成")

        elif cmd == CMD_STATUS_QUERY:
            # 状态查询 -> 回复缓冲区状态
            status = self._ring_buffer.get_status()
            reply = encode_status_reply(
                status["capacity"], status["count"],
                status["unsent"], status["total_written"],
            )
            self._send(reply)

        elif cmd == CMD_PULL_HISTORY:
            # 手动拉取一批历史数据
            if not self._time_synced:
                print("[BLE] 收到拉取指令但未对表，忽略")
                return
            if self._ring_buffer.unsent_count == 0:
                print("[BLE] 收到拉取指令但无待补数据")
                return
            sent = self.send_history_batch()
            if sent:
                print("[BLE] 手动拉取：已发送一批历史数据")

        elif cmd == CMD_BULK_DUMP:
            if not self._time_synced:
                return
            if self._ring_buffer.unsent_count == 0:
                self._send(encode_dump_complete())
                return
            print("[BLE] 收到快闪拉取指令，开始全量 Dump")
            self._syncing_history = True
            self._dump_offset = 0

        elif cmd == CMD_ENTER_REALTIME:
            print("[BLE] 切换至实时推送模式")
            self._realtime_mode = True

    def send_realtime(self, timestamp, t_water, t_air, p_local) -> bool:
        """发送实时数据帧。

        Returns:
            True 发送成功，False 未连接或发送失败
        """
        if not self._connected or not self._time_synced:
            return False

        frame = encode_realtime_data(timestamp, t_water, t_air, p_local)
        return self._send(frame)

    def send_history_batch(self) -> bool:
        """发送一批历史缓存数据（手动拉取模式）。"""
        if not self._connected or not self._time_synced:
            return False

        unsent = self._ring_buffer.get_unsent(max_count=BLE_BATCH_SIZE)
        if not unsent:
            return False

        frame = encode_history_batch(unsent)
        return self._send(frame)

    def process_fast_dump(self):
        """处理快闪历史数据（供主循环不断调用）。"""
        if not self._syncing_history or not self._connected:
            return

        unsent = self._ring_buffer.get_unsent(max_count=BLE_BATCH_SIZE, offset=self._dump_offset)
        if not unsent:
            self._syncing_history = False
            self._send(encode_dump_complete())
            print("[BLE] 快闪 Dump 结束，等待统一 ACK")
            return

        frame = encode_history_batch(unsent)
        if self._send(frame):
            self._dump_offset += len(unsent)
        else:
            # 发送失败（可能 notify 队列满），等待下次 tick 重试
            pass

    def is_realtime_mode(self) -> bool:
        return self._realtime_mode

    def has_pending_history(self) -> bool:
        """是否还有未同步的历史数据需要补传。"""
        return self._ring_buffer.unsent_count > 0

    def _send(self, data: bytes) -> bool:
        """通过 TX 特征值发送数据（Notify）。"""
        if not self._connected or self._conn_handle is None:
            return False
        try:
            self._ble.gatts_notify(self._conn_handle, self._tx_handle, data)
            return True
        except Exception as e:
            print("[BLE] 发送失败: {}".format(e))
            return False

    def deinit(self):
        """关闭 BLE。"""
        self._ble.active(False)
        print("[BLE] 已关闭")
