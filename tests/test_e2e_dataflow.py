"""
Part C：小程序 → 后端数据流端到端测试
=========================================
模拟完整链路：ESP32 编码 → 二进制帧 → 解码(JS格式) → 转 SensorReading → 后端预测。
覆盖渐进式报告、多鱼种×多场景矩阵。
"""
import sys, os, struct, time
from datetime import datetime, timezone, timedelta

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "esp32"))

from esp32.ble.protocol import encode_realtime_data, encode_history_batch
from esp32.config import CMD_REALTIME_DATA, CMD_HISTORY_DATA

from domain.value_objects import (
    SensorReading, SensorTimeSeries, ApiData, PredictionResult,
)
from domain.constants import FISH_PROFILES
from domain.tags import TacticalTag
from domain.services import FishingPredictionService
from domain.time_utils import get_time_period, get_season

_CST = timezone(timedelta(hours=8))

# ── 占位符（与双端协议一致）──
TEMP_NONE = -999.0
PRESS_NONE = 0.0


def _to_nullable(value, placeholder):
    return None if abs(value - placeholder) < 0.01 else value


def _fmt(value):
    return round(value, 2) if value is not None else None


# ── 模拟完整链路：ESP32 encode → JS decode → 转 SensorReading ──

def decode_frame_to_js(frame: bytes) -> dict:
    """将 ESP32 编码的二进制帧解码为 JS 格式对象（camelCase 字段名）。"""
    cmd = frame[0]
    if cmd == CMD_REALTIME_DATA:
        ts = struct.unpack_from("<I", frame, 1)[0]
        tb = _fmt(_to_nullable(struct.unpack_from("<f", frame, 5)[0], TEMP_NONE))
        tm = _fmt(_to_nullable(struct.unpack_from("<f", frame, 9)[0], TEMP_NONE))
        tsf = _fmt(_to_nullable(struct.unpack_from("<f", frame, 13)[0], TEMP_NONE))
        pl = _to_nullable(struct.unpack_from("<f", frame, 17)[0], PRESS_NONE)
        pl = round(pl, 2) if pl is not None else None
        return {
            "cmd": cmd, "timestamp": ts,
            "tBottom": tb, "tMid": tm, "tSurface": tsf, "pLocal": pl,
            "tDiff": round(tsf - tb, 2) if (tsf is not None and tb is not None) else None,
        }
    elif cmd == CMD_HISTORY_DATA:
        count = struct.unpack_from("<H", frame, 1)[0]
        records = []
        for i in range(count):
            off = 3 + i * 20
            ts = struct.unpack_from("<I", frame, off)[0]
            tb = _fmt(_to_nullable(struct.unpack_from("<f", frame, off + 4)[0], TEMP_NONE))
            tm = _fmt(_to_nullable(struct.unpack_from("<f", frame, off + 8)[0], TEMP_NONE))
            tsf = _fmt(_to_nullable(struct.unpack_from("<f", frame, off + 12)[0], TEMP_NONE))
            pl = _to_nullable(struct.unpack_from("<f", frame, off + 16)[0], PRESS_NONE)
            pl = round(pl, 2) if pl is not None else None
            records.append({
                "timestamp": ts, "tBottom": tb, "tMid": tm,
                "tSurface": tsf, "pLocal": pl,
                "tDiff": round(tsf - tb, 2) if (tsf is not None and tb is not None) else None,
            })
        return {"cmd": cmd, "count": count, "records": records}
    return {"error": "unknown cmd"}


def js_record_to_sensor_reading(rec: dict) -> SensorReading:
    """模拟小程序上报到后端时的 camelCase → snake_case 字段映射。"""
    return SensorReading(
        timestamp=rec["timestamp"],
        t_bottom=rec["tBottom"],
        t_mid=rec["tMid"],
        t_surface=rec["tSurface"],
        p_local=rec["pLocal"],
    )


def _make_api(weather="sunny"):
    return ApiData(wind_speed=2.5, altitude=150.0, weather_trend=weather)


def _make_cst_ts(year, month, day, hour, minute=0):
    dt = datetime(year, month, day, hour, minute, tzinfo=_CST)
    return int(dt.timestamp())


def _build_esp32_readings(base_ts, count, interval=5,
                          t_bottom=18.0, t_mid=19.0, t_surface=20.0,
                          p_local=1008.0):
    """模拟 ESP32 采集并编码为历史帧，再解码得到 JS 格式记录。"""
    raw_records = []
    for i in range(count):
        ts = base_ts + i * interval
        raw_records.append((ts, t_bottom, t_mid, t_surface, p_local))

    # ESP32 编码为历史帧
    frame = encode_history_batch(raw_records)
    # JS 解码
    decoded = decode_frame_to_js(frame)
    # 转换为后端 SensorReading
    readings = [js_record_to_sensor_reading(r) for r in decoded["records"]]
    return readings


# ================================================================
#  Task C1：数据格式转换链路
# ================================================================

class TestDataFlowConversion:
    """C1: 数据格式转换链路。"""

    # C1-1 单帧完整链路
    def test_single_frame_full_pipeline(self):
        ts, tb, tm, tsf, pl = 1714000000, 18.5, 19.0, 20.5, 1008.5
        frame = encode_realtime_data(ts, tb, tm, tsf, pl)
        js_data = decode_frame_to_js(frame)
        reading = js_record_to_sensor_reading(js_data)

        series = SensorTimeSeries(readings=(reading,))
        svc = FishingPredictionService()
        result = svc.predict_from_series(series, _make_api())

        assert isinstance(result, PredictionResult)
        assert 0 <= result.bite_index <= 100
        assert result.report_stage == "instant"

    # C1-2 历史批量链路
    def test_history_batch_pipeline(self):
        base_ts = int(time.time()) - 300
        readings = _build_esp32_readings(base_ts, 61, interval=5)  # 61条×5s=300s跨度
        assert len(readings) == 61

        series = SensorTimeSeries(readings=tuple(readings))
        svc = FishingPredictionService()
        result = svc.predict_from_series(series, _make_api())

        assert result.report_stage == "brief"
        assert result.confidence == 55
        assert 0 <= result.bite_index <= 100

    # C1-3 字段名映射验证
    def test_field_name_mapping(self):
        frame = encode_realtime_data(1714000000, 18.5, 19.0, 20.5, 1008.5)
        js_data = decode_frame_to_js(frame)

        # JS camelCase 字段
        assert "tBottom" in js_data
        assert "tMid" in js_data
        assert "tSurface" in js_data
        assert "pLocal" in js_data

        # 转换后的 Python snake_case
        reading = js_record_to_sensor_reading(js_data)
        assert reading.t_bottom is not None
        assert reading.t_mid is not None
        assert reading.t_surface is not None
        assert reading.p_local is not None

    # C1-4 None 值透传
    def test_none_passthrough(self):
        frame = encode_realtime_data(1714000000, None, 19.0, None, None)
        js_data = decode_frame_to_js(frame)
        assert js_data["tBottom"] is None
        assert js_data["tSurface"] is None
        assert js_data["pLocal"] is None

        reading = js_record_to_sensor_reading(js_data)
        assert reading.t_bottom is None
        assert reading.t_surface is None
        assert reading.p_local is None
        assert reading.t_mid is not None  # 19.0 保持

    # C1-5 时间戳一致性
    def test_timestamp_consistency(self):
        # 2025-04-15 07:30 CST → spring, morning
        ts = _make_cst_ts(2025, 4, 15, 7, 30)
        frame = encode_realtime_data(ts, 18.0, 19.0, 20.0, 1008.0)
        js_data = decode_frame_to_js(frame)
        reading = js_record_to_sensor_reading(js_data)

        assert reading.timestamp == ts
        assert get_time_period(reading.timestamp) == "morning"
        assert get_season(reading.timestamp) == "spring"


# ================================================================
#  Task C2：渐进式报告端到端
# ================================================================

class TestProgressiveReportE2E:
    """C2: 渐进式报告端到端。"""

    def _build_series(self, duration_sec):
        """构建指定时长的数据，经过完整 ESP32 encode/decode 链路。"""
        base_ts = int(time.time()) - duration_sec
        count = max(1, duration_sec // 5 + 1)  # +1 保证跨度 = (count-1)*5 = duration_sec
        readings = _build_esp32_readings(
            base_ts, count, interval=5,
            t_bottom=18.0, t_mid=19.0, t_surface=20.0, p_local=1008.0,
        )
        return SensorTimeSeries(readings=tuple(readings))

    # C2-1
    def test_instant_stage(self):
        # 1 条数据
        base_ts = int(time.time())
        frame = encode_realtime_data(base_ts, 18.0, 19.0, 20.0, 1008.0)
        js_data = decode_frame_to_js(frame)
        reading = js_record_to_sensor_reading(js_data)
        series = SensorTimeSeries(readings=(reading,))

        svc = FishingPredictionService()
        result = svc.predict_from_series(series, _make_api())
        assert result.report_stage == "instant"
        assert result.confidence == 30

    # C2-2
    def test_brief_stage(self):
        series = self._build_series(300)  # 5 分钟
        svc = FishingPredictionService()
        result = svc.predict_from_series(series, _make_api())
        assert result.report_stage == "brief"
        assert result.confidence == 55

    # C2-3
    def test_standard_stage(self):
        series = self._build_series(600)  # 10 分钟
        svc = FishingPredictionService()
        result = svc.predict_from_series(series, _make_api())
        assert result.report_stage == "standard"
        assert result.confidence == 75

    # C2-4
    def test_full_stage(self):
        series = self._build_series(1800)  # 30 分钟
        svc = FishingPredictionService()
        result = svc.predict_from_series(series, _make_api())
        assert result.report_stage == "full"
        assert result.confidence == 90

    # C2-5 渐进置信度递增
    def test_confidence_increases(self):
        svc = FishingPredictionService()
        confidences = []
        for duration in [0, 300, 600, 1800]:
            if duration == 0:
                base_ts = int(time.time())
                readings = _build_esp32_readings(base_ts, 1)
            else:
                base_ts = int(time.time()) - duration
                count = duration // 5
                readings = _build_esp32_readings(base_ts, count)
            series = SensorTimeSeries(readings=tuple(readings))
            result = svc.predict_from_series(series, _make_api())
            confidences.append(result.confidence)

        # instant < brief < standard < full
        assert confidences == sorted(confidences)
        assert confidences[0] < confidences[-1]


# ================================================================
#  Task C3：多鱼种 × 多场景矩阵
# ================================================================

class TestMultiSpeciesScenarios:
    """C3: 多鱼种×多场景矩阵。"""

    def _make_scenario_series(self, base_ts, duration_sec=1800,
                              t_bottom=18.0, t_mid=19.0, t_surface=20.0,
                              p_local=1008.0):
        """构建指定场景的 full 阶段数据。"""
        count = duration_sec // 5
        readings = _build_esp32_readings(
            base_ts, count, interval=5,
            t_bottom=t_bottom, t_mid=t_mid,
            t_surface=t_surface, p_local=p_local,
        )
        return SensorTimeSeries(readings=tuple(readings))

    # C3-1 鲫鱼-冬季早晨
    def test_jiyu_winter_morning(self):
        # 1月7:00，水底8℃
        base_ts = _make_cst_ts(2025, 1, 15, 7, 0) - 1800
        series = self._make_scenario_series(
            base_ts, t_bottom=8.0, t_mid=8.5, t_surface=9.0, p_local=1020.0,
        )
        svc = FishingPredictionService(fish_profile=FISH_PROFILES["鲫鱼"])
        result = svc.predict_from_series(series, _make_api())

        # 8℃在鲫鱼可忍受区间[5,32]内 → base=40，冬季-8分
        assert result.bite_index < 70
        assert TacticalTag.SEASON_WINTER_COLD.value in result.tactical_tags
        assert TacticalTag.PERIOD_MORNING_GOLDEN.value in result.tactical_tags

    # C3-2 鲢鳙-夏季傍晚
    def test_liangyong_summer_evening(self):
        # 7月19:00，表层30℃
        base_ts = _make_cst_ts(2025, 7, 15, 19, 0) - 1800
        series = self._make_scenario_series(
            base_ts, t_bottom=24.0, t_mid=27.0, t_surface=30.0, p_local=1005.0,
        )
        svc = FishingPredictionService(fish_profile=FISH_PROFILES["鲢鳙"])
        result = svc.predict_from_series(series, _make_api())

        # 鲢鳙 top 层用 surface=30℃, 最适[25,32] → base=80
        assert result.bite_index >= 50
        assert TacticalTag.SEASON_SUMMER_HEAT.value in result.tactical_tags
        assert TacticalTag.PERIOD_EVENING_PEAK.value in result.tactical_tags

    # C3-3 土鲮-低温停口
    def test_tuling_cold_shutout(self):
        # 12月，水底12℃（土鲮低于14度基本停口）
        base_ts = _make_cst_ts(2025, 12, 15, 14, 0) - 1800
        series = self._make_scenario_series(
            base_ts, t_bottom=12.0, t_mid=12.5, t_surface=13.0, p_local=1015.0,
        )
        svc = FishingPredictionService(fish_profile=FISH_PROFILES["土鲮"])
        result = svc.predict_from_series(series, _make_api())

        # 12℃ 不在 tolerable[14,32] 范围 → base_score_outside=0
        assert result.bite_index <= 30

    # C3-4 鲤鱼-气压骤降（一票否决）
    def test_liyu_pressure_crash_veto(self):
        # 构造气压骤降场景：1012→1005 = -7hPa
        base_ts = int(time.time()) - 1800
        count = 360
        raw_records = []
        for i in range(count):
            ts = base_ts + i * 5
            progress = i / max(count - 1, 1)
            p = round(1012.0 - progress * 7.0, 2)
            raw_records.append((ts, 22.0, 23.0, 24.0, p))

        frame = encode_history_batch(raw_records)
        decoded = decode_frame_to_js(frame)
        readings = [js_record_to_sensor_reading(r) for r in decoded["records"]]
        series = SensorTimeSeries(readings=tuple(readings))

        svc = FishingPredictionService(fish_profile=FISH_PROFILES["鲤鱼"])
        result = svc.predict_from_series(series, _make_api())

        assert result.bite_index == 5
        assert TacticalTag.RATING_VETO.value in result.tactical_tags

    # C3-5 翘嘴-全温域
    def test_qiaozui_temperature_ranges(self):
        """翘嘴 optimal[18,30], tolerable[3,36]。测试三个温度点。"""
        svc = FishingPredictionService(fish_profile=FISH_PROFILES["翘嘴"])
        scores = []

        for t_surface in [5.0, 20.0, 35.0]:
            base_ts = int(time.time()) - 1800
            series = self._make_scenario_series(
                base_ts,
                t_bottom=t_surface - 2, t_mid=t_surface - 1,
                t_surface=t_surface, p_local=1010.0,
            )
            result = svc.predict_from_series(series, _make_api())
            scores.append(result.bite_index)

        # 5℃=tolerable, 20℃=optimal, 35℃=tolerable
        # optimal 分数应最高
        assert scores[1] > scores[0]  # 20℃ > 5℃
        assert scores[1] > scores[2]  # 20℃ > 35℃
        # 5℃和35℃都在 tolerable，分数应相近
        assert all(0 <= s <= 100 for s in scores)
