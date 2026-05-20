"""
Unit tests for the digital tackle box equipment matching logic in domain services.
"""
import sys
import os
import pytest
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from domain.value_objects import ApiData, SensorReading, SensorTimeSeries
from domain.constants import FISH_PROFILES
from domain.services import FishingPredictionService




def _make_series(timestamp, t_bottom=20.0, p_local=1013.0):
    reading = SensorReading(
        timestamp=timestamp,
        t_bottom=t_bottom,
        t_mid=t_bottom + 1.0,
        t_surface=t_bottom + 2.0,
        p_local=p_local
    )
    return SensorTimeSeries(readings=(reading,))


class TestEquipmentMatching:
    """Test suite for validating smart equipment recommendations against digital tackle box inventory."""

    @pytest.fixture
    def api_normal(self):
        return ApiData(wind_speed=2.0, altitude=150.0, weather_trend="sunny")

    @pytest.fixture
    def api_windy(self):
        return ApiData(wind_speed=5.0, altitude=150.0, weather_trend="sunny")

    @pytest.fixture
    def sample_inventory(self):
        return {
            "rods": [
                {"id": "rod_short_stiff", "brand": "BrandA", "name": "ShortStiff竿", "length": 3.6, "action": "19调", "type": "台钓竿"},
                {"id": "rod_long_stiff", "brand": "BrandB", "name": "LongStiff竿", "length": 5.4, "action": "19调", "type": "台钓竿"},
                {"id": "rod_long_soft", "brand": "BrandC", "name": "LongSoft竿", "length": 5.4, "action": "37调", "type": "台钓竿"},
                {"id": "rod_short_soft", "brand": "BrandD", "name": "ShortSoft竿", "length": 4.5, "action": "37调", "type": "台钓竿"}
            ],
            "mainLines": [
                {"id": "ml_0.8", "size": 0.8, "length": 50},
                {"id": "ml_1.2", "size": 1.2, "length": 50},
                {"id": "ml_2.5", "size": 2.5, "length": 50},
                {"id": "ml_4.0", "size": 4.0, "length": 50}
            ],
            "subLineHooks": [
                {"id": "sl_0.3", "lineSize": 0.3, "hookType": "袖钩", "hookSize": "2号"},
                {"id": "sl_0.6", "lineSize": 0.6, "hookType": "袖钩", "hookSize": "4号"},
                {"id": "sl_1.5", "lineSize": 1.5, "hookType": "伊势尼", "hookSize": "5号"},
                {"id": "sl_3.0", "lineSize": 3.0, "hookType": "伊势尼", "hookSize": "7号"}
            ],
            "floats": [
                {"id": "fl_light", "name": "LightFloat", "material": "巴尔杉木", "shape": "长身", "lead": 1.2, "tail_type": "细尾"},
                {"id": "fl_heavy", "name": "HeavyFloat", "material": "羽毛", "shape": "枣核", "lead": 3.0, "tail_type": "粗尾"}
            ],
            "baits": [
                {"id": "bait_lanji", "category": "商品饵", "brand": "老鬼", "name": "野战蓝鲫", "flavor": "香腥", "targetFish": "鲫鱼"},
                {"id": "bait_918", "category": "商品饵", "brand": "老鬼", "name": "九一八野战篇", "flavor": "麦香", "targetFish": "鲫鱼"},
                {"id": "bait_sugong", "category": "商品饵", "brand": "老鬼", "name": "速攻2号", "flavor": "奶香", "targetFish": "鲫鱼"},
                {"id": "bait_carp_sweet", "category": "商品饵", "brand": "化氏", "name": "超诱", "flavor": "麸香", "targetFish": "鲤鱼"}
            ]
        }

    def test_empty_inventory_fallback(self, api_normal):
        """1. Verify that prediction falls back to ideal suggestions with warning message when inventory is empty."""
        svc = FishingPredictionService(fish_profile=FISH_PROFILES["鲫鱼"])
        series = _make_series(1716166400, t_bottom=20.0)

        # Empty inventory dictionary
        res = svc.predict_from_series(series, api_normal, user_inventory={})
        advice = res.tactical_advice["equipment_advice"]

        assert advice["rod"]["matching_id"] is None
        assert "数字钓箱暂无最适配的鱼竿" in advice["rod"]["reason"]
        assert "推荐使用" in advice["rod"]["recommendation"]

        assert advice["main_line"]["matching_id"] is None
        assert "数字钓箱暂无适配主线" in advice["main_line"]["reason"]

        assert advice["sub_line_hook"]["matching_id"] is None
        assert "数字钓箱暂无适配子线" in advice["sub_line_hook"]["reason"]

        assert advice["float"]["matching_id"] is None
        assert "未在钓箱找到最优浮漂" in advice["float"]["reason"]

        assert advice["bait"]["matching_id"] is None
        assert "数字钓箱暂无适配饵料" in advice["bait"]["reason"]

    def test_windy_weather_matching(self, api_windy, sample_inventory):
        """2. Verify shorter, stiffer rods (<= 4.5m) and heavier floats (>= 2.5g) are matched under windy weather (>3.33 m/s)."""
        svc = FishingPredictionService(fish_profile=FISH_PROFILES["鲤鱼"])
        series = _make_series(1716166400, t_bottom=20.0)

        res = svc.predict_from_series(series, api_windy, user_inventory=sample_inventory)
        advice = res.tactical_advice["equipment_advice"]

        # Check rod: Should match rod_short_stiff because windy weather prioritizes length <= 4.5 and stiff action
        assert advice["rod"]["matching_id"] == "rod_short_stiff"
        assert "大风" in advice["rod"]["reason"]

        # Check float: Should match fl_heavy because windy weather needs lead >= 2.5
        assert advice["float"]["matching_id"] == "fl_heavy"
        assert "大风" in advice["float"]["reason"]

    def test_cold_weather_line_override_big_fish(self, api_normal, sample_inventory):
        """3. Verify cold weather line downscaling override (water/air temp <12℃) for big fish (鲤鱼)."""
        svc = FishingPredictionService(fish_profile=FISH_PROFILES["鲤鱼"])
        
        # WARM weather: Should match thicker lines (e.g. 4.0 main, 3.0 sub)
        series_warm = _make_series(1716166400, t_bottom=20.0)
        res_warm = svc.predict_from_series(series_warm, api_normal, user_inventory=sample_inventory)
        advice_warm = res_warm.tactical_advice["equipment_advice"]
        assert advice_warm["main_line"]["matching_id"] == "ml_4.0"
        assert advice_warm["sub_line_hook"]["matching_id"] == "sl_3.0"

        # COLD weather: Should override and downscale (e.g. 2.5 main, 1.5 sub)
        series_cold = _make_series(1716166400, t_bottom=8.0)
        res_cold = svc.predict_from_series(series_cold, api_normal, user_inventory=sample_inventory)
        advice_cold = res_cold.tactical_advice["equipment_advice"]
        assert advice_cold["main_line"]["matching_id"] == "ml_2.5"
        assert advice_cold["sub_line_hook"]["matching_id"] == "sl_1.5"
        assert "轻口低温期" in advice_cold["main_line"]["reason"]
        assert "极寒降温" in advice_cold["sub_line_hook"]["reason"]

    def test_cold_weather_line_override_small_fish(self, api_normal, sample_inventory):
        """3. Verify cold weather line downscaling override for small fish (鲫鱼)."""
        svc = FishingPredictionService(fish_profile=FISH_PROFILES["鲫鱼"])

        # WARM weather: Should match normal lines (e.g. 1.2 main, 0.6 sub)
        series_warm = _make_series(1716166400, t_bottom=20.0)
        res_warm = svc.predict_from_series(series_warm, api_normal, user_inventory=sample_inventory)
        advice_warm = res_warm.tactical_advice["equipment_advice"]
        assert advice_warm["main_line"]["matching_id"] == "ml_1.2"
        assert advice_warm["sub_line_hook"]["matching_id"] == "sl_0.6"

        # COLD weather: Should override and downscale (e.g. 0.8 main, 0.3 sub)
        series_cold = _make_series(1716166400, t_bottom=8.0)
        res_cold = svc.predict_from_series(series_cold, api_normal, user_inventory=sample_inventory)
        advice_cold = res_cold.tactical_advice["equipment_advice"]
        assert advice_cold["main_line"]["matching_id"] == "ml_0.8"
        assert advice_cold["sub_line_hook"]["matching_id"] == "sl_0.3"

    def test_old_three_bait_mix_ratios_cold(self, api_normal, sample_inventory):
        """4. Verify "老三样" bait mix ratio under cold conditions (<15℃)."""
        svc = FishingPredictionService(fish_profile=FISH_PROFILES["鲫鱼"])
        series_cold = _make_series(1716166400, t_bottom=10.0) # cold water
        
        res = svc.predict_from_series(series_cold, api_normal, user_inventory=sample_inventory)
        advice = res.tactical_advice["equipment_advice"]
        
        assert advice["bait"]["matching_id"] in ("bait_lanji", "bait_918", "bait_sugong")
        assert "老三样" in advice["bait"]["recommendation"]
        assert "40%" in advice["bait"]["recommendation"]
        assert "低温季节" in advice["bait"]["reason"]

    def test_old_three_bait_mix_ratios_warm(self, api_normal, sample_inventory):
        """4. Verify "老三样" bait mix ratio under warm conditions (>25℃)."""
        # Let's override season to summer
        svc = FishingPredictionService(fish_profile=FISH_PROFILES["鲫鱼"])
        series_warm = _make_series(1716166400, t_bottom=28.0)
        
        res = svc.predict_from_series(series_warm, api_normal, user_inventory=sample_inventory)
        advice = res.tactical_advice["equipment_advice"]
        
        assert advice["bait"]["matching_id"] in ("bait_lanji", "bait_918", "bait_sugong")
        assert "老三样" in advice["bait"]["recommendation"]
        assert "60%" in advice["bait"]["recommendation"]
        assert "气温偏高" in advice["bait"]["reason"]
