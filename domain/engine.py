"""
变率引擎 (Physics Engine)
"""
from typing import List
from .value_objects import SensorTimeSeries
from .analyzers import TimeSeriesAnalyzer
from .tags import TacticalTag

class FishingEngine:
    """纯物理变率引擎，输出特征指标与物理标签。
    这里抽取了 V1 中算物理变率的纯净逻辑，与 LLM 文案解耦。
    """
    def __init__(self):
        pass

    def evaluate(self, series: SensorTimeSeries) -> dict:
        tags = []
        metrics = {}
        
        if not series or series.count == 0:
            return {"tags": tags, "metrics": metrics}
            
        readings = list(series.readings)
        
        # 1. 气压分析
        pressure_detail = TimeSeriesAnalyzer.calc_pressure_trend_detail(readings)
        metrics["delta_p_2h"] = pressure_detail["delta_p"]
        trend = pressure_detail["trend"]
        if trend == "crash":
            tags.append(TacticalTag.STATUS_PRESSURE_CRASH.value)
        elif trend == "dropping":
            tags.append(TacticalTag.STATUS_PRESSURE_DROPPING.value)
        elif trend == "rising":
            tags.append(TacticalTag.STATUS_PRESSURE_RISING.value)
        else:
            tags.append(TacticalTag.STATUS_PRESSURE_STABLE.value)
            
        # 2. 三层水温分析
        thermal = TimeSeriesAnalyzer.analyze_thermal_profile(readings)
        if thermal["stratification"] is not None:
            metrics["thermocline"] = thermal["stratification"]
            if thermal["mixing_state"] == "strongly_stratified":
                tags.append(TacticalTag.STATUS_THERMOCLINE_STRONG.value)
            elif thermal["mixing_state"] == "weakly_stratified":
                tags.append(TacticalTag.STATUS_THERMOCLINE_WEAK.value)
                
            if thermal["layers_diverging"]:
                tags.append(TacticalTag.THERMAL_LAYERS_DIVERGING.value)
                
        # 3. 基础均值记录
        averages = TimeSeriesAnalyzer.calc_averages(readings)
        t_water = averages.get("t_bottom") or averages.get("t_surface")
        if t_water is not None:
            metrics["t_water_avg"] = t_water
        if averages["p_local"] is not None:
            metrics["p_local_avg"] = averages["p_local"]

        return {
            "tags": tags,
            "metrics": metrics
        }
