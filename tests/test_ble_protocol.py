"""
Part B：ESP32 ↔ 小程序 BLE 协议互验证测试
=============================================
用 Python 同时模拟 ESP32 编码端和小程序解码端，验证协议完全对齐。
环形缓冲区测试验证断连补传逻辑正确性。
"""
import sys, os, struct

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "esp32"))

from esp32.ble.protocol import (
    encode_realtime_data, encode_history_batch, encode_status_reply,
    decode_incoming,
)
from esp32.config import (
    CMD_TIME_SYNC, CMD_REALTIME_DATA, CMD_HISTORY_DATA,
    CMD_SYNC_ACK, CMD_STATUS_QUERY, CMD_STATUS_REPLY,
)
from esp32.storage.ring_buffer import RingBuffer

# ── 小程序侧解码逻辑的 Python 复现 ──
# 与 miniprogram/utils/protocol.js 完全对齐

TEMP_NONE = -999.0
PRESS_NONE = 0.0


def _to_nullable(value, placeholder):
    """JS 侧 toNullable() 的 Python 复现。"""
    return None if abs(value - placeholder) < 0.01 else value


def _fmt_temp(value):
    """JS 侧 fmtTemp() 的 Python 复现。"""
    return round(value, 2) if value is not None else None


def js_decode_realtime(data: bytes) -> dict:
    """模拟 JS decodeRealtimeData()。"""
    if len(data) < 21:
        return {"cmd": CMD_REALTIME_DATA, "error": "实时数据帧长度不足"}
    cmd = data[0]
    ts = struct.unpack_from("<I", data, 1)[0]
    tb_raw = struct.unpack_from("<f", data, 5)[0]
    tm_raw = struct.unpack_from("<f", data, 9)[0]
    ts_raw = struct.unpack_from("<f", data, 13)[0]
    pl_raw = struct.unpack_from("<f", data, 17)[0]

    tb = _fmt_temp(_to_nullable(tb_raw, TEMP_NONE))
    tm = _fmt_temp(_to_nullable(tm_raw, TEMP_NONE))
    tsf = _fmt_temp(_to_nullable(ts_raw, TEMP_NONE))
    pl = _to_nullable(pl_raw, PRESS_NONE)
    pl = round(pl, 2) if pl is not None else None

    t_diff = round(tsf - tb, 2) if (tsf is not None and tb is not None) else None

    return {
        "cmd": cmd,
        "timestamp": ts,
        "tBottom": tb,
        "tMid": tm,
        "tSurface": tsf,
        "pLocal": pl,
        "tDiff": t_diff,
    }


def js_decode_history_batch(data: bytes) -> dict:
    """模拟 JS decodeHistoryBatch()。"""
    if len(data) < 3:
        return {"cmd": CMD_HISTORY_DATA, "error": "历史数据帧头长度不足"}
    count = struct.unpack_from("<H", data, 1)[0]
    record_size = 20
    expected = 3 + count * record_size
    if len(data) < expected:
        return {"cmd": CMD_HISTORY_DATA, "error": "长度不足"}

    records = []
    for i in range(count):
        offset = 3 + i * record_size
        ts = struct.unpack_from("<I", data, offset)[0]
        tb_raw = struct.unpack_from("<f", data, offset + 4)[0]
        tm_raw = struct.unpack_from("<f", data, offset + 8)[0]
        ts_raw = struct.unpack_from("<f", data, offset + 12)[0]
        pl_raw = struct.unpack_from("<f", data, offset + 16)[0]

        tb = _fmt_temp(_to_nullable(tb_raw, TEMP_NONE))
        tm = _fmt_temp(_to_nullable(tm_raw, TEMP_NONE))
        tsf = _fmt_temp(_to_nullable(ts_raw, TEMP_NONE))
        pl = _to_nullable(pl_raw, PRESS_NONE)
        pl = round(pl, 2) if pl is not None else None
        t_diff = round(tsf - tb, 2) if (tsf is not None and tb is not None) else None

        records.append({
            "timestamp": ts,
            "tBottom": tb, "tMid": tm, "tSurface": tsf,
            "pLocal": pl, "tDiff": t_diff,
        })

    return {"cmd": CMD_HISTORY_DATA, "count": count, "records": records}


def js_decode_status_reply(data: bytes) -> dict:
    """模拟 JS decodeStatusReply()。"""
    if len(data) < 11:
        return {"cmd": CMD_STATUS_REPLY, "error": "状态回复帧长度不足"}
    return {
        "cmd": data[0],
        "capacity": struct.unpack_from("<H", data, 1)[0],
        "count": struct.unpack_from("<H", data, 3)[0],
        "unsent": struct.unpack_from("<H", data, 5)[0],
        "totalWritten": struct.unpack_from("<I", data, 7)[0],
    }


def js_encode_time_sync(unix_ts: int) -> bytes:
    """模拟 JS encodeTimeSync()。"""
    return struct.pack("<BI", CMD_TIME_SYNC, unix_ts)


def js_encode_sync_ack(count: int) -> bytes:
    """模拟 JS encodeSyncAck()。"""
    return struct.pack("<BH", CMD_SYNC_ACK, count)


def js_encode_status_query() -> bytes:
    """模拟 JS encodeStatusQuery()。"""
    return struct.pack("<B", CMD_STATUS_QUERY)


# ================================================================
#  Task B1：帧编解码一致性
# ================================================================

class TestFrameEncoding:
    """B1: 帧编解码一致性。"""

    # B1-1
    def test_realtime_frame_length(self):
        frame = encode_realtime_data(1714000000, 18.5, 19.0, 20.5, 1008.5)
        assert len(frame) == 21

    # B1-2
    def test_realtime_roundtrip_normal(self):
        ts, tb, tm, tsf, pl = 1714000000, 18.5, 19.0, 20.5, 1008.5
        frame = encode_realtime_data(ts, tb, tm, tsf, pl)
        decoded = js_decode_realtime(frame)
        assert decoded["timestamp"] == ts
        assert abs(decoded["tBottom"] - tb) < 0.01
        assert abs(decoded["tMid"] - tm) < 0.01
        assert abs(decoded["tSurface"] - tsf) < 0.01
        assert abs(decoded["pLocal"] - pl) < 0.01

    # B1-3
    def test_realtime_with_none(self):
        frame = encode_realtime_data(1714000000, None, None, 20.0, None)
        decoded = js_decode_realtime(frame)
        assert decoded["tBottom"] is None
        assert decoded["tMid"] is None
        assert abs(decoded["tSurface"] - 20.0) < 0.01
        assert decoded["pLocal"] is None

    # B1-4
    def test_realtime_tdiff(self):
        frame = encode_realtime_data(1714000000, 19.0, 20.0, 22.0, 1008.0)
        decoded = js_decode_realtime(frame)
        assert abs(decoded["tDiff"] - 3.0) < 0.01

    # B1-5
    def test_history_batch_3_records(self):
        records = [
            (1714000000 + i * 5, 18.0 + i * 0.1, 19.0, 20.0, 1008.0)
            for i in range(3)
        ]
        frame = encode_history_batch(records)
        assert len(frame) == 3 + 3 * 20  # 63 bytes
        decoded = js_decode_history_batch(frame)
        assert decoded["count"] == 3
        assert len(decoded["records"]) == 3
        assert decoded["records"][0]["timestamp"] == 1714000000
        assert abs(decoded["records"][2]["tBottom"] - 18.2) < 0.01

    # B1-6
    def test_history_batch_empty(self):
        frame = encode_history_batch([])
        assert len(frame) == 3
        decoded = js_decode_history_batch(frame)
        assert decoded["count"] == 0
        assert decoded["records"] == []

    # B1-7
    def test_status_reply(self):
        frame = encode_status_reply(2160, 100, 50, 500)
        assert len(frame) == 11
        decoded = js_decode_status_reply(frame)
        assert decoded["capacity"] == 2160
        assert decoded["count"] == 100
        assert decoded["unsent"] == 50
        assert decoded["totalWritten"] == 500

    # B1-8
    def test_time_sync_encode(self):
        frame = js_encode_time_sync(1714000000)
        assert len(frame) == 5
        assert frame[0] == CMD_TIME_SYNC
        decoded = decode_incoming(frame)
        assert decoded["cmd"] == CMD_TIME_SYNC
        assert decoded["timestamp"] == 1714000000

    # B1-9
    def test_sync_ack_encode(self):
        frame = js_encode_sync_ack(10)
        assert len(frame) == 3
        assert frame[0] == CMD_SYNC_ACK
        decoded = decode_incoming(frame)
        assert decoded["cmd"] == CMD_SYNC_ACK
        assert decoded["count"] == 10

    # B1-10
    def test_status_query_encode(self):
        frame = js_encode_status_query()
        assert len(frame) == 1
        assert frame[0] == CMD_STATUS_QUERY
        decoded = decode_incoming(frame)
        assert decoded["cmd"] == CMD_STATUS_QUERY


# ================================================================
#  Task B2：协议边界与异常
# ================================================================

class TestProtocolEdgeCases:
    """B2: 协议边界与异常。"""

    # B2-1
    def test_decode_empty(self):
        result = decode_incoming(b"")
        assert result["cmd"] is None
        assert "空数据" in result["error"]

    # B2-2
    def test_decode_unknown_cmd(self):
        result = decode_incoming(bytes([0xFF]))
        assert "未知指令码" in result["error"]

    # B2-3 对表帧4字节兼容
    def test_time_sync_4byte_compat(self):
        frame = struct.pack("<BI", CMD_TIME_SYNC, 1714000000)  # 5字节
        result = decode_incoming(frame)
        assert result["cmd"] == CMD_TIME_SYNC
        assert result["timestamp"] == 1714000000

    # B2-4 对表帧数据不足
    def test_time_sync_too_short(self):
        frame = struct.pack("<BB", CMD_TIME_SYNC, 0x00)  # 仅2字节
        result = decode_incoming(frame)
        assert "error" in result

    # B2-5 温度占位符精度
    def test_temp_placeholder_precision(self):
        frame = encode_realtime_data(1000, None, None, None, 1008.0)
        decoded = js_decode_realtime(frame)
        assert decoded["tBottom"] is None
        assert decoded["tMid"] is None
        assert decoded["tSurface"] is None

    # B2-6 气压占位符
    def test_pressure_placeholder(self):
        frame = encode_realtime_data(1000, 18.0, 19.0, 20.0, None)
        decoded = js_decode_realtime(frame)
        assert decoded["pLocal"] is None

    # B2-7 float精度
    def test_float_precision(self):
        val = 18.123456789
        frame = encode_realtime_data(1000, val, 19.0, 20.0, 1008.0)
        decoded = js_decode_realtime(frame)
        # 32位float精度约6-7位有效数字，round(2)后误差在0.01内
        assert abs(decoded["tBottom"] - val) < 0.01


# ================================================================
#  Task B3：环形缓冲区测试
# ================================================================

class TestRingBuffer:
    """B3: 环形缓冲区。"""

    # B3-1
    def test_empty_buffer(self):
        buf = RingBuffer(capacity=10)
        assert buf.count == 0
        assert buf.unsent_count == 0
        assert buf.get_latest() is None

    # B3-2
    def test_write_10(self):
        buf = RingBuffer(capacity=100)
        for i in range(10):
            buf.write(1000 + i * 5, 18.0, 19.0, 20.0, 1008.0)
        assert buf.count == 10
        assert buf.unsent_count == 10

    # B3-3
    def test_mark_sent(self):
        buf = RingBuffer(capacity=100)
        for i in range(10):
            buf.write(1000 + i * 5, 18.0, 19.0, 20.0, 1008.0)
        buf.mark_sent(5)
        assert buf.unsent_count == 5

    # B3-4 覆盖测试
    def test_overflow(self):
        buf = RingBuffer(capacity=5)
        for i in range(8):
            buf.write(1000 + i * 5, float(i), 0.0, 0.0, 0.0)
        assert buf.count == 5
        latest = buf.get_latest()
        assert latest[0] == 1000 + 7 * 5  # 最新一条的时间戳

    # B3-5 覆盖后 unsent 修正
    def test_overflow_unsent_correction(self):
        buf = RingBuffer(capacity=5)
        for i in range(8):
            buf.write(1000 + i * 5, float(i), 0.0, 0.0, 0.0)
        # 未 mark_sent，但前3条已被覆盖
        # unsent_count 应自动修正
        assert buf.unsent_count == 5  # 只剩5条有效

    # B3-6 get_unsent 分批
    def test_get_unsent_batch(self):
        buf = RingBuffer(capacity=100)
        for i in range(10):
            buf.write(1000 + i * 5, float(i), 0.0, 0.0, 0.0)
        batch = buf.get_unsent(max_count=3)
        assert len(batch) == 3
        assert batch[0][0] == 1000  # 最早的未同步

    # B3-7 get_latest
    def test_get_latest(self):
        buf = RingBuffer(capacity=100)
        for i in range(5):
            buf.write(1000 + i * 5, float(i), 0.0, 0.0, 0.0)
        latest = buf.get_latest()
        assert latest[0] == 1000 + 4 * 5
        assert latest[1] == 4.0

    # B3-8 get_status
    def test_get_status(self):
        buf = RingBuffer(capacity=100)
        for i in range(10):
            buf.write(1000 + i * 5, 0.0, 0.0, 0.0, 0.0)
        buf.mark_sent(3)
        status = buf.get_status()
        assert status["capacity"] == 100
        assert status["count"] == 10
        assert status["unsent"] == 7
        assert status["total_written"] == 10
