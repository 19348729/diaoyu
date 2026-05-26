"""
BLE 通信协议模块 (Protocol)
==============================
定义 ESP32 与小程序之间的数据包编解码格式。
所有数值使用小端序 struct.pack/unpack。

协议帧格式:
    [1字节 CMD] + [N字节 PAYLOAD]

指令码:
    0x01 对表指令    (小程序 -> ESP32): 4字节 Unix 时间戳
    0x02 实时数据帧  (ESP32 -> 小程序): 时间戳 + 水温 + 气温 + 气压 = 17 字节
    0x03 历史数据帧  (ESP32 -> 小程序): 条数 + N条数据（每条 16 字节）
    0x04 同步确认    (小程序 -> ESP32): 已确认条数
    0x05 状态查询    (小程序 -> ESP32): 无载荷
    0x06 状态回复    (ESP32 -> 小程序): 缓冲区状态
"""

import struct

from config import (
    CMD_TIME_SYNC, CMD_REALTIME_DATA, CMD_HISTORY_DATA,
    CMD_SYNC_ACK, CMD_STATUS_QUERY, CMD_STATUS_REPLY, CMD_PULL_HISTORY,
    CMD_BULK_DUMP, CMD_DUMP_COMPLETE, CMD_ENTER_REALTIME, CMD_SONAR_DATA,
)

# ── 数据帧中 None 值的占位符 ──
# 温度用 -999.0 表示无效（远超正常范围），气压用 0.0 表示无效
_TEMP_NONE = -999.0
_PRESS_NONE = 0.0


def _val_or_placeholder(value, placeholder):
    """将 None 转换为占位符，用于 pack。"""
    return value if value is not None else placeholder


def _placeholder_to_none(value, placeholder):
    """将占位符还原为 None，用于 unpack。"""
    return None if value == placeholder else value


# ──────────────────────────────────────────────
#  编码（ESP32 -> 小程序）
# ──────────────────────────────────────────────

def encode_realtime_data(timestamp: int, t_water, t_air, p_local) -> bytes:
    """编码实时数据帧。

    帧结构 (17 字节):
        CMD(1) + timestamp(4) + t_water(4) + t_air(4) + p_local(4) = 17 字节

    Args:
        timestamp: Unix 时间戳（秒）
        t_water:   水温，可为 None
        t_air:     气温，可为 None
        p_local:   气压 (hPa)，可为 None
    """
    return struct.pack(
        "<BIfff",
        CMD_REALTIME_DATA,
        timestamp,
        _val_or_placeholder(t_water, _TEMP_NONE),
        _val_or_placeholder(t_air, _TEMP_NONE),
        _val_or_placeholder(p_local, _PRESS_NONE),
    )


def encode_history_batch(records: list) -> bytes:
    """编码历史数据批量帧。

    帧结构:
        CMD(1) + count(2) + N * [timestamp(4) + t_water(4) + t_air(4) + p_local(4)]
        每条记录 16 字节

    Args:
        records: [(timestamp, t_water, t_air, p_local), ...]
    """
    count = len(records)
    # 头部: CMD + count
    header = struct.pack("<BH", CMD_HISTORY_DATA, count)

    # 数据部分
    data_parts = []
    for ts, tw, ta, pl in records:
        data_parts.append(struct.pack(
            "<Ifff",
            ts,
            _val_or_placeholder(tw, _TEMP_NONE),
            _val_or_placeholder(ta, _TEMP_NONE),
            _val_or_placeholder(pl, _PRESS_NONE),
        ))

    return header + b"".join(data_parts)


def encode_status_reply(capacity: int, count: int, unsent: int, total_written: int) -> bytes:
    """编码状态回复帧。

    帧结构 (11 字节):
        CMD(1) + capacity(2) + count(2) + unsent(2) + total_written(4)
    """
    return struct.pack(
        "<BHHHI",
        CMD_STATUS_REPLY,
        capacity,
        count,
        unsent,
        total_written,
    )


def encode_dump_complete() -> bytes:
    """编码全量快闪结束标记。

    帧结构 (1 字节):
        CMD(1)
    """
    return struct.pack("<B", CMD_DUMP_COMPLETE)


def encode_sonar_data(timestamp: int, distance_cm, baseline_cm,
                     status: int, fish_event: bool,
                     alarm_level: int = 0) -> bytes:
    """编码水下声呐实时帧。

    帧结构 (16 字节):
        CMD(1) + timestamp(4) + distance_cm(4 float) + baseline_cm(4 float)
        + status(1) + fish_event(1) + alarm_level(1)

    Args:
        timestamp:    Unix 秒时间戳
        distance_cm:  当前距离（cm），可为 None
        baseline_cm:  基准水深基线（cm），可为 None
        status:       0=正常 1=超出量程 2=过近 3=通讯失败
        fish_event:   True=检测到鱼讯
        alarm_level:  0=无鱼 1=底层拱窝 2=中层截杀（由 ESP32-A 边缘端判定）
    """
    d = -999.0 if distance_cm is None else float(distance_cm)
    b = -999.0 if baseline_cm is None else float(baseline_cm)
    return struct.pack(
        '<BIffBBB',
        CMD_SONAR_DATA,
        timestamp & 0xFFFFFFFF,
        d, b,
        status & 0xFF,
        1 if fish_event else 0,
        alarm_level & 0xFF,
    )


# ──────────────────────────────────────────────
#  解码（小程序 -> ESP32）
# ──────────────────────────────────────────────

def decode_incoming(data: bytes) -> dict:
    """解码从小程序收到的数据帧。

    Args:
        data: 原始字节数据

    Returns:
        {"cmd": int, ...} 解码后的指令字典
        解码失败返回 {"cmd": None, "error": str}
    """
    if not data or len(data) < 1:
        return {"cmd": None, "error": "空数据"}

    cmd = data[0]

    try:
        if cmd == CMD_TIME_SYNC:
            # 对表指令: CMD(1) + unix_timestamp(8字节，使用 unsigned long long)
            if len(data) < 9:
                # 兼容4字节时间戳（32位，够用到2106年）
                if len(data) >= 5:
                    timestamp = struct.unpack_from("<I", data, 1)[0]
                else:
                    return {"cmd": cmd, "error": "对表数据长度不足"}
            else:
                timestamp = struct.unpack_from("<Q", data, 1)[0]
            return {"cmd": cmd, "timestamp": timestamp}

        elif cmd == CMD_SYNC_ACK:
            # 同步确认: CMD(1) + confirmed_count(2)
            if len(data) < 3:
                return {"cmd": cmd, "error": "确认数据长度不足"}
            count = struct.unpack_from("<H", data, 1)[0]
            return {"cmd": cmd, "count": count}

        elif cmd in (CMD_STATUS_QUERY, CMD_PULL_HISTORY, CMD_BULK_DUMP, CMD_ENTER_REALTIME):
            # 无载荷
            return {"cmd": cmd}

        else:
            return {"cmd": cmd, "error": "未知指令码: 0x{:02X}".format(cmd)}

    except Exception as e:
        return {"cmd": cmd, "error": "解码异常: {}".format(e)}
