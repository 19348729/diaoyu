"""
ESP-NOW 声呐包协议（ESP32-B 测距板 -> ESP32-A 主板）
====================================================
帧结构（共 8 字节，小端序 <BBHBBH）：
    [magic(1)=0x5A] [ver(1)=0x01] [distance_mm(2)] [status(1)] [seq(1)] [crc(2)]

字段:
    magic         : 帧头标识，固定 0x5A，用于过滤非法广播
    ver           : 协议版本，当前 1
    distance_mm   : 距离（毫米），uint16_le；0xFFFF 表示无效
    status        : 0=正常 1=超出量程 2=过近 3=通信失败
    seq           : 序号 0~255 循环，用于丢包统计
    crc           : payload 累加和 & 0xFFFF（前 6 字节求和），简单防御
"""

import struct

SONAR_MAGIC = 0x5A
SONAR_VER = 0x01
SONAR_PKT_LEN = 8

# 状态码（与 ESP32-B esp-hcrs04.py 保持一致）
STATUS_OK = 0
STATUS_OUT_OF_RANGE = 1
STATUS_TOO_NEAR = 2
STATUS_COMM_FAIL = 3

# 距离无效占位
DIST_INVALID = 0xFFFF


def _calc_crc(payload6: bytes) -> int:
    """简单累加和（前 6 字节求和取低 16 位）。"""
    s = 0
    for b in payload6:
        s = (s + b) & 0xFFFF
    return s


def encode_sonar_packet(distance_mm: int, status: int, seq: int) -> bytes:
    """打包一帧 ESP-NOW 声呐数据。

    Args:
        distance_mm: 0~65534；无效请传 0xFFFF
        status:      STATUS_*
        seq:         0~255
    """
    if distance_mm < 0:
        distance_mm = DIST_INVALID
    if distance_mm > 0xFFFF:
        distance_mm = DIST_INVALID
    head = struct.pack("<BBHBB", SONAR_MAGIC, SONAR_VER,
                       distance_mm & 0xFFFF, status & 0xFF, seq & 0xFF)
    crc = _calc_crc(head)
    return head + struct.pack("<H", crc)


def decode_sonar_packet(raw: bytes):
    """解析一帧 ESP-NOW 声呐数据。

    Returns:
        dict {distance_mm, status, seq, valid: bool} 或 None（包非法）
    """
    if not raw or len(raw) != SONAR_PKT_LEN:
        return None
    try:
        magic, ver, dist, status, seq, crc = struct.unpack("<BBHBBH", raw)
    except Exception:
        return None
    if magic != SONAR_MAGIC or ver != SONAR_VER:
        return None
    expected_crc = _calc_crc(raw[:6])
    if crc != expected_crc:
        return None
    return {
        "distance_mm": dist,
        "status": status,
        "seq": seq,
        "valid": (status == STATUS_OK and dist != DIST_INVALID),
    }
