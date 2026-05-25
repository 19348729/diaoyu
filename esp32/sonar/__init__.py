"""水下声呐探鱼模块（ESP-NOW 接收 + 鱼经过检测）。"""
from sonar.protocol import (
    SONAR_PKT_LEN, SONAR_MAGIC,
    STATUS_OK, STATUS_OUT_OF_RANGE, STATUS_TOO_NEAR, STATUS_COMM_FAIL,
    encode_sonar_packet, decode_sonar_packet,
)
from sonar.receiver import SonarReceiver
