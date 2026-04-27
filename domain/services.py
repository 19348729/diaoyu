"""领域服务层 (Domain Services)
============================
封装跨值对象的纯业务逻辑。高内聚、低耦合。
纯面向对象，不依赖任何数据库或外部框架，方便被 Django Service 层直接调用。
"""
import math
from typing import List, Optional, Tuple

from .value_objects import (
    HardwareData, ApiData, PredictionResult,
    SensorReading, SensorTimeSeries, SessionContext,
)
from .constants import (
    DissolvedOxygenConfig, FishSpeciesProfile, BiteIndexConfig,
    TimePeriodConfig, SeasonConfig, ProgressiveStageConfig, ThermoclineConfig,
    SolunarConfig, PressureAnalysisConfig, WindDirectionConfig, HumidityConfig,
    interpolate_do_saturation,
)
from .tags import TacticalTag
from .analyzers import TimeSeriesAnalyzer
from .solunar import calc_moon_phase, calc_solunar_rating
from .time_utils import (
    get_time_period, get_season, get_report_stage,
    get_confidence, get_stage_features, build_session_context,
)


class FishingPredictionService:
    """AI 铓鱼多因子融合预测核心服务类。
    
    支持两种预测模式：
      1. predict()            ─ 单帧快照模式（向后兼容）
      2. predict_from_series() ─ 时序数据模式（新版完整功能）
    """

    def __init__(
        self,
        do_config: DissolvedOxygenConfig = None,
        fish_profile: FishSpeciesProfile = None,
        bite_config: BiteIndexConfig = None,
        period_config: TimePeriodConfig = None,
        season_config: SeasonConfig = None,
        stage_config: ProgressiveStageConfig = None,
        thermocline_config: ThermoclineConfig = None,
        solunar_config: SolunarConfig = None,
        pressure_analysis_config: PressureAnalysisConfig = None,
        wind_direction_config: WindDirectionConfig = None,
        humidity_config: HumidityConfig = None,
    ):
        """支持依赖注入配置，方便针对不同水域/鱼种动态实例化。"""
        self.do_config = do_config or DissolvedOxygenConfig()
        self.fish_profile = fish_profile or FishSpeciesProfile()
        self.bite_config = bite_config or BiteIndexConfig()
        self.period_config = period_config or TimePeriodConfig()
        self.season_config = season_config or SeasonConfig()
        self.stage_config = stage_config or ProgressiveStageConfig()
        self.thermocline_config = thermocline_config or ThermoclineConfig()
        self.solunar_config = solunar_config or SolunarConfig()
        self.pressure_config = pressure_analysis_config or PressureAnalysisConfig()
        self.wind_config = wind_direction_config or WindDirectionConfig()
        self.humidity_config = humidity_config or HumidityConfig()
        self._analyzer = TimeSeriesAnalyzer()

    def predict(self, hardware: HardwareData, api: ApiData) -> PredictionResult:
        """单帧快照预测（向后兼容接口）。
        
        保留原始接口，内部复用基础评分逻辑。
        """
        tags: List[str] = []

        # 1. 估算虚拟溶解氧
        do_est = self._calculate_do(hardware, api, tags)

        # 2. 根据水温计算基准分
        base_score = self._calc_temp_base_score(hardware.t_water, tags)

        # 3. 气压动态加权与一票否决判定
        pressure_modifier, is_veto = self._calc_pressure_modifier(hardware.delta_p, tags)

        # 如果触发一票否决（如气压骤降），直接走短路逻辑返回极低分
        if is_veto:
            tags.append(TacticalTag.RATING_VETO.value)
            return PredictionResult(
                do_trend=round(do_est, 2),
                bite_index=self.bite_config.pressure_crash_score,
                tactical_tags=tags
            )

        # 4. 溶解氧加权
        do_modifier = self._calc_do_modifier(do_est, tags)

        # 5. 短临天气加权
        weather_modifier = self._calc_weather_modifier(api.weather_trend, tags)

        # 6. 计算总分并限制在 [0, 100] 范围内
        final_score = base_score + pressure_modifier + do_modifier + weather_modifier
        final_score = max(0, min(100, int(final_score)))

        # 7. 根据最终得分补充综合评级标签
        self._add_rating_tag(final_score, tags)

        return PredictionResult(
            do_trend=round(do_est, 2),
            bite_index=final_score,
            tactical_tags=tags
        )

    def _calculate_do(self, hardware: HardwareData, api: ApiData, tags: List[str]) -> float:
        """虚拟溶解氧估算模块（查表插值法）。

        基于 Benson & Krause 标准查表：
          1. 根据水温查表得到标准气压下的饱和溶解氧
          2. 乘以气压修正系数 (P_actual / P_standard)
          3. 乘以风力增氧系数（微风促进气体交换，实际 DO 趋近饱和值）
        """
        return self._calculate_do_from_values(
            hardware.p_local, hardware.t_water, api, tags
        )

    def _calc_temp_base_score(self, t_water: float, tags: List[str]) -> int:
        """根据水温落在目标鱼种的适宜区间计算基准分。"""
        opt_min, opt_max = self.fish_profile.optimal_temp
        tol_min, tol_max = self.fish_profile.tolerable_temp

        if opt_min <= t_water <= opt_max:
            tags.append(TacticalTag.STATUS_TEMP_OPTIMAL.value)
            return self.fish_profile.base_score_optimal
        elif tol_min <= t_water <= tol_max:
            tags.append(TacticalTag.STATUS_TEMP_TOLERABLE.value)
            return self.fish_profile.base_score_tolerable
        else:
            if t_water > tol_max:
                tags.append(TacticalTag.STATUS_TEMP_EXTREME_HOT.value)
            else:
                tags.append(TacticalTag.STATUS_TEMP_EXTREME_COLD.value)
            return self.fish_profile.base_score_outside

    def _calc_pressure_modifier(self, delta_p: float, tags: List[str]) -> Tuple[int, bool]:
        """气压动态加权模块。返回 (加减分数, 是否一票否决)。"""
        if delta_p <= self.bite_config.pressure_crash_threshold:
            # 气压骤降，触发一票否决
            tags.append(TacticalTag.STATUS_PRESSURE_CRASH.value)
            return 0, True
            
        if delta_p > 0:
            # 气压回升加分（可根据增幅线性计算，此处使用简化封顶逻辑）
            bonus = min(int(delta_p * 5), self.bite_config.pressure_rise_bonus)
            tags.append(TacticalTag.STATUS_PRESSURE_RISING.value)
            return bonus, False
            
        if delta_p < 0:
            # 气压缓降扣分
            penalty = min(int(abs(delta_p) * 5), self.bite_config.pressure_drop_penalty)
            tags.append(TacticalTag.STATUS_PRESSURE_DROPPING.value)
            return -penalty, False
            
        # delta_p == 0
        tags.append(TacticalTag.STATUS_PRESSURE_STABLE.value)
        return 0, False

    def _calc_do_modifier(self, do_est: float, tags: List[str]) -> int:
        """结合虚拟溶解氧估算值，触发加/扣分。"""
        if do_est > self.bite_config.do_danger_line:
            tags.append(TacticalTag.STATUS_DO_HEALTHY.value)
            return self.bite_config.do_bonus
        else:
            tags.append(TacticalTag.STATUS_DO_DANGER.value)
            return -self.bite_config.do_penalty

    def _calc_weather_modifier(self, weather_trend: str, tags: List[str]) -> int:
        """天气加权模块。"""
        score = self.bite_config.weather_bonus_map.get(weather_trend, 0)
        if score > 0:
            tags.append(TacticalTag.STATUS_WEATHER_FAVORABLE.value)
        elif score < 0:
            tags.append(TacticalTag.STATUS_WEATHER_ADVERSE.value)
        return score

    def _add_rating_tag(self, score: int, tags: List[str]) -> None:
        """根据最终得分附加综合评级标签。"""
        if score >= 80:
            tags.append(TacticalTag.RATING_EXCELLENT.value)
        elif score >= 60:
            tags.append(TacticalTag.RATING_GOOD.value)
        elif score >= 40:
            tags.append(TacticalTag.RATING_FAIR.value)
        else:
            tags.append(TacticalTag.RATING_POOR.value)

    # ================================================================
    #  新版时序预测接口
    # ================================================================

    def predict_from_series(
        self,
        series: SensorTimeSeries,
        api: ApiData,
        session: SessionContext = None,
    ) -> PredictionResult:
        """基于时序数据的完整预测流程。

        新版主入口，支持：
          - 三层水温（根据鱼种水层选择参考温度）
          - 自动计算气压变化率 delta_p
          - 四时段加权
          - 四季节修正
          - 温跃层/分层分析
          - 渐进式报告阶段

        Args:
            series:  传感器时序数据
            api:     云端气象数据
            session: 会话上下文（可省略，自动构建）

        Returns:
            PredictionResult 含报告阶段、置信度、时段建议、季节备注
        """
        tags: List[str] = []
        readings = list(series.readings)

        # ── 自动构建会话上下文 ──
        if session is None:
            session = build_session_context(
                readings, self.period_config, self.season_config, self.stage_config
            )

        # ── 确定报告阶段和启用特征 ──
        report_stage = session.report_stage
        confidence = get_confidence(session.duration_seconds, self.stage_config)
        features = get_stage_features(session.duration_seconds, self.stage_config)

        # 添加阶段标签
        stage_tag_map = {
            "instant": TacticalTag.STAGE_INSTANT,
            "brief": TacticalTag.STAGE_BRIEF,
            "standard": TacticalTag.STAGE_STANDARD,
            "full": TacticalTag.STAGE_FULL,
        }
        if report_stage in stage_tag_map:
            tags.append(stage_tag_map[report_stage].value)

        # ── 1. 从时序数据提取核心指标 ──
        latest = series.latest
        if latest is None:
            return PredictionResult(
                do_trend=0.0, bite_index=0, tactical_tags=tags,
                report_stage=report_stage, confidence=confidence,
            )

        # 根据鱼种水层选择参考水温
        ref_temp = self._analyzer.select_reference_temp(
            latest, self.fish_profile.water_layer
        )
        if ref_temp is None:
            ref_temp = 20.0  # 安全默认值

        # 气压快照
        p_local = latest.p_local if latest.p_local is not None else 1013.0

        # 自动计算 delta_p
        if "pressure_trend" in features and len(readings) >= 2:
            pressure_detail = self._analyzer.calc_pressure_trend_detail(readings)
            delta_p = pressure_detail["delta_p"]
        else:
            delta_p = 0.0  # 数据不足时视为稳定

        # ── 2. 基准分（水温） ──
        base_score = self._calc_temp_base_score(ref_temp, tags)

        # ── 3. 气压动态加权 ──
        pressure_modifier, is_veto = self._calc_pressure_modifier(delta_p, tags)

        if is_veto:
            tags.append(TacticalTag.RATING_VETO.value)
            return PredictionResult(
                do_trend=0.0,
                bite_index=self.bite_config.pressure_crash_score,
                tactical_tags=tags,
                report_stage=report_stage,
                confidence=confidence,
                time_period_advice=self._generate_period_advice(session.time_period, tags),
                season_note=self._generate_season_note(session.season, tags),
            )

        # ── 4. 溶解氧估算与加权 ──
        do_est = 0.0
        do_modifier = 0
        if "do_estimate" in features:
            do_est = self._calculate_do_from_values(p_local, ref_temp, api, tags)
            do_modifier = self._calc_do_modifier(do_est, tags)

        # ── 5. 天气加权 ──
        weather_modifier = self._calc_weather_modifier(api.weather_trend, tags)

        # ── 6. 时段加权 ──
        period_modifier = self._calc_time_period_modifier(session.time_period, tags)

        # ── 7. 季节修正 ──
        season_modifier = self._calc_season_modifier(session.season, tags)

        # ── 8. 温跃层分析 ──
        thermocline_modifier = 0
        if "thermocline" in features:
            thermocline_modifier = self._calc_thermocline_modifier(latest, tags)

        # ── 9. 温度趋势分析 ──
        temp_rate_modifier = 0
        if "temp_trend" in features and len(readings) >= 2:
            temp_field = {"bottom": "t_bottom", "mid": "t_mid", "top": "t_surface"}.get(
                self.fish_profile.water_layer, "t_bottom"
            )
            temp_trend = self._analyzer.calc_temp_trend(readings, field=temp_field)
            if temp_trend == "rising":
                tags.append(TacticalTag.STATUS_TEMP_RISING.value)
            elif temp_trend == "dropping":
                tags.append(TacticalTag.STATUS_TEMP_DROPPING.value)
            else:
                tags.append(TacticalTag.TREND_TEMP_STABLE.value)

            # P0: 温度速率量化分析
            temp_rate_modifier = self._calc_temp_rate_modifier(readings, tags)

        # ── 10. 月相 (Solunar) 评分 ── [P0 新增]
        solunar_modifier = self._calc_solunar_modifier(latest.timestamp, tags)
        solunar_info = calc_solunar_rating(latest.timestamp)

        # ── 11. 短期气压突变检测 ── [P0 新增]
        short_pressure_modifier = self._calc_short_pressure_modifier(readings, tags)

        # ── 12. 风向评分 ── [P1 新增]
        wind_dir_modifier = self._calc_wind_direction_modifier(
            api, session.season, tags
        )

        # ── 13. 湿度评分 ── [P1 新增]
        humidity_modifier = self._calc_humidity_modifier(api, tags)

        # ── 14. 三层水温空间分析 ── [P1 新增]
        thermal_profile_modifier = 0
        if "thermocline" in features and len(readings) >= 2:
            thermal_profile_modifier = self._calc_thermal_profile_modifier(
                readings, tags
            )

        # ── 15. 汇总评分（加权混合体系） ──
        # 基础分 + 传统修正（加法）
        additive_score = (
            base_score
            + pressure_modifier
            + do_modifier
            + weather_modifier
            + period_modifier
            + season_modifier
            + thermocline_modifier
            + solunar_modifier
            + short_pressure_modifier
            + wind_dir_modifier
            + humidity_modifier
            + thermal_profile_modifier
            + temp_rate_modifier
        )
        final_score = max(0, min(100, int(additive_score)))

        # ── 16. 综合评级 ──
        self._add_rating_tag(final_score, tags)

        # ── 17. 鱼情趋势判断（标准阶段以上） ──
        if "deep_analysis" in features:
            self._add_trend_tags(readings, tags)

        # ── 18. 生成时段建议和季节备注 ──
        period_advice = self._generate_period_advice(session.time_period, tags)
        season_note = self._generate_season_note(session.season, tags)

        # ── 19. 生成结构化战术建议 ── [P1 新增]
        tactical_advice = self._generate_tactical_advice(
            final_score, tags, session, latest
        )

        return PredictionResult(
            do_trend=round(do_est, 2),
            bite_index=final_score,
            tactical_tags=tags,
            report_stage=report_stage,
            confidence=confidence,
            time_period_advice=period_advice,
            season_note=season_note,
            solunar_info=solunar_info,
            tactical_advice=tactical_advice,
        )

    # ================================================================
    #  新增私有方法
    # ================================================================

    def _calculate_do_from_values(
        self, p_local: float, t_water: float, api: ApiData, tags: List[str]
    ) -> float:
        """基于 Benson & Krause 查表的溶氧估算（替代原始指数衰减公式）。

        计算步骤：
          1. 查表插值得到标准气压下饱和 DO
          2. 气压修正：DO_sat × (P_actual / 1013.25)
          3. 风力增氧：微风促进水面气体交换，实际 DO 趋近或超过饱和值
        """
        # 1. 查表插值
        do_sat_std = interpolate_do_saturation(t_water)

        # 2. 气压修正
        p_correction = p_local / 1013.25
        do_sat = do_sat_std * p_correction

        # 3. 风力增氧系数（微风促进气体交换，上限 15%）
        wind_factor = min(1.0 + 0.02 * api.wind_speed, 1.15)
        do_est = do_sat * wind_factor

        return do_est

    def _calc_time_period_modifier(self, time_period: str, tags: List[str]) -> int:
        """时段加权模块。"""
        period_tag_map = {
            "morning":   TacticalTag.PERIOD_MORNING_GOLDEN,
            "noon":      TacticalTag.PERIOD_NOON_REST,
            "afternoon": TacticalTag.PERIOD_AFTERNOON_ACTIVE,
            "evening":   TacticalTag.PERIOD_EVENING_PEAK,
        }
        if time_period in period_tag_map:
            tags.append(period_tag_map[time_period].value)

        return self.period_config.modifiers.get(time_period, 0)

    def _calc_season_modifier(self, season: str, tags: List[str]) -> int:
        """季节修正模块。"""
        season_tag_map = {
            "spring": TacticalTag.SEASON_SPRING_WARMING,
            "summer": TacticalTag.SEASON_SUMMER_HEAT,
            "autumn": TacticalTag.SEASON_AUTUMN_COOLING,
            "winter": TacticalTag.SEASON_WINTER_COLD,
        }
        if season in season_tag_map:
            tags.append(season_tag_map[season].value)

        mod = self.season_config.season_modifiers.get(season, {})
        return mod.get("score_modifier", 0)

    def _calc_thermocline_modifier(self, reading: SensorReading, tags: List[str]) -> int:
        """温跃层分析模块。

        表底温差较大时影响鱼类分布，需调整战术。
        """
        cfg = self.thermocline_config
        index = self._analyzer.calc_thermocline_index(reading)

        if index is None:
            return 0

        if index < -cfg.inversion_threshold:
            # 逆温现象（底层比表层暖）─ 异常情况
            tags.append(TacticalTag.STATUS_TEMP_INVERSION.value)
            tags.append(TacticalTag.TACTIC_FISH_SUSPENDED.value)  # 建议铓离底
            return -cfg.inversion_penalty
        elif abs(index) > cfg.strong_threshold:
            # 强温跃层 ─ 鱼类可能集中在温跃层附近
            tags.append(TacticalTag.STATUS_THERMOCLINE_STRONG.value)
            tags.append(TacticalTag.TACTIC_FISH_MID.value)  # 建议铓中层
            return -cfg.strong_penalty
        elif abs(index) > cfg.weak_threshold:
            tags.append(TacticalTag.STATUS_THERMOCLINE_WEAK.value)
            return 0

        return 0

    def _add_trend_tags(self, readings: List[SensorReading], tags: List[str]) -> None:
        """深度分析：鱼情总体趋势判断。

        综合气压趋势和温度趋势，判断鱼情是在转好还是转差。
        """
        p_detail = self._analyzer.calc_pressure_trend_detail(readings)
        temp_trend = self._analyzer.calc_temp_trend(readings, field="t_bottom")

        improving_signals = 0
        deteriorating_signals = 0

        # 气压趋势
        if p_detail["trend"] == "rising":
            improving_signals += 1
        elif p_detail["trend"] in ("dropping", "crash"):
            deteriorating_signals += 1

        # 温度趋势（夏季降温是好事，冬季升温是好事）
        # 简化逻辑：趋于稳定是中性
        if temp_trend == "rising":
            improving_signals += 1
        elif temp_trend == "dropping":
            deteriorating_signals += 1

        if improving_signals > deteriorating_signals:
            tags.append(TacticalTag.TREND_IMPROVING.value)
        elif deteriorating_signals > improving_signals:
            tags.append(TacticalTag.TREND_DETERIORATING.value)

    def _generate_period_advice(self, time_period: str, tags: List[str]) -> str:
        """生成时段铓鱼建议文案。"""
        advice_map = {
            "morning": (
                "当前处于早口黄金期，水体溶氧充足，鱼类活跃度高。"
                "建议把握早晨窗口期，稍铓浅一些。"
            ),
            "noon": (
                "当前处于午休期，日照强烈，表层水温升高，鱼口可能偏轻。"
                "建议铓深水或荐草区，耐心等待午后回口。"
            ),
            "afternoon": (
                "当前处于午后开口期，水温开始回落，鱼类重新活跃。"
                "建议适当铓浅，注意观察浮漂信号。"
            ),
            "evening": (
                "当前处于傍晚爆口期/夜铓时段，鱼类活动频繁。"
                "建议拉满缺铓，抛竿频率可适当提高。"
            ),
        }
        return advice_map.get(time_period, "")

    def _generate_season_note(self, season: str, tags: List[str]) -> str:
        """生成季节铓鱼备注。"""
        mod = self.season_config.season_modifiers.get(season, {})
        return mod.get("advice", "")

    # ================================================================
    #  新增评分模块（P0/P1/P2）
    # ================================================================

    def _calc_solunar_modifier(self, timestamp: int, tags: List[str]) -> int:
        """月相 (Solunar) 评分模块。"""
        phase, _ = calc_moon_phase(timestamp)
        cfg = self.solunar_config

        # 月相标签
        phase_tag_map = {
            "new_moon": TacticalTag.SOLUNAR_NEW_MOON,
            "full_moon": TacticalTag.SOLUNAR_FULL_MOON,
            "first_quarter": TacticalTag.SOLUNAR_FIRST_QUARTER,
            "last_quarter": TacticalTag.SOLUNAR_LAST_QUARTER,
        }
        if phase in phase_tag_map:
            tags.append(phase_tag_map[phase].value)
        elif "waxing" in phase:
            tags.append(TacticalTag.SOLUNAR_WAXING.value)
        elif "waning" in phase:
            tags.append(TacticalTag.SOLUNAR_WANING.value)

        return cfg.phase_modifiers.get(phase, 0)

    def _calc_short_pressure_modifier(
        self, readings: List[SensorReading], tags: List[str]
    ) -> int:
        """短窗口气压突变检测模块。

        检查 15 分钟内的急速气压变化，补充 2 小时窗口无法捕获的瞬态事件。
        """
        if len(readings) < 2:
            return 0

        cfg = self.pressure_config
        multi = self._analyzer.calc_pressure_multi_window(
            readings, cfg.windows
        )

        modifier = 0

        # 15 分钟短窗口急降
        d15 = multi.get("delta_15min", 0.0)
        if d15 <= cfg.short_drop_threshold:
            tags.append(TacticalTag.PRESSURE_SHORT_DROP.value)
            modifier -= cfg.short_drop_penalty
        elif d15 >= cfg.short_spike_threshold:
            tags.append(TacticalTag.PRESSURE_SHORT_SPIKE.value)
            modifier += cfg.short_spike_bonus

        # 波动率
        vol = multi.get("volatility_1h", 0.0)
        if vol > cfg.volatility_threshold:
            tags.append(TacticalTag.PRESSURE_HIGH_VOLATILITY.value)
            modifier -= cfg.volatility_penalty

        return modifier

    def _calc_temp_rate_modifier(
        self, readings: List[SensorReading], tags: List[str]
    ) -> int:
        """温度变化速率分析模块。

        快速水温变化（>1.5℃/h）通常触发鱼类应激反应。
        """
        if len(readings) < 2:
            return 0

        temp_field = {"bottom": "t_bottom", "mid": "t_mid", "top": "t_surface"}.get(
            self.fish_profile.water_layer, "t_bottom"
        )
        detail = self._analyzer.calc_temp_trend_detail(readings, field=temp_field)

        if detail["is_rapid"]:
            if detail["rate_per_hour"] > 0:
                tags.append(TacticalTag.TEMP_RAPID_RISE.value)
            else:
                tags.append(TacticalTag.TEMP_RAPID_DROP.value)
            return -5  # 快速变化通常对鱼口不利（应激）

        return 0

    def _calc_wind_direction_modifier(
        self, api: ApiData, season: str, tags: List[str]
    ) -> int:
        """风向评分模块（含季节交叉效应）。"""
        if not api.wind_direction:
            return 0

        cfg = self.wind_config
        direction = api.wind_direction.upper()

        # 优先检查季节覆盖
        override_key = (direction, season)
        if override_key in cfg.season_overrides:
            score = cfg.season_overrides[override_key]
        else:
            score = cfg.direction_modifiers.get(direction, 0)

        if score >= 2:
            tags.append(TacticalTag.STATUS_WIND_DIRECTION_FAVORABLE.value)
        elif score <= -3:
            tags.append(TacticalTag.STATUS_WIND_DIRECTION_ADVERSE.value)

        return score

    def _calc_humidity_modifier(self, api: ApiData, tags: List[str]) -> int:
        """湿度评分模块。高湿闷热扣分。"""
        if api.humidity <= 0:
            return 0  # 未提供湿度数据

        cfg = self.humidity_config
        if api.humidity >= cfg.muggy_threshold:
            tags.append(TacticalTag.STATUS_HUMIDITY_MUGGY.value)
            return -cfg.muggy_penalty
        else:
            tags.append(TacticalTag.STATUS_HUMIDITY_NORMAL.value)
            return 0

    def _calc_thermal_profile_modifier(
        self, readings: List[SensorReading], tags: List[str]
    ) -> int:
        """三层水温空间分布分析模块。"""
        if len(readings) < 2:
            return 0

        profile = self._analyzer.analyze_thermal_profile(readings)
        modifier = 0

        if profile["mixing_state"] == "well_mixed":
            tags.append(TacticalTag.THERMAL_WELL_MIXED.value)
            modifier += 3  # 水体混合良好，溶氧均匀，加分
        elif profile["mixing_state"] == "strongly_stratified":
            modifier -= 3  # 强分层可能底层缺氧

        if profile["layers_diverging"]:
            tags.append(TacticalTag.THERMAL_LAYERS_DIVERGING.value)
            modifier -= 2  # 各层趋势分化，鱼情不稳定

        return modifier

    def _generate_tactical_advice(
        self, result_score: int, tags: List[str],
        session: SessionContext, latest: SensorReading = None,
    ) -> dict:
        """生成结构化战术建议。"""
        advice = {}

        # 水层建议
        if TacticalTag.TACTIC_FISH_SUSPENDED.value in tags:
            advice["layer"] = "钓离底或半水（鱼因缺氧上浮）"
        elif TacticalTag.TACTIC_FISH_MID.value in tags:
            advice["layer"] = "钓中层，打行程搜索鱼层"
        elif TacticalTag.TACTIC_FISH_TOP.value in tags:
            advice["layer"] = "钓浮或打水皮"
        else:
            advice["layer"] = "钓底"

        # 用饵建议
        if TacticalTag.STATUS_TEMP_EXTREME_COLD.value in tags:
            advice["bait"] = "重腥味饵料或活饵（蚯蚓/红虫），促低温开口"
        elif TacticalTag.STATUS_TEMP_EXTREME_HOT.value in tags:
            advice["bait"] = "清淡型饵料，减少雾化"
        else:
            advice["bait"] = "腥香均衡型商品饵"

        # 节奏建议
        if result_score >= 80:
            advice["rhythm"] = "高频抛竿，积极逗钓"
        elif result_score >= 50:
            advice["rhythm"] = "正常节奏，耐心守候"
        else:
            advice["rhythm"] = "放慢节奏，守钓为主"

        # 风险提示
        risks = []
        if TacticalTag.PRESSURE_SHORT_DROP.value in tags:
            risks.append("气压短期急降中，鱼口可能随时变差")
        if TacticalTag.PRESSURE_HIGH_VOLATILITY.value in tags:
            risks.append("气压波动剧烈，鱼情不稳定")
        if TacticalTag.STATUS_HUMIDITY_MUGGY.value in tags:
            risks.append("高湿闷热，水体溶氧可能偏低")
        if TacticalTag.TEMP_RAPID_DROP.value in tags:
            risks.append("水温正在快速下降，鱼类可能应激停口")
        advice["risk"] = "；".join(risks) if risks else "当前无明显风险"

        return advice

