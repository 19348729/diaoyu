"""
时序数据分析器 (Time Series Analyzers)
========================================
独立的时序数据分析逻辑，供核心预测服务调用。
从传感器时序数据中提取气压变化率、温度趋势、温跃层指数等聚合指标。
"""
from __future__ import annotations

from typing import List, Optional

from .value_objects import SensorReading


class TimeSeriesAnalyzer:
    """传感器时序数据分析器。

    所有方法均为静态方法，无状态，方便测试和复用。
    """

    @staticmethod
    def calc_pressure_delta(
        readings: List[SensorReading],
        window_seconds: int = 7200,
    ) -> float:
        """计算指定时间窗口内的气压变化率。

        从最新读数往前找 window_seconds（默认2小时）前的最近一条有效气压读数，
        计算 delta_p = latest_p - earliest_p。

        Args:
            readings:       按时间升序排列的读数列表
            window_seconds: 回看窗口长度（秒），默认 7200（2小时）

        Returns:
            气压变化量（hPa），正值=升压，负值=降压。
            数据不足时返回 0.0。
        """
        if not readings:
            return 0.0

        # 找到最新的有效气压
        latest_p = None
        latest_ts = 0
        for r in reversed(readings):
            if r.p_local is not None:
                latest_p = r.p_local
                latest_ts = r.timestamp
                break

        if latest_p is None:
            return 0.0

        # 向前查找窗口起点附近的有效气压
        target_ts = latest_ts - window_seconds
        earliest_p = None
        min_distance = float('inf')

        for r in readings:
            if r.p_local is not None and r.timestamp <= latest_ts:
                distance = abs(r.timestamp - target_ts)
                if distance < min_distance:
                    min_distance = distance
                    earliest_p = r.p_local

        if earliest_p is None or earliest_p == latest_p:
            return 0.0

        return round(latest_p - earliest_p, 2)

    @staticmethod
    def calc_temp_trend(
        readings: List[SensorReading],
        field: str = "t_bottom",
        window_seconds: int = 600,
    ) -> str:
        """计算指定温度字段的变化趋势。

        使用最近 window_seconds 窗口内的数据，通过简单线性回归斜率判断。

        Args:
            readings:       按时间升序排列的读数列表
            field:          温度字段名 ("t_bottom" / "t_mid" / "t_surface")
            window_seconds: 分析窗口（秒），默认 600（10分钟）

        Returns:
            "rising" / "dropping" / "stable"
        """
        if len(readings) < 2:
            return "stable"

        latest_ts = readings[-1].timestamp
        cutoff_ts = latest_ts - window_seconds

        # 收集窗口内有效数据点
        points = []
        for r in readings:
            if r.timestamp >= cutoff_ts:
                val = getattr(r, field, None)
                if val is not None:
                    points.append((r.timestamp, val))

        if len(points) < 2:
            return "stable"

        # 简单线性回归斜率
        n = len(points)
        sum_t = sum(p[0] for p in points)
        sum_v = sum(p[1] for p in points)
        sum_tv = sum(p[0] * p[1] for p in points)
        sum_t2 = sum(p[0] ** 2 for p in points)

        denominator = n * sum_t2 - sum_t ** 2
        if denominator == 0:
            return "stable"

        slope = (n * sum_tv - sum_t * sum_v) / denominator

        # 斜率阈值：每秒变化 0.001℃ 以上视为有趋势
        # 即每分钟 0.06℃，每10分钟 0.6℃
        if slope > 0.001:
            return "rising"
        elif slope < -0.001:
            return "dropping"
        else:
            return "stable"

    @staticmethod
    def calc_thermocline_index(reading: SensorReading) -> Optional[float]:
        """计算温跃层强度指数。

        温跃层强度 = t_surface - t_bottom
        正值表示正常分层（表暖底冷），负值表示逆温。

        Args:
            reading: 单条传感器读数

        Returns:
            温跃层指数（℃），数据不完整时返回 None
        """
        if reading.t_surface is None or reading.t_bottom is None:
            return None
        return round(reading.t_surface - reading.t_bottom, 2)

    @staticmethod
    def calc_averages(
        readings: List[SensorReading],
        window_seconds: int = 300,
    ) -> dict:
        """计算最近时间窗口内各字段的均值。

        Args:
            readings:       按时间升序排列的读数列表
            window_seconds: 均值窗口（秒），默认 300（5分钟）

        Returns:
            {"t_bottom": float|None, "t_mid": float|None,
             "t_surface": float|None, "p_local": float|None}
        """
        if not readings:
            return {"t_bottom": None, "t_mid": None, "t_surface": None, "p_local": None}

        latest_ts = readings[-1].timestamp
        cutoff_ts = latest_ts - window_seconds

        sums = {"t_bottom": 0.0, "t_mid": 0.0, "t_surface": 0.0, "p_local": 0.0}
        counts = {"t_bottom": 0, "t_mid": 0, "t_surface": 0, "p_local": 0}

        for r in readings:
            if r.timestamp >= cutoff_ts:
                for field in sums:
                    val = getattr(r, field, None)
                    if val is not None:
                        sums[field] += val
                        counts[field] += 1

        result = {}
        for field in sums:
            if counts[field] > 0:
                result[field] = round(sums[field] / counts[field], 2)
            else:
                result[field] = None

        return result

    @staticmethod
    def select_reference_temp(
        reading: SensorReading,
        water_layer: str = "bottom",
    ) -> Optional[float]:
        """根据鱼种栖息水层选择参考水温。

        Args:
            reading:     单条传感器读数
            water_layer: 鱼种栖息水层 ("bottom" / "mid" / "top")

        Returns:
            参考水温值，若对应层无数据则尝试降级到其他层
        """
        layer_map = {
            "bottom": [reading.t_bottom, reading.t_mid, reading.t_surface],
            "mid":    [reading.t_mid, reading.t_bottom, reading.t_surface],
            "top":    [reading.t_surface, reading.t_mid, reading.t_bottom],
        }

        candidates = layer_map.get(water_layer, layer_map["bottom"])
        for temp in candidates:
            if temp is not None:
                return temp

        return None

    @staticmethod
    def calc_pressure_trend_detail(
        readings: List[SensorReading],
        window_seconds: int = 7200,
    ) -> dict:
        """计算气压趋势的详细信息。

        Returns:
            {
                "delta_p": float,
                "trend": "rising" / "dropping" / "stable" / "crash",
                "rate_per_hour": float  # 每小时变化率
            }
        """
        delta_p = TimeSeriesAnalyzer.calc_pressure_delta(readings, window_seconds)

        if delta_p <= -3.0:
            trend = "crash"
        elif delta_p > 0.5:
            trend = "rising"
        elif delta_p < -0.5:
            trend = "dropping"
        else:
            trend = "stable"

        # 计算实际数据跨度
        valid_readings = [r for r in readings if r.p_local is not None]
        if len(valid_readings) >= 2:
            span_hours = (valid_readings[-1].timestamp - valid_readings[0].timestamp) / 3600
            rate_per_hour = delta_p / span_hours if span_hours > 0 else 0.0
        else:
            rate_per_hour = 0.0

        return {
            "delta_p": delta_p,
            "trend": trend,
            "rate_per_hour": round(rate_per_hour, 3),
        }
