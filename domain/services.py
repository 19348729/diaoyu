"""
领域服务层 (Domain Services)
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
)
from .tags import TacticalTag
from .analyzers import TimeSeriesAnalyzer
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
    ):
        """支持依赖注入配置，方便针对不同水域/鱼种动态实例化。"""
        self.do_config = do_config or DissolvedOxygenConfig()
        self.fish_profile = fish_profile or FishSpeciesProfile()
        self.bite_config = bite_config or BiteIndexConfig()
        self.period_config = period_config or TimePeriodConfig()
        self.season_config = season_config or SeasonConfig()
        self.stage_config = stage_config or ProgressiveStageConfig()
        self.thermocline_config = thermocline_config or ThermoclineConfig()
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
        """虚拟溶解氧估算模块。
        
        公式：DO_est ≈ (P_local / scale) * (1 + k * Wind_api) / exp(α * T_water)
        注意：此处对气压稍作缩放(除以100)，使结果回落到 mg/L 的常规量纲级别（如 4~10），
        从而匹配常数类里面的阈值。
        """
        k = self.do_config.k
        alpha = self.do_config.alpha
        
        # 将气压缩放到类似“标准大气压倍数*10”的级别，以贴近真实的溶氧数值 (mg/L)
        p_scaled = hardware.p_local / 100.0  
        
        do_est = p_scaled * (1 + k * api.wind_speed) / math.exp(alpha * hardware.t_water)
        return do_est

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

        # ── 10. 汇总评分 ──
        final_score = (
            base_score
            + pressure_modifier
            + do_modifier
            + weather_modifier
            + period_modifier
            + season_modifier
            + thermocline_modifier
        )
        final_score = max(0, min(100, int(final_score)))

        # ── 11. 综合评级 ──
        self._add_rating_tag(final_score, tags)

        # ── 12. 鱼情趋势判断（标准阶段以上） ──
        if "deep_analysis" in features:
            self._add_trend_tags(readings, tags)

        # ── 13. 生成时段建议和季节备注 ──
        period_advice = self._generate_period_advice(session.time_period, tags)
        season_note = self._generate_season_note(session.season, tags)

        return PredictionResult(
            do_trend=round(do_est, 2),
            bite_index=final_score,
            tactical_tags=tags,
            report_stage=report_stage,
            confidence=confidence,
            time_period_advice=period_advice,
            season_note=season_note,
        )

    # ================================================================
    #  新增私有方法
    # ================================================================

    def _calculate_do_from_values(
        self, p_local: float, t_water: float, api: ApiData, tags: List[str]
    ) -> float:
        """纯数值版溶氧估算（从时序提取后的值调用）。"""
        k = self.do_config.k
        alpha = self.do_config.alpha
        p_scaled = p_local / 100.0
        do_est = p_scaled * (1 + k * api.wind_speed) / math.exp(alpha * t_water)
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
