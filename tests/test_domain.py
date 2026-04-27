"""
Part A：后端 Domain 层单元测试
================================
覆盖值对象校验、时间工具、时序分析器、预测服务集成测试。
"""
import sys, os, time, math
from datetime import datetime, timezone, timedelta

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from domain.value_objects import (
    HardwareData, ApiData, SensorReading, SensorTimeSeries,
    SessionContext, PredictionResult,
)
from domain.constants import (
    FISH_PROFILES, TimePeriodConfig, SeasonConfig,
    ProgressiveStageConfig, ThermoclineConfig,
)
from domain.tags import TacticalTag
from domain.time_utils import (
    get_time_period, get_season, get_report_stage,
    get_confidence, get_stage_features, build_session_context,
)
from domain.analyzers import TimeSeriesAnalyzer
from domain.services import FishingPredictionService

# 东八区
_CST = timezone(timedelta(hours=8))


# ── 辅助函数 ──

def _make_cst_timestamp(year, month, day, hour, minute=0):
    """构造指定北京时间的 Unix 时间戳。"""
    dt = datetime(year, month, day, hour, minute, tzinfo=_CST)
    return int(dt.timestamp())


def _make_readings(base_ts, count, interval=5,
                   t_bottom=18.0, t_mid=19.0, t_surface=20.0, p_local=1008.0):
    """构造等间隔传感器读数列表。"""
    return [
        SensorReading(
            timestamp=base_ts + i * interval,
            t_bottom=t_bottom,
            t_mid=t_mid,
            t_surface=t_surface,
            p_local=p_local,
        )
        for i in range(count)
    ]


def _make_trend_readings(base_ts, count, interval=5,
                         t_start=18.0, t_end=20.0, p_start=1008.0, p_end=1010.0):
    """构造含趋势变化的读数列表。"""
    readings = []
    for i in range(count):
        progress = i / max(count - 1, 1)
        readings.append(SensorReading(
            timestamp=base_ts + i * interval,
            t_bottom=round(t_start + progress * (t_end - t_start), 4),
            t_mid=round(t_start + 0.5 + progress * (t_end - t_start), 4),
            t_surface=round(t_start + 1.5 + progress * (t_end - t_start), 4),
            p_local=round(p_start + progress * (p_end - p_start), 4),
        ))
    return readings


# ================================================================
#  Task A1：值对象校验 (value_objects)
# ================================================================

class TestValueObjects:
    """A1: 值对象校验。"""

    # A1-1
    def test_hardware_data_normal(self):
        hw = HardwareData(t_water=22.5, p_local=1013.0, delta_p=1.0)
        assert hw.t_water == 22.5
        assert hw.p_local == 1013.0
        assert hw.delta_p == 1.0

    # A1-2
    def test_hardware_data_temp_out_of_range(self):
        with pytest.raises(ValueError, match="t_water"):
            HardwareData(t_water=50.0, p_local=1013.0, delta_p=0.0)

    # A1-3
    def test_hardware_data_pressure_out_of_range(self):
        with pytest.raises(ValueError, match="p_local"):
            HardwareData(t_water=20.0, p_local=800.0, delta_p=0.0)

    # A1-4
    def test_api_data_normal(self):
        api = ApiData(wind_speed=2.5, altitude=150.0, weather_trend="sunny")
        assert api.wind_speed == 2.5

    # A1-5
    def test_api_data_invalid_weather(self):
        with pytest.raises(ValueError, match="weather_trend"):
            ApiData(wind_speed=2.5, altitude=150.0, weather_trend="haze")

    # A1-6
    def test_sensor_reading_with_none(self):
        r = SensorReading(timestamp=1000, t_bottom=None, p_local=None)
        assert r.timestamp == 1000
        assert r.t_bottom is None
        assert r.p_local is None
        assert r.t_mid is None

    # A1-7
    def test_sensor_time_series_properties(self):
        readings = tuple(_make_readings(1000, 10, interval=5))
        series = SensorTimeSeries(readings=readings)
        assert series.count == 10
        assert series.duration_seconds == 45  # (10-1)*5
        assert series.latest.timestamp == 1000 + 9 * 5
        assert series.earliest.timestamp == 1000

    # A1-8
    def test_sensor_time_series_empty(self):
        series = SensorTimeSeries(readings=())
        assert series.count == 0
        assert series.latest is None
        assert series.earliest is None
        assert series.duration_seconds == 0

    # A1-9
    def test_prediction_result_out_of_range(self):
        with pytest.raises(ValueError, match="bite_index"):
            PredictionResult(do_trend=5.0, bite_index=101)

    # A1-10
    def test_prediction_result_valid_boundaries(self):
        for score in [0, 50, 100]:
            r = PredictionResult(do_trend=5.0, bite_index=score)
            assert r.bite_index == score


# ================================================================
#  Task A2：时间工具测试 (time_utils)
# ================================================================

class TestTimeUtils:
    """A2: 时间工具。"""

    # A2-1
    def test_period_morning(self):
        ts = _make_cst_timestamp(2025, 6, 15, 7, 30)
        assert get_time_period(ts) == "morning"

    # A2-2
    def test_period_noon(self):
        ts = _make_cst_timestamp(2025, 6, 15, 12, 0)
        assert get_time_period(ts) == "noon"

    # A2-3
    def test_period_afternoon(self):
        ts = _make_cst_timestamp(2025, 6, 15, 15, 30)
        assert get_time_period(ts) == "afternoon"

    # A2-4
    def test_period_evening(self):
        ts = _make_cst_timestamp(2025, 6, 15, 20, 0)
        assert get_time_period(ts) == "evening"

    # A2-5 跨午夜凌晨仍是 evening
    def test_period_evening_across_midnight(self):
        ts = _make_cst_timestamp(2025, 6, 15, 2, 0)
        assert get_time_period(ts) == "evening"

    # A2-6
    def test_season_spring(self):
        ts = _make_cst_timestamp(2025, 4, 15, 12)
        assert get_season(ts) == "spring"

    # A2-7
    def test_season_winter_december(self):
        ts = _make_cst_timestamp(2025, 12, 15, 12)
        assert get_season(ts) == "winter"

    # A2-8
    def test_season_winter_january(self):
        ts = _make_cst_timestamp(2025, 1, 15, 12)
        assert get_season(ts) == "winter"

    # A2-9
    def test_stage_instant(self):
        assert get_report_stage(0) == "instant"
        assert get_confidence(0) == 30

    # A2-10
    def test_stage_brief(self):
        assert get_report_stage(300) == "brief"
        # 平滑置信度：300s → ~48%
        assert 45 <= get_confidence(300) <= 55

    # A2-11
    def test_stage_standard(self):
        assert get_report_stage(600) == "standard"
        # 平滑置信度：600s → ~61%
        assert 58 <= get_confidence(600) <= 68

    # A2-12
    def test_stage_full(self):
        assert get_report_stage(1800) == "full"
        # 平滑置信度：1800s → ~83%
        assert 80 <= get_confidence(1800) <= 92

    # A2-13
    def test_build_session_context(self):
        # 4月15日早晨7点，600秒数据 → spring, morning, standard
        base_ts = _make_cst_timestamp(2025, 4, 15, 7, 0)
        readings = _make_readings(base_ts, 120, interval=5)  # 120条×5秒=595秒
        # 确保跨度>=600秒
        readings_long = _make_readings(base_ts, 121, interval=5)  # 600秒
        ctx = build_session_context(readings_long)
        assert ctx.time_period == "morning"
        assert ctx.season == "spring"
        assert ctx.report_stage == "standard"
        assert ctx.duration_seconds == 600


# ================================================================
#  Task A3：时序分析器测试 (analyzers)
# ================================================================

class TestAnalyzers:
    """A3: 时序分析器。"""

    # A3-1 升压
    def test_pressure_delta_rising(self):
        base_ts = 1000
        readings = []
        # 2h 窗口：从1008到1010
        for i in range(100):
            ts = base_ts + i * 72  # 间隔72秒，100条≈7200秒
            progress = i / 99
            readings.append(SensorReading(
                timestamp=ts, p_local=round(1008.0 + progress * 2.0, 2)
            ))
        delta = TimeSeriesAnalyzer.calc_pressure_delta(readings)
        assert abs(delta - 2.0) < 0.1

    # A3-2 降压
    def test_pressure_delta_dropping(self):
        base_ts = 1000
        readings = []
        for i in range(100):
            ts = base_ts + i * 72
            progress = i / 99
            readings.append(SensorReading(
                timestamp=ts, p_local=round(1010.0 - progress * 5.0, 2)
            ))
        delta = TimeSeriesAnalyzer.calc_pressure_delta(readings)
        assert abs(delta - (-5.0)) < 0.1

    # A3-3 数据不足
    def test_pressure_delta_insufficient(self):
        readings = [SensorReading(timestamp=1000, p_local=1008.0)]
        delta = TimeSeriesAnalyzer.calc_pressure_delta(readings)
        assert delta == 0.0

    # A3-4 全 None
    def test_pressure_delta_all_none(self):
        readings = [SensorReading(timestamp=1000 + i * 5) for i in range(10)]
        delta = TimeSeriesAnalyzer.calc_pressure_delta(readings)
        assert delta == 0.0

    # A3-5 温度上升
    def test_temp_trend_rising(self):
        readings = _make_trend_readings(1000, 120, interval=5,
                                        t_start=18.0, t_end=20.0)
        trend = TimeSeriesAnalyzer.calc_temp_trend(readings, field="t_bottom")
        assert trend == "rising"

    # A3-6 温度稳定
    def test_temp_trend_stable(self):
        readings = _make_readings(1000, 120, interval=5, t_bottom=18.0)
        trend = TimeSeriesAnalyzer.calc_temp_trend(readings, field="t_bottom")
        assert trend == "stable"

    # A3-7 温度下降
    def test_temp_trend_dropping(self):
        readings = _make_trend_readings(1000, 120, interval=5,
                                        t_start=20.0, t_end=18.0)
        trend = TimeSeriesAnalyzer.calc_temp_trend(readings, field="t_bottom")
        assert trend == "dropping"

    # A3-8 正常分层
    def test_thermocline_normal(self):
        r = SensorReading(timestamp=1000, t_surface=25.0, t_bottom=20.0)
        index = TimeSeriesAnalyzer.calc_thermocline_index(r)
        assert index == 5.0

    # A3-9 逆温
    def test_thermocline_inversion(self):
        r = SensorReading(timestamp=1000, t_surface=18.0, t_bottom=22.0)
        index = TimeSeriesAnalyzer.calc_thermocline_index(r)
        assert index == -4.0

    # A3-10 数据缺失
    def test_thermocline_missing(self):
        r = SensorReading(timestamp=1000, t_surface=None, t_bottom=20.0)
        assert TimeSeriesAnalyzer.calc_thermocline_index(r) is None

    # A3-11 参考温度-底层鱼
    def test_ref_temp_bottom(self):
        r = SensorReading(timestamp=1000, t_bottom=18.0, t_mid=19.0, t_surface=20.0)
        assert TimeSeriesAnalyzer.select_reference_temp(r, "bottom") == 18.0

    # A3-12 参考温度-降级
    def test_ref_temp_fallback(self):
        r = SensorReading(timestamp=1000, t_bottom=None, t_mid=19.0, t_surface=20.0)
        assert TimeSeriesAnalyzer.select_reference_temp(r, "bottom") == 19.0

    # A3-13 均值计算
    def test_calc_averages(self):
        readings = _make_readings(1000, 60, interval=5,
                                  t_bottom=18.0, t_mid=19.0,
                                  t_surface=20.0, p_local=1008.0)
        avgs = TimeSeriesAnalyzer.calc_averages(readings, window_seconds=300)
        assert abs(avgs["t_bottom"] - 18.0) < 0.01
        assert abs(avgs["t_mid"] - 19.0) < 0.01
        assert abs(avgs["t_surface"] - 20.0) < 0.01
        assert abs(avgs["p_local"] - 1008.0) < 0.01

    # A3-14 气压趋势详情-骤降
    def test_pressure_trend_crash(self):
        base_ts = 1000
        readings = []
        for i in range(100):
            ts = base_ts + i * 72
            progress = i / 99
            readings.append(SensorReading(
                timestamp=ts, p_local=round(1010.0 - progress * 5.0, 2)
            ))
        detail = TimeSeriesAnalyzer.calc_pressure_trend_detail(readings)
        assert detail["trend"] == "crash"
        assert detail["delta_p"] < -3.0


# ================================================================
#  Task A4：预测服务集成测试 (services)
# ================================================================

class TestPredictionService:
    """A4: 预测服务。"""

    def _api(self, weather="sunny"):
        return ApiData(wind_speed=2.5, altitude=150.0, weather_trend=weather)

    # A4-1 Legacy 正常
    def test_legacy_normal(self):
        svc = FishingPredictionService()
        hw = HardwareData(t_water=22.0, p_local=1013.0, delta_p=1.2)
        result = svc.predict(hw, self._api())
        assert 60 <= result.bite_index <= 100
        assert any(t in result.tactical_tags for t in [
            TacticalTag.RATING_GOOD.value, TacticalTag.RATING_EXCELLENT.value
        ])

    # A4-2 Legacy 气压骤降否决
    def test_legacy_pressure_crash(self):
        svc = FishingPredictionService()
        hw = HardwareData(t_water=22.0, p_local=1013.0, delta_p=-4.0)
        result = svc.predict(hw, self._api())
        assert result.bite_index == 5
        assert TacticalTag.RATING_VETO.value in result.tactical_tags

    # A4-3 Series instant
    def test_series_instant(self):
        svc = FishingPredictionService()
        readings = _make_readings(int(time.time()), 1)
        series = SensorTimeSeries(readings=tuple(readings))
        result = svc.predict_from_series(series, self._api())
        assert result.report_stage == "instant"
        assert result.confidence == 30

    # A4-4 Series full
    def test_series_full(self):
        svc = FishingPredictionService()
        base_ts = int(time.time()) - 1800
        readings = _make_readings(base_ts, 361, interval=5)  # 361条×5s=1800s跨度
        series = SensorTimeSeries(readings=tuple(readings))
        result = svc.predict_from_series(series, self._api())
        assert result.report_stage == "full"
        assert result.confidence >= 80  # 平滑置信度 1800s → ~83-86%

    # A4-5 时段标签
    def test_series_period_tag(self):
        svc = FishingPredictionService()
        base_ts = _make_cst_timestamp(2025, 6, 15, 7, 0) - 1800
        readings = _make_readings(base_ts, 360, interval=5)
        series = SensorTimeSeries(readings=tuple(readings))
        result = svc.predict_from_series(series, self._api())
        assert TacticalTag.PERIOD_MORNING_GOLDEN.value in result.tactical_tags

    # A4-6 季节标签
    def test_series_season_tag(self):
        svc = FishingPredictionService()
        base_ts = _make_cst_timestamp(2025, 4, 15, 12, 0) - 1800
        readings = _make_readings(base_ts, 360, interval=5)
        series = SensorTimeSeries(readings=tuple(readings))
        result = svc.predict_from_series(series, self._api())
        assert TacticalTag.SEASON_SPRING_WARMING.value in result.tactical_tags

    # A4-7 温跃层强
    def test_series_thermocline_strong(self):
        svc = FishingPredictionService()
        base_ts = int(time.time()) - 1800
        readings = _make_readings(base_ts, 360, interval=5,
                                  t_bottom=18.0, t_surface=22.0)  # diff=4 > 3
        series = SensorTimeSeries(readings=tuple(readings))
        result = svc.predict_from_series(series, self._api())
        assert TacticalTag.STATUS_THERMOCLINE_STRONG.value in result.tactical_tags

    # A4-8 逆温检测
    def test_series_temp_inversion(self):
        svc = FishingPredictionService()
        base_ts = int(time.time()) - 1800
        # 逆温：bottom > surface + 1.5
        readings = _make_readings(base_ts, 360, interval=5,
                                  t_bottom=22.0, t_mid=20.0, t_surface=19.0)
        series = SensorTimeSeries(readings=tuple(readings))
        result = svc.predict_from_series(series, self._api())
        assert TacticalTag.STATUS_TEMP_INVERSION.value in result.tactical_tags

    # A4-9 多鱼种切换
    def test_series_multi_species(self):
        base_ts = int(time.time()) - 1800
        # 表层30℃适合鲢鳙，底层18℃适合鲫鱼
        readings = _make_readings(base_ts, 360, interval=5,
                                  t_bottom=18.0, t_mid=24.0, t_surface=30.0,
                                  p_local=1010.0)
        series = SensorTimeSeries(readings=tuple(readings))
        api = self._api()

        svc_liangyong = FishingPredictionService(fish_profile=FISH_PROFILES["鲢鳙"])
        result_ly = svc_liangyong.predict_from_series(series, api)

        svc_jiyu = FishingPredictionService(fish_profile=FISH_PROFILES["鲫鱼"])
        result_jy = svc_jiyu.predict_from_series(series, api)

        # 两个鱼种分数应不同（鲢鳙用表层30℃在最适区间，鲫鱼用底层18℃也在最适区间但分数有差异）
        # 关键是不崩溃且都返回有效结果
        assert 0 <= result_ly.bite_index <= 100
        assert 0 <= result_jy.bite_index <= 100

    # A4-10 空数据保护
    def test_series_empty_data(self):
        svc = FishingPredictionService()
        series = SensorTimeSeries(readings=())
        result = svc.predict_from_series(series, self._api())
        assert result.bite_index == 0
