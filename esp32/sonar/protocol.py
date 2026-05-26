"""
ESP-NOW 声呐包协议（ESP32-A 边缘节点 -> ESP32-B 岸上主板）
====================================================
帧结构（共 10 字节，小端序 <IHHBB）：
    [timestamp(4)] [base_depth(2)] [current_depth(2)] [alarm_level(1)] [checksum(1)]

字段:
    timestamp       : 毫秒级时间戳 (time.ticks_ms())，uint32_le
    base_depth      : 基准水深（毫米），uint16_le
    current_depth   : 当前水深（毫米），uint16_le；0xFFFF 表示无效（传感器故障）
    alarm_level     : 鱼讯告警级别
                      0 = 无鱼
                      1 = 底层拱窝（鲤鱼/鲫鱼贴底拱窝搅局，由方差波动判定）
                      2 = 中层截杀（鲢鳙/草鱼截杀中心波束，由连续 3 帧突刺判定）
    checksum        : 前 9 字节逐字节异或 (XOR)，简单防御

注意:
    - ESP32-A 已在边缘端完成基准锁定、动态阈值计算和双轨鱼讯判定
    - 岸上只需解码并转发，无需二次判定
"""

import struct

SONAR_PKT_LEN = 10

# 告警级别常量
ALARM_NONE = 0
ALARM_BOTTOM_FISH = 1      # 底层拱窝
ALARM_MID_FISH = 2          # 中层截杀

# 距离无效占位
DIST_INVALID = 0xFFFF

# ── 向下兼容：旧 status 常量映射 ──
# 新协议不再使用传感器状态码，但为了 BLE 层兼容保留映射
STATUS_OK = 0
STATUS_OUT_OF_RANGE = 1
STATUS_TOO_NEAR = 2
STATUS_COMM_FAIL = 3


def _calc_xor_checksum(data: bytes) -> int:
    """逐字节异或校验和。"""
    chk = 0
    for b in data:
        chk ^= b
    return chk


def encode_sonar_packet(timestamp: int, base_depth: int,
                        current_depth: int, alarm_level: int) -> bytes:
    """打包一帧 10 字节 ESP-NOW 声呐数据。

    Args:
        timestamp:     毫秒级时间戳
        base_depth:    基准水深 mm
        current_depth: 当前水深 mm（0xFFFF = 无效）
        alarm_level:   ALARM_NONE / ALARM_BOTTOM_FISH / ALARM_MID_FISH
    """
    payload = struct.pack('<IHHB',
                          timestamp & 0xFFFFFFFF,
                          base_depth & 0xFFFF,
                          current_depth & 0xFFFF,
                          alarm_level & 0xFF)
    chk = _calc_xor_checksum(payload)
    return payload + struct.pack('B', chk)


def decode_sonar_packet(raw: bytes):
    """解析一帧 10 字节 ESP-NOW 声呐数据。

    Returns:
        dict {timestamp, base_depth, current_depth, alarm_level, valid: bool}
        或 None（包非法 / 校验失败）
    """
    if not raw or len(raw) != SONAR_PKT_LEN:
        return None
    try:
        timestamp, base_depth, current_depth, alarm_level, checksum = \
            struct.unpack('<IHHBB', raw)
    except Exception:
        return None

    # 校验 XOR
    expected = _calc_xor_checksum(raw[:9])
    if checksum != expected:
        return None

    return {
        "timestamp": timestamp,
        "base_depth": base_depth,
        "current_depth": current_depth,
        "alarm_level": alarm_level,
        "valid": (current_depth != DIST_INVALID),
    }
