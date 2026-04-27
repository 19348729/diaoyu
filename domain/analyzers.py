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

    @staticmethod
    def calc_pressure_multi_window(
        readings: List[SensorReading],
        windows: tuple = (900, 1800, 3600, 7200),
    ) -> dict:
        """多窗口气压变化分析。

        同时计算 15min/30min/1h/2h 窗口的气压变化，
        捕获不同时间尺度的气压动态。

        Args:
            readings: 按时间升序排列的读数列表
            windows:  分析窗口列表（秒）

        Returns:
            {"delta_15min": float, "delta_30min": float, ..., "volatility_1h": float}
        """
        result = {}
        window_names = {900: "15min", 1800: "30min", 3600: "1h", 7200: "2h"}

        for w in windows:
            key = window_names.get(w, f"{w}s")
            result[f"delta_{key}"] = TimeSeriesAnalyzer.calc_pressure_delta(readings, w)

        # 计算过去 1 小时的气压波动标准差
        result["volatility_1h"] = TimeSeriesAnalyzer.calc_pressure_volatility(
            readings, 3600
        )

        return result

    @staticmethod
    def calc_pressure_volatility(
        readings: List[SensorReading],
        window_seconds: int = 3600,
    ) -> float:
        """计算指定窗口内气压值的标准差（波动率）。

        Args:
            readings:       按时间升序排列的读数列表
            window_seconds: 分析窗口（秒），默认 1 小时

        Returns:
            标准差 (hPa)，数据不足时返回 0.0
        """
        if not readings:
            return 0.0

        latest_ts = readings[-1].timestamp
        cutoff_ts = latest_ts - window_seconds

        values = [
            r.p_local for r in readings
            if r.p_local is not None and r.timestamp >= cutoff_ts
        ]

        if len(values) < 2:
            return 0.0

        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        return round(variance ** 0.5, 3)

    @staticmethod
    def calc_temp_trend_detail(
        readings: List[SensorReading],
        field: str = "t_bottom",
        window_seconds: int = 600,
    ) -> dict:
        """计算温度变化的详细特征（含速率量化）。

        Args:
            readings:       按时间升序排列的读数列表
            field:          温度字段名
            window_seconds: 分析窗口（秒）

        Returns:
            {
                "direction": "rising"/"dropping"/"stable",
                "rate_per_hour": float,  # ℃/h
                "is_rapid": bool,        # 是否快速变化（>1.5℃/h）
            }
        """
        direction = TimeSeriesAnalyzer.calc_temp_trend(readings, field, window_seconds)

        # 计算精确速率
        rate_per_hour = 0.0
        if len(readings) >= 2:
            latest_ts = readings[-1].timestamp
            cutoff_ts = latest_ts - window_seconds

            points = []
            for r in readings:
                if r.timestamp >= cutoff_ts:
                    val = getattr(r, field, None)
                    if val is not None:
                        points.append((r.timestamp, val))

            if len(points) >= 2:
                span_hours = (points[-1][0] - points[0][0]) / 3600
                if span_hours > 0:
                    delta = points[-1][1] - points[0][1]
                    rate_per_hour = delta / span_hours

        is_rapid = abs(rate_per_hour) > 1.5

        return {
            "direction": direction,
            "rate_per_hour": round(rate_per_hour, 3),
            "is_rapid": is_rapid,
        }

    @staticmethod
    def analyze_thermal_profile(
        readings: List[SensorReading],
        window_seconds: int = 600,
    ) -> dict:
        """三层水温空间分布综合分析。

        分析表层/中层/底层温度的空间关系和时间趋势差异。

        Args:
            readings:       按时间升序排列的读数列表
            window_seconds: 分析窗口（秒）

        Returns:
            {
                "stratification": float|None,     # 表底温差 (℃)
                "mixing_state": str,               # well_mixed/weakly/strongly_stratified
                "surface_rate": float,             # 表层温度变化率 ℃/h
                "bottom_rate": float,              # 底层温度变化率 ℃/h
                "layers_diverging": bool,          # 各层趋势是否分化
            }
        """
        latest = readings[-1] if readings else None

        # 分层强度
        stratification = None
        mixing_state = "unknown"
        if latest and latest.t_surface is not None and latest.t_bottom is not None:
            stratification = round(latest.t_surface - latest.t_bottom, 2)
            abs_strat = abs(stratification)
            if abs_strat < 1.0:
                mixing_state = "well_mixed"
            elif abs_strat < 3.0:
                mixing_state = "weakly_stratified"
            else:
                mixing_state = "strongly_stratified"

        # 各层变化速率
        surface_detail = TimeSeriesAnalyzer.calc_temp_trend_detail(
            readings, "t_surface", window_seconds
        )
        bottom_detail = TimeSeriesAnalyzer.calc_temp_trend_detail(
            readings, "t_bottom", window_seconds
        )

        surface_rate = surface_detail["rate_per_hour"]
        bottom_rate = bottom_detail["rate_per_hour"]

        # 趋势分化判断：一层升温另一层降温，或速率差异大于 1℃/h
        layers_diverging = False
        if surface_rate * bottom_rate < 0:
            layers_diverging = True  # 一升一降
        elif abs(surface_rate - bottom_rate) > 1.0:
            layers_diverging = True  # 速率差异大

        return {
            "stratification": stratification,
            "mixing_state": mixing_state,
            "surface_rate": surface_rate,
            "bottom_rate": bottom_rate,
            "layers_diverging": layers_diverging,
        }

