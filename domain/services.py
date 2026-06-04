"""领域服务层 (Domain Services)
============================
封装跨值对象的纯业务逻辑。高内聚、低耦合。
纯面向对象，不依赖任何数据库或外部框架，方便被 Django Service 层直接调用。
"""
import math
import time as _time
from typing import List, Optional, Tuple

from .value_objects import (
    HardwareData, ApiData, PredictionResult,
    SensorReading, SensorTimeSeries, SessionContext,
)
from .constants import (
    DissolvedOxygenConfig, FishSpeciesProfile, BiteIndexConfig,
    TimePeriodConfig, SeasonConfig, ProgressiveStageConfig, ThermoclineConfig,
    SolunarConfig, PressureAnalysisConfig, WindDirectionConfig, HumidityConfig,
    WindSpeedConfig, AirToWaterConfig, PressureAbsoluteConfig,
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
        wind_speed_config: WindSpeedConfig = None,
        air_to_water_config: AirToWaterConfig = None,
        pressure_abs_config: PressureAbsoluteConfig = None,
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
        self.wind_speed_config = wind_speed_config or WindSpeedConfig()
        self.air_to_water_config = air_to_water_config or AirToWaterConfig()
        self.pressure_abs_config = pressure_abs_config or PressureAbsoluteConfig()
        self._analyzer = TimeSeriesAnalyzer()

    # ================================================================
    #  开口指数合成模型（乘性归一）
    # ================================================================
    #  设计目标：解决旧加法模型的结构缺陷
    #    1) 各因子未归一、总和失控 → clamp 抹平两端区分度
    #    2) base_score 台阶式 → 水温边界 30 分断崖
    #    3) 气压三处重复计权、veto 硬编码定值
    #  方案：base01（平滑隶属度，相对最适达成度，跨鱼种可比）
    #        × 气压系数（合并封顶）× ∏环境系数（利好递减/不利短板）
    _UP_SCALE = 55.0      # 利好因子强度缩放（边际递减，越接近满分提升越小）
    _UP_CAP = 0.45        # 单个利好因子最多吃掉的剩余空间比例
    _DOWN_SCALE = 42.0    # 不利因子强度缩放
    _DOWN_MIN = 0.30      # 单因子乘性下限，避免单点过度压制
    _PRESSURE_CLAMP = (-25.0, 18.0)  # 气压三项合并后的封顶区间
    _VETO_FACTOR = 0.15   # 气压骤降一票否决的强力折减系数（软化原硬编码定值）
    _TEMP_PEAK = 0.92     # 最适水温处的基准达成度峰值（<1，为利好因子留出上探空间）

    def _temp_membership(self, t_water: float, tags: List[str]) -> float:
        """平滑的水温隶属度 base01 ∈ (0, 0.92]，替代 70/40/10 三档台阶。

        以鱼种最适区间中点为峰、高斯衰减，消除边界 30 分断崖；
        该值是“相对该鱼种自身最适的达成度”，跨鱼种可直接比较，
        从根上消除 auto 选鱼时高 base 鱼种的基准偏置。
        """
        o_lo, o_hi = self.fish_profile.optimal_temp
        center = (o_lo + o_hi) / 2.0
        half = max(0.5, (o_hi - o_lo) / 2.0)
        # 标定 sigma，使最适区间边界处的高斯值约为 0.85
        sigma = half / 0.4034
        gauss = math.exp(-((t_water - center) / sigma) ** 2)
        base01 = self._TEMP_PEAK * gauss

        # 标签分档（与原 optimal/tolerable/extreme 语义对齐）
        if gauss >= 0.85:
            tags.append(TacticalTag.STATUS_TEMP_OPTIMAL.value)
        elif gauss >= 0.35:
            tags.append(TacticalTag.STATUS_TEMP_TOLERABLE.value)
        elif t_water > center:
            tags.append(TacticalTag.STATUS_TEMP_EXTREME_HOT.value)
        else:
            tags.append(TacticalTag.STATUS_TEMP_EXTREME_COLD.value)
        return base01

    def _apply_factor(self, c: float, score: float, up_gate: float = 1.0) -> float:
        """把单个修正分值施加到当前达成度 c ∈ [0,1] 上。

        利好(score>0)：按剩余空间 (1-c) 递减逼近上限（高分区不撞 100），
                       并乘以 up_gate（水温达成度）—— 水温不到位时利好打折，
                       体现“鱼不在状态，天气再好也有限”的短板直觉；
        不利(score<0)：乘性压制（短板效应，多个不利连乘自然放大影响），不设闸门。
        """
        if score >= 0:
            gain = min(score / self._UP_SCALE, self._UP_CAP) * up_gate
            return c + (1.0 - c) * gain
        factor = max(self._DOWN_MIN, 1.0 + score / self._DOWN_SCALE)
        return c * factor

    def _combine_score(
        self, base01: float, env_scores: List[float],
        pressure_sum: float = 0.0, veto: bool = False,
    ) -> int:
        """乘性归一汇总：base01 × 气压系数 × ∏环境系数 → 开口指数 [0,100]。"""
        c = max(0.0, min(1.0, base01))
        # 气压维度：合并封顶，避免变率/短窗/绝对值三处重复计权
        if veto:
            c *= self._VETO_FACTOR
        else:
            ps = max(self._PRESSURE_CLAMP[0], min(self._PRESSURE_CLAMP[1], pressure_sum))
            c = self._apply_factor(c, ps, up_gate=c)
        # 利好闸门 = 经气压/veto 折减后的达成度上限（综合状态差则利好打折，
        # 且对环境因子取固定值以消除施加顺序依赖）
        gate = min(base01, c)
        for s in env_scores:
            c = self._apply_factor(c, s, up_gate=gate)
        return max(0, min(100, int(round(c * 100))))

    def predict(self, hardware: HardwareData, api: ApiData) -> PredictionResult:
        """单帧快照预测（向后兼容接口）。
        
        保留原始接口，内部复用基础评分逻辑。
        """
        tags: List[str] = []

        # 1. 估算虚拟溶解氧
        do_est = self._calculate_do(hardware, api, tags)

        # 2. 根据水温计算基准达成度（平滑隶属度）
        base01 = self._temp_membership(hardware.t_water, tags)

        # 3. 气压动态加权与一票否决判定
        pressure_modifier, is_veto = self._calc_pressure_modifier(hardware.delta_p, tags)
        if is_veto:
            tags.append(TacticalTag.RATING_VETO.value)

        # 4. 溶解氧加权
        do_modifier = self._calc_do_modifier(do_est, tags)

        # 5. 短临天气加权
        weather_modifier = self._calc_weather_modifier(api.weather_trend, tags)

        # 6. 乘性归一汇总（气压 veto 时软化折减，而非硬编码定值）
        final_score = self._combine_score(
            base01, [do_modifier, weather_modifier],
            pressure_sum=pressure_modifier, veto=is_veto,
        )

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
        user_inventory: Optional[dict] = None,
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

        # ── 2. 基准达成度（水温，平滑隶属度 0~0.92） ──
        base01 = self._temp_membership(ref_temp, tags)

        # ── 3. 气压动态加权 ──
        #   veto 不再短路返回固定分，而是在汇总阶段以强折减系数软化，
        #   既保留“骤降几乎空军”的强先验，又能平滑反映水温等其它因子。
        pressure_modifier, is_veto = self._calc_pressure_modifier(delta_p, tags)
        if is_veto:
            tags.append(TacticalTag.RATING_VETO.value)

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

        # ── 8. 温跃层分析（仅多层水温传感器可用） ──
        thermocline_modifier = 0
        is_single_sensor = (
            latest.t_bottom is not None
            and latest.t_surface is not None
            and latest.t_bottom == latest.t_surface
        )
        if "thermocline" in features and not is_single_sensor:
            thermocline_modifier = self._calc_thermocline_modifier(latest, tags)
        elif "thermocline" in features and is_single_sensor:
            tags.append(TacticalTag.THERMOCLINE_SINGLE_SENSOR.value)

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

        # ── 14. 三层水温空间分析（仅多层水温传感器可用） ── [P1 新增]
        thermal_profile_modifier = 0
        if "thermocline" in features and len(readings) >= 2 and not is_single_sensor:
            thermal_profile_modifier = self._calc_thermal_profile_modifier(
                readings, tags
            )

        # ── 15. 风力等级评分 ── [P0 新增]
        wind_speed_modifier = self._calc_wind_speed_modifier(api, tags)

        # ── 16. 气压绝对值评分 ── [P1 新增]
        pressure_abs_modifier = self._calc_pressure_absolute_modifier(
            latest.p_local if latest and latest.p_local else None, tags
        )

        # ── 17. 汇总评分（乘性归一模型） ──
        #   - base01：相对该鱼种最适温度的达成度（跨鱼种可比）
        #   - 气压三项（变率/短窗/绝对值）合并封顶为单一维度，避免重复计权
        #   - 利好因子边际递减（高分区不撞 100），不利因子乘性压制（短板效应）
        pressure_sum = pressure_modifier + short_pressure_modifier + pressure_abs_modifier
        env_scores = [
            do_modifier, weather_modifier, period_modifier, season_modifier,
            thermocline_modifier, solunar_modifier, wind_dir_modifier,
            humidity_modifier, thermal_profile_modifier, temp_rate_modifier,
            wind_speed_modifier,
        ]
        final_score = self._combine_score(base01, env_scores, pressure_sum, veto=is_veto)

        # ── 18. 综合评级 ──
        self._add_rating_tag(final_score, tags)

        # ── 17. 鱼情趋势判断（标准阶段以上） ──
        if "deep_analysis" in features:
            self._add_trend_tags(readings, tags, season=session.season)

        # ── 18. 生成时段建议和季节备注（动态文案） ──
        period_advice = self._generate_period_advice(
            session.time_period, tags, latest=latest, api=api
        )
        season_note = self._generate_season_note(session.season, tags)

        # ── 19. 生成结构化战术建议 ──
        tactical_advice = self._generate_tactical_advice(
            final_score, tags, session, latest, api=api, user_inventory=user_inventory
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
        do_sat *= wind_factor

        # 4. 高温缺氧折减：估算“实际溶氧”而非理论饱和值。
        #    高温水体易热分层、底层耗氧，实际 DO 显著低于饱和值；
        #    使溶氧因子在盛夏高温时能真正触发缺氧判定，
        #    修复原实现“恒为健康、判别力失效”的缺陷。
        reduction = 1.0
        if t_water > 26.0:
            reduction -= min((t_water - 26.0) * 0.035, 0.35)
        do_est = do_sat * max(0.55, reduction)

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

    def _add_trend_tags(
        self, readings: List[SensorReading], tags: List[str],
        season: str = "spring",
    ) -> None:
        """深度分析：鱼情总体趋势判断（含季节×温度趋势交叉修正）。

        综合气压趋势和温度趋势，判断鱼情是在转好还是转差。
        修正：夏季降温=好事，冬季升温=好事。
        """
        p_detail = self._analyzer.calc_pressure_trend_detail(readings)
        temp_trend = self._analyzer.calc_temp_trend(readings, field="t_bottom")

        improving_signals = 0
        deteriorating_signals = 0

        # 气压趋势（四季一致：升压好、降压差）
        if p_detail["trend"] == "rising":
            improving_signals += 1
        elif p_detail["trend"] in ("dropping", "crash"):
            deteriorating_signals += 1

        # 温度趋势（季节交叉修正）
        if season == "summer":
            # 夏季：降温缓解高温压力是好事
            if temp_trend == "dropping":
                improving_signals += 1
            elif temp_trend == "rising":
                deteriorating_signals += 1
        elif season == "winter":
            # 冬季：升温是唯一黄金窗口
            if temp_trend == "rising":
                improving_signals += 1
            elif temp_trend == "dropping":
                deteriorating_signals += 1
        else:
            # 春秋：升温通常促进鱼类活性
            if temp_trend == "rising":
                improving_signals += 1
            elif temp_trend == "dropping":
                deteriorating_signals += 1

        if improving_signals > deteriorating_signals:
            tags.append(TacticalTag.TREND_IMPROVING.value)
        elif deteriorating_signals > improving_signals:
            tags.append(TacticalTag.TREND_DETERIORATING.value)

    def _generate_period_advice(
        self, time_period: str, tags: List[str],
        latest: SensorReading = None, api: ApiData = None,
    ) -> str:
        """生成动态时段建议文案（嵌入实际数据引用）。"""
        fish_name = self.fish_profile.name

        # 构建数据片段
        temp_str = ""
        pressure_str = ""
        if latest and latest.t_bottom is not None:
            t = latest.t_bottom
            opt_lo, opt_hi = self.fish_profile.optimal_temp
            if opt_lo <= t <= opt_hi:
                activity = "活性高"
            elif self.fish_profile.tolerable_temp[0] <= t <= self.fish_profile.tolerable_temp[1]:
                activity = "活性一般"
            else:
                activity = "活性极低"
            temp_str = f"水底实测 {t:.1f}℃，{fish_name}{activity}。"
        if latest and latest.p_local is not None:
            pressure_str = f"本地气压 {latest.p_local:.1f} hPa。"
        elif api and api.wind_speed is not None:
            pressure_str = ""  # 纯天气模式无本地气压

        base_map = {
            "morning": (
                f"当前处于早口黄金期，水体溶氧充足。{temp_str}"
                f"建议把握早晨窗口期，适当钓浅。{pressure_str}"
            ),
            "noon": (
                f"当前处于午休期，日照强烈，表层水温升高。{temp_str}"
                f"建议钓深水或水草区，耐心等待午后回口。{pressure_str}"
            ),
            "afternoon": (
                f"当前处于午后开口期，水温开始回落。{temp_str}"
                f"鱼类重新活跃，建议适当钓浅，注意观察浮漂信号。{pressure_str}"
            ),
            "evening": (
                f"当前处于傍晚爆口期/夜钓时段。{temp_str}"
                f"鱼类活动频繁，可适当提高抛竿频率。{pressure_str}"
            ),
        }
        return base_map.get(time_period, temp_str + pressure_str)

    def _generate_season_note(self, season: str, tags: List[str]) -> str:
        """生成季节钓鱼备注。"""
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
        api: ApiData = None,
        user_inventory: Optional[dict] = None,
    ) -> dict:
        """生成结构化战术建议（与鱼种绑定 + 动态数据引用）。"""
        advice = {}
        profile = self.fish_profile

        # ── 水层建议：优先鱼种默认，异常标签覆盖 ──
        if TacticalTag.TACTIC_FISH_SUSPENDED.value in tags:
            advice["layer"] = "钓离底或半水（鱼因缺氧上浮）"
        elif TacticalTag.TACTIC_FISH_MID.value in tags:
            advice["layer"] = "钓中层，打行程搜索鱼层"
        elif TacticalTag.TACTIC_FISH_TOP.value in tags:
            advice["layer"] = "钓浮或打水皮"
        elif profile.default_layer_advice:
            advice["layer"] = profile.default_layer_advice
        else:
            layer_text = {
                "bottom": "钓底", "mid": "钓中下层", "top": "钓浮"
            }
            advice["layer"] = layer_text.get(profile.water_layer, "钓底")

        # ── 用饵建议：鱼种×季节，极端温度覆盖 ──
        if TacticalTag.STATUS_TEMP_EXTREME_COLD.value in tags:
            advice["bait"] = "重腥味饵料或活饵（蚯蚓/红虫），促低温开口"
        elif TacticalTag.STATUS_TEMP_EXTREME_HOT.value in tags:
            advice["bait"] = "清淡型饵料，减少雾化"
        else:
            season = session.season
            advice["bait"] = profile.bait_by_season.get(season, "腥香均衡型商品饵")

        # ── 作钓方式 ──
        advice["method"] = profile.fishing_method

        # ── 节奏建议 ──
        if result_score >= 80:
            advice["rhythm"] = "高频抛竿，积极逗钓"
        elif result_score >= 50:
            advice["rhythm"] = "正常节奏，耐心守候"
        else:
            advice["rhythm"] = "放慢节奏，守钓为主"

        # ── 钓深建议 ──
        advice["depth"] = self._suggest_depth(session, tags)

        # ── 钓位建议 [P1 新增] ──
        advice["spot"] = self._suggest_spot(session, tags, api)

        # ── 鱼种活性描述 [P1 新增] ──
        advice["fish_activity"] = self._describe_fish_activity(
            latest, session
        )

        # ── 风险提示 ──
        risks = []
        if TacticalTag.PRESSURE_SHORT_DROP.value in tags:
            risks.append("气压短期急降中，鱼口可能随时变差")
        if TacticalTag.PRESSURE_HIGH_VOLATILITY.value in tags:
            risks.append("气压波动剧烈，鱼情不稳定")
        if TacticalTag.STATUS_HUMIDITY_MUGGY.value in tags:
            risks.append("高湿闷热，水体溶氧可能偏低")
        if TacticalTag.TEMP_RAPID_DROP.value in tags:
            risks.append("水温正在快速下降，鱼类可能应激停口")
        if TacticalTag.WIND_SPEED_STRONG.value in tags:
            risks.append("风力过大，手竿作钓困难，注意安全")
        if TacticalTag.PRESSURE_ABS_EXTREME_LOW.value in tags:
            risks.append("气压极低（<990 hPa），闷热缺氧，建议改日出钓")
        elif TacticalTag.PRESSURE_ABS_LOW.value in tags:
            risks.append("气压偏低（<1000 hPa），鱼口可能偏差")
        if TacticalTag.WEATHER_STORM_APPROACHING.value in tags:
            risks.append("未来数小时有雷阵雨逼近，抓紧末日口但注意安全撤离")
        advice["risk"] = "；".join(risks) if risks else "当前无明显风险"

        # ── 利好信号 [P2 新增] ──
        highlights = []
        if TacticalTag.WEATHER_POST_RAIN_CLEAR.value in tags:
            highlights.append("🎉 雨后初晴，气压回升+溶氧充足+食物丰富，绝佳鱼情！")
        if TacticalTag.WEATHER_LONG_RAIN_TO_CLEAR.value in tags:
            highlights.append("🔥 连续阴雨后放晴，经典爆护天气！")
        if TacticalTag.WEATHER_STORM_APPROACHING.value in tags:
            highlights.append("⚡ 雷阵雨前末日口，鱼口会异常凶猛，但务必注意安全")
        if TacticalTag.PRESSURE_ABS_OPTIMAL.value in tags:
            highlights.append("✅ 气压处于最适范围（1005-1020 hPa），利好出钓")
        advice["highlight"] = "；".join(highlights) if highlights else ""

        # ── 关联查询用户的数字钓箱设备并做个性化匹配 ──
        advice["equipment_advice"] = self._generate_equipment_advice(
            target_fish=profile.name,
            api=api,
            user_inventory=user_inventory,
            session=session,
            tags=tags,
            latest=latest
        )

        return advice

    def _generate_equipment_advice(
        self,
        target_fish: str,
        api: ApiData,
        user_inventory: Optional[dict],
        session: SessionContext,
        tags: List[str],
        latest: SensorReading = None
    ) -> dict:
        """
        根据目标鱼种、天气/季节/温度数据，从用户拥有的数字钓箱(user_inventory)中精准匹配最合适的装备。
        如果没有匹配的，或者用户未录入装备，则给出建议配比，并提示在数字钓箱中补充。
        """
        advice = {
            "rod": {},
            "main_line": {},
            "sub_line_hook": {},
            "float": {},
            "bait": {}
        }
        
        # 1. 安全初始化与空钓箱标志
        if not user_inventory:
            user_inventory = {}
            
        rods = user_inventory.get("rods", [])
        main_lines = user_inventory.get("mainLines", [])
        sub_lines = user_inventory.get("subLineHooks", [])
        floats = user_inventory.get("floats", [])
        baits = user_inventory.get("baits", [])
        
        # 风速判断 (>12km/h, 约 3.33 m/s)
        is_windy = False
        if api and api.wind_speed > 3.33:
            is_windy = True
            
        # 温度/极寒判断 (水温或气温极低 < 12℃)
        is_cold = False
        if TacticalTag.STATUS_TEMP_EXTREME_COLD.value in tags:
            is_cold = True
        elif latest and latest.t_bottom is not None and latest.t_bottom < 12.0:
            is_cold = True
        elif latest and latest.t_surface is not None and latest.t_surface < 12.0:
            is_cold = True
            
        # 目标鱼种特性：大鱼（鲤鱼/草鱼/青鱼/大物/鲢鳙）还是小鱼（鲫鱼/白条/鲮鱼/罗非鱼）
        is_big_fish = target_fish in ("鲤鱼", "草鱼", "青鱼", "鲢鳙", "大物")
        
        # ──────────────────────────────────────────────
        #  (1) 鱼竿适配逻辑 (Rods)
        # ──────────────────────────────────────────────
        ideal_rod_desc = ""
        if is_windy:
            ideal_rod_desc = "短硬竿 (长度 <= 4.5米，19调或28调)，以获得更好的抛投精准度与抗风控制力"
        elif is_big_fish:
            ideal_rod_desc = "长硬竿 (长度 >= 5.4米，19调或28调)，提供足够的腰力控鱼，防爆竿断线"
        else:
            ideal_rod_desc = "轻软竿 (长度 <= 4.5米，28调或37调)，手感轻盈，防拉豁小鱼嘴"
            
        best_rod = None
        best_rod_score = -999
        
        for r in rods:
            try:
                length = float(r.get("length", 4.5))
            except (ValueError, TypeError):
                length = 4.5
            action = r.get("action", "未知") or "未知"
            
            score = 0
            # 风天适配
            if is_windy:
                if length <= 4.5:
                    score += 50
                if any(x in action for x in ("19", "28", "极硬")):
                    score += 30
            # 大鱼适配
            elif is_big_fish:
                if length >= 5.4:
                    score += 50
                if any(x in action for x in ("19", "28", "大物")):
                    score += 30
            # 小鱼适配
            else:
                if length <= 4.5:
                    score += 50
                if any(x in action for x in ("28", "37", "软", "综合")):
                    score += 30
                    
            if score > best_rod_score:
                best_rod_score = score
                best_rod = r
                
        if best_rod:
            advice["rod"] = {
                "recommendation": f"{best_rod.get('brand', '')} {best_rod.get('name', '')} ({best_rod.get('length')}米, {best_rod.get('action', '未知')})",
                "matching_id": best_rod.get("id"),
                "reason": f"已为您从数字钓箱匹配最优鱼竿。当前{'大风' if is_windy else '作钓' + target_fish}场景，该竿的长度与调性契合度高。"
            }
        else:
            advice["rod"] = {
                "recommendation": f"推荐使用【{ideal_rod_desc}】",
                "matching_id": None,
                "reason": "数字钓箱暂无最适配的鱼竿，建议在钓箱中补充相应规格。"
            }
            
        # ──────────────────────────────────────────────
        #  (2) 主线适配逻辑 (MainLine)
        # ──────────────────────────────────────────────
        # 确定理想主线号
        if is_big_fish:
            ideal_main = 2.5 if is_cold else 4.0
        else:
            ideal_main = 0.8 if is_cold else 1.2
            
        best_ml = None
        best_ml_score = -999
        for ml in main_lines:
            try:
                size = float(ml.get("size", 1.5))
            except (ValueError, TypeError):
                size = 1.5
            # 打分：越接近理想线号分数越高
            score = 100 - abs(size - ideal_main) * 30
            if score > best_ml_score:
                best_ml_score = score
                best_ml = ml
                
        if best_ml:
            advice["main_line"] = {
                "recommendation": f"{best_ml.get('size')}号主线",
                "matching_id": best_ml.get("id"),
                "reason": f"已为您从数字钓箱匹配最优主线。针对{target_fish}{'且处于轻口低温期' if is_cold else ''}，该线号兼顾拉力与敏感度。"
            }
        else:
            advice["main_line"] = {
                "recommendation": f"推荐使用【{ideal_main}号】主线",
                "matching_id": None,
                "reason": f"数字钓箱暂无适配主线。针对{target_fish}{'低温轻口' if is_cold else ''}推荐此线号。"
            }
            
        # ──────────────────────────────────────────────
        #  (3) 子线双钩适配逻辑 (SubLineHook)
        # ──────────────────────────────────────────────
        # 确定理想子线与钩型
        if is_big_fish:
            ideal_sub = 1.5 if is_cold else 3.0
            ideal_hook_type = "伊势尼"
            ideal_hook_size = "5号" if is_cold else "7号"
        else:
            ideal_sub = 0.3 if is_cold else 0.6
            ideal_hook_type = "袖钩"
            ideal_hook_size = "2号" if is_cold else "4号"
            
        best_sl = None
        best_sl_score = -999
        for sl in sub_lines:
            try:
                line_size = float(sl.get("lineSize", 0.8))
            except (ValueError, TypeError):
                line_size = 0.8
            hook_type = sl.get("hookType", "") or ""
            hook_size = str(sl.get("hookSize", ""))
            
            score = 100 - abs(line_size - ideal_sub) * 40
            if ideal_hook_type in hook_type:
                score += 20
            # 钩号如果刚好匹配
            if ideal_hook_size in hook_size:
                score += 10
                
            if score > best_sl_score:
                best_sl_score = score
                best_sl = sl
                
        if best_sl:
            advice["sub_line_hook"] = {
                "recommendation": f"{best_sl.get('lineSize')}号子线 + {best_sl.get('hookSize')}{best_sl.get('hookType')}",
                "matching_id": best_sl.get("id"),
                "reason": f"已为您从数字钓箱匹配最优子线双钩。{'极寒降温，推荐细线小钩以降低鱼警惕性；' if is_cold else ''}双钩类型与拉力匹配。"
            }
        else:
            advice["sub_line_hook"] = {
                "recommendation": f"推荐使用【{ideal_sub}号子线 + {ideal_hook_size}{ideal_hook_type}】",
                "matching_id": None,
                "reason": f"数字钓箱暂无适配子线。针对{target_fish}{'低温轻口' if is_cold else ''}推荐此配置。"
            }
            
        # ──────────────────────────────────────────────
        #  (4) 浮漂适配逻辑 (Float)
        # ──────────────────────────────────────────────
        is_deep = False
        depth_advice = self._suggest_depth(session, tags)
        if any(x in depth_advice for x in ("深", "2.5-", "3-", "4米")):
            is_deep = True
            
        if is_windy or is_deep:
            ideal_lead = 3.0
            ideal_float_desc = "大吃铅量浮漂 (>= 2.5g，如大底漂)，以便抗风抗流水、迅速带线到底"
        else:
            ideal_lead = 1.2
            ideal_float_desc = "小吃铅量灵敏浮漂 (< 1.5g，如浅水鲫鱼漂)，提升吃口敏锐度"
            
        best_fl = None
        best_fl_score = -999
        for fl in floats:
            try:
                lead = float(fl.get("lead", 1.8))
            except (ValueError, TypeError):
                lead = 1.8
            score = 100 - abs(lead - ideal_lead) * 30
            if score > best_fl_score:
                best_fl_score = score
                best_fl = fl
                
        if best_fl:
            advice["float"] = {
                "recommendation": f"{best_fl.get('name')} (吃铅{best_fl.get('lead')}g)",
                "matching_id": best_fl.get("id"),
                "reason": f"已从数字钓箱匹配。当前{'大风' if is_windy else ''}{'且' if is_windy and is_deep else ''}{'深水' if is_deep else ''}环境，吃铅量与抗风/灵敏度完美契合。"
            }
        else:
            advice["float"] = {
                "recommendation": f"推荐使用【{ideal_float_desc}】",
                "matching_id": None,
                "reason": f"未在钓箱找到最优浮漂。建议准备吃铅约 {ideal_lead}g 的浮漂以应对当前环境。"
            }
            
        # ──────────────────────────────────────────────
        #  (5) 饵料适配与“老三样”黄金配比检测 (Bait)
        # ──────────────────────────────────────────────
        has_blue = False
        has_918 = False
        has_sugong = False
        
        blue_id, n918_id, sugong_id = None, None, None
        
        for b in baits:
            name = b.get("name", "") or ""
            b_id = b.get("id")
            
            if "蓝鲫" in name:
                has_blue = True
                blue_id = b_id
            if "九一八" in name or "918" in name:
                has_918 = True
                n918_id = b_id
            if "速攻" in name:
                has_sugong = True
                sugong_id = b_id
                
        match_count = sum([has_blue, has_918, has_sugong])
        if match_count >= 2:
            owned_names = []
            if has_blue: owned_names.append("野战蓝鲫")
            if has_918: owned_names.append("九一八")
            if has_sugong: owned_names.append("速攻2号")
            
            is_cold_bait = is_cold
            if api and hasattr(api, "humidity") and not is_cold_bait:
                if session.season == "winter":
                    is_cold_bait = True
                    
            if is_cold_bait:
                ratio_desc = "野战蓝鲫 (腥) 40% + 九一八 (香) 40% + 速攻 (状态) 20%"
                ratio_reason = "当前属于低温季节，鱼类极度需要高蛋白补充体力，推荐此经典【老三样】重腥配方，拉饵作钓，促低温开口。"
            else:
                ratio_desc = "野战蓝鲫 (腥) 20% + 九一八 (香) 60% + 速攻 (状态) 20%"
                ratio_reason = "当前气温偏高，为避开表层小杂鱼闹钩，推荐此【老三样】谷物麦香主攻大鱼配方，搓大饵钓底。"
                
            advice["bait"] = {
                "recommendation": f"经典【老三样】黄金配比：{ratio_desc}",
                "matching_id": blue_id or n918_id or sugong_id,
                "reason": f"检测到您的钓箱已备齐 {', '.join(owned_names)} 等经典饵料。{ratio_reason}"
            }
        else:
            ideal_flavor = ""
            if is_cold:
                ideal_flavor = "浓腥/腥香/活体肉腥"
            elif session.season == "summer":
                ideal_flavor = "天然麸香/谷香/清甜"
            else:
                ideal_flavor = "香腥均衡/本味"
                
            best_bait = None
            best_bait_score = -999
            for b in baits:
                flavor = b.get("flavor", "") or ""
                target = b.get("targetFish", "") or ""
                
                score = 0
                if target_fish in target or "综合" in target:
                    score += 50
                if is_cold and any(x in flavor for x in ("腥", "活")):
                    score += 30
                elif not is_cold and any(x in flavor for x in ("麸", "香", "谷", "甜")):
                    score += 30
                else:
                    score += 10
                    
                if score > best_bait_score:
                    best_bait_score = score
                    best_bait = b
                    
            if best_bait and best_bait_score >= 40:
                advice["bait"] = {
                    "recommendation": f"{best_bait.get('brand', '')} {best_bait.get('name', '')} ({best_bait.get('flavor')})",
                    "matching_id": best_bait.get("id"),
                    "reason": f"已从数字钓箱匹配最适配的单品饵料。味型为【{best_bait.get('flavor')}】，十分契合当前{target_fish}在{'低温' if is_cold else '常温'}下的开口偏好。"
                }
            else:
                if is_cold:
                    rec = "浓腥型商品饵 (如 4/6号鲫、野战蓝鲫) 或 鲜活红虫/蚯蚓"
                    reason = "水温较低，鱼活性差，重腥味/鲜活红虫能大幅提高诱鱼效率。"
                else:
                    rec = "谷物清香型商品饵 (如 九一八野战篇、大板鲫) 搭配拉丝粉"
                    reason = "温暖水域杂鱼较多，清淡天然的谷物麦香能有效避开小鱼侵扰，直击底层大鱼。"
                advice["bait"] = {
                    "recommendation": f"推荐使用【{rec}】",
                    "matching_id": None,
                    "reason": f"数字钓箱暂无适配饵料。{reason}"
                }
                
        return advice

    def _suggest_depth(
        self, session: SessionContext, tags: List[str]
    ) -> str:
        """根据季节+时段+鱼种推荐钓深。"""
        layer = self.fish_profile.water_layer
        season = session.season
        period = session.time_period

        if layer == "top":
            return "钓浮 1.5-3 米水深"

        if season == "winter":
            return "建议钓深 2.5-4 米，鱼扎堆在深水越冬"
        elif season == "summer" and period == "noon":
            return "建议钓深 2-3 米，避开表层高温区"
        elif season == "spring":
            return "建议钓浅 1-1.5 米，鱼上滩觅食繁殖"
        else:
            return "建议钓 1.5-2.5 米"

    def _suggest_spot(
        self, session: SessionContext, tags: List[str],
        api: ApiData = None,
    ) -> str:
        """钓位选择建议（风向+季节+时段综合）。[P1 新增]"""
        season = session.season
        wind_dir = api.wind_direction if api else ""

        # 风向驱动钓位
        if wind_dir in ("N", "NW", "NE"):
            spot = "选下风口（南岸），食物被风吹聚集"
        elif wind_dir in ("S", "SW", "SE"):
            spot = "选下风口（北岸），同时食物丰富"
        elif wind_dir in ("E", "W"):
            spot = "选侧风位，利于抛竿且食物堆积"
        else:
            spot = ""

        # 季节补充
        if season == "winter":
            spot = (spot + "；" if spot else "") + "优先选向阳深水湾，避风背水"
        elif season == "spring":
            spot = (spot + "；" if spot else "") + "优先选浅滩、水草边、进水口"
        elif season == "summer" and session.time_period == "noon":
            spot = (spot + "；" if spot else "") + "选树荫下或深水区，避开烈日直射"

        return spot or "选深浅交界处、进水口或水草边缘"

    def _describe_fish_activity(
        self, latest: SensorReading = None,
        session: SessionContext = None,
    ) -> str:
        """鱼种活性描述（基于实测水温）。[P1 新增]"""
        profile = self.fish_profile
        if latest is None or latest.t_bottom is None:
            return ""

        t = latest.t_bottom
        opt_lo, opt_hi = profile.optimal_temp
        tol_lo, tol_hi = profile.tolerable_temp

        if opt_lo <= t <= opt_hi:
            return f"当前水温 {t:.1f}℃ 处于{profile.name}最适温度区间（{opt_lo:.0f}-{opt_hi:.0f}℃），活性高，动作清晰"
        elif tol_lo <= t <= tol_hi:
            if t < opt_lo:
                return f"当前水温 {t:.1f}℃ 低于{profile.name}最适温度（{opt_lo:.0f}℃），活性偏低，口轻动作小"
            else:
                return f"当前水温 {t:.1f}℃ 高于{profile.name}最适温度（{opt_hi:.0f}℃），食欲下降，可能上浮"
        else:
            return f"当前水温 {t:.1f}℃ 超出{profile.name}可忍受范围（{tol_lo:.0f}-{tol_hi:.0f}℃），几乎不开口"

    def _calc_pressure_absolute_modifier(
        self, p_local: Optional[float], tags: List[str]
    ) -> int:
        """气压绝对值评分模块。[P1 新增]

        补全系统此前仅关注气压变化率而忽略绝对值的缺陷。
        低气压闷天扣分，高压晴好天加分。
        """
        if p_local is None:
            return 0

        cfg = self.pressure_abs_config

        if p_local < cfg.extreme_low:
            tags.append(TacticalTag.PRESSURE_ABS_EXTREME_LOW.value)
            return -cfg.extreme_penalty
        elif p_local < cfg.low_threshold:
            tags.append(TacticalTag.PRESSURE_ABS_LOW.value)
            return -cfg.low_penalty
        elif cfg.optimal_range[0] <= p_local <= cfg.optimal_range[1]:
            tags.append(TacticalTag.PRESSURE_ABS_OPTIMAL.value)
            return cfg.optimal_bonus
        elif p_local > cfg.high_threshold:
            tags.append(TacticalTag.PRESSURE_ABS_HIGH.value)
            return cfg.high_bonus
        else:
            return 0

    def _calc_weather_transition_modifier(
        self, hourly_forecast: Optional[List[dict]], tags: List[str]
    ) -> int:
        """天气转变检测模块（雨后效应）。[P2 新增]

        分析逐小时天气预报，检测"雨→晴"等天气转变模式。
        
        经典钓鱼场景：
          - 雨后初晴：气压回升+溶氧增加+食物被冲入水中 → 绝佳鱼情 (+10)
          - 连续阴雨3天后放晴：爆护经典场景 → 强加分 (+12)
          - 雷阵雨前1-2小时：气压急降鱼疯狂抢食 → 末日口 (+5 但高风险)

        Args:
            hourly_forecast: 逐小时天气预报列表（来自 get_hourly_forecast）
            tags: 标签列表（会追加新标签）

        Returns:
            加减分值
        """
        if not hourly_forecast or len(hourly_forecast) < 3:
            return 0

        modifier = 0

        # 将天气分为"湿"和"干"
        wet_types = {"rainy", "stormy"}
        dry_types = {"sunny", "cloudy", "overcast"}

        trends = [h.get("weather_trend", "sunny") for h in hourly_forecast]

        # ── 检测"雨后初晴"：前几小时是雨，当前/近期是晴 ──
        # 取前6小时和后6小时对比
        split = min(6, len(trends) // 2)
        if split >= 2:
            past_trends = trends[:split]
            future_trends = trends[split:split + 6]

            past_wet_ratio = sum(1 for t in past_trends if t in wet_types) / len(past_trends)
            future_dry_ratio = sum(1 for t in future_trends if t in dry_types) / len(future_trends) if future_trends else 0

            # 前半段>50%是雨，后半段>60%是晴/多云 → 雨后转晴
            if past_wet_ratio >= 0.5 and future_dry_ratio >= 0.6:
                tags.append("WEATHER_POST_RAIN_CLEAR")
                modifier += 10

                # 如果前段几乎全是雨（>80%），升级为"连续阴雨后放晴"
                if past_wet_ratio >= 0.8:
                    tags.append("WEATHER_LONG_RAIN_TO_CLEAR")
                    modifier += 2  # 额外 +2（总共 +12）

        # ── 检测"雷阵雨前末日口"：未来2-4小时有暴雨/雷暴 ──
        near_future = trends[1:5] if len(trends) >= 5 else trends[1:]
        has_storm_coming = any(t == "stormy" for t in near_future)
        current_dry = trends[0] in dry_types

        if current_dry and has_storm_coming:
            tags.append("WEATHER_STORM_APPROACHING")
            modifier += 5  # 末日口加分，但风险提示由 tactical_advice 处理

        return modifier

    # ================================================================
    #  纯天气预测模式（P0 新增）
    # ================================================================

    def predict_weather_only(
        self,
        api: ApiData,
        air_temp: float,
        lat: float = 0.0,
        lng: float = 0.0,
        hourly_forecast: Optional[List[dict]] = None,
        user_inventory: Optional[dict] = None,
    ) -> PredictionResult:
        """纯天气模式预测（无需传感器数据）。

        适用场景：钓鱼人出发前，仅凭天气+位置获取粗略建议。

        Args:
            api:              云端气象数据
            air_temp:         气温（℃）
            lat:              纬度
            lng:              经度
            hourly_forecast:  可选逐24h预报数据，用于雨后效应检测

        Returns:
            PredictionResult
        """
        tags: List[str] = []
        tags.append(TacticalTag.STAGE_WEATHER_ONLY.value)

        now_ts = int(_time.time())

        # ── 推算水温 ──
        season = get_season(now_ts, self.season_config)
        t_water_est = self.air_to_water_config.estimate_water_temp(air_temp, season)
        t_water_est = max(0.0, min(45.0, t_water_est))  # 安全钳位

        # ── 1. 水温基准达成度（平滑隶属度） ──
        base01 = self._temp_membership(t_water_est, tags)

        # ── 2. 天气加权 ──
        weather_modifier = self._calc_weather_modifier(api.weather_trend, tags)

        # ── 3. 时段加权 ──
        time_period = get_time_period(now_ts, self.period_config)
        period_modifier = self._calc_time_period_modifier(time_period, tags)

        # ── 4. 季节修正 ──
        season_modifier = self._calc_season_modifier(season, tags)

        # ── 5. 月相评分 ──
        solunar_modifier = self._calc_solunar_modifier(now_ts, tags)
        solunar_info = calc_solunar_rating(now_ts)

        # ── 6. 风向评分 ──
        wind_dir_modifier = self._calc_wind_direction_modifier(api, season, tags)

        # ── 7. 湿度评分 ──
        humidity_modifier = self._calc_humidity_modifier(api, tags)

        # ── 8. 风力等级评分 ──
        wind_speed_modifier = self._calc_wind_speed_modifier(api, tags)

        # ── 9. 溶解氧估算（用推算水温 + 天气气压） ──
        p_local_est = 1013.25  # 标准气压（天气API无此字段时兜底）
        do_est = self._calculate_do_from_values(p_local_est, t_water_est, api, tags)
        do_modifier = self._calc_do_modifier(do_est, tags)

        # ── 10. 天气转变检测（雨后效应） ── [P2 新增]
        weather_transition_modifier = self._calc_weather_transition_modifier(
            hourly_forecast, tags
        )

        # ── 11. 汇总（乘性归一模型；纯天气模式无传感器气压维度） ──
        env_scores = [
            weather_modifier, period_modifier, season_modifier,
            solunar_modifier, wind_dir_modifier, humidity_modifier,
            wind_speed_modifier, do_modifier, weather_transition_modifier,
        ]
        final_score = self._combine_score(base01, env_scores, pressure_sum=0.0, veto=False)
        self._add_rating_tag(final_score, tags)

        # ── 构建会话上下文 ──
        session = SessionContext(
            time_period=time_period,
            season=season,
            duration_seconds=0,
            report_stage="weather_only",
        )

        # ── 时段建议与季节备注 ──
        period_advice = self._generate_period_advice(
            time_period, tags, api=api
        )
        season_note = self._generate_season_note(season, tags)

        # ── 战术建议 ──
        tactical_advice = self._generate_tactical_advice(
            final_score, tags, session, api=api, user_inventory=user_inventory
        )
        tactical_advice["estimated_water_temp"] = f"{t_water_est:.1f}℃（根据气温{air_temp:.0f}℃推算）"

        return PredictionResult(
            do_trend=round(do_est, 2),
            bite_index=final_score,
            tactical_tags=tags,
            report_stage="weather_only",
            confidence=30,
            time_period_advice=period_advice,
            season_note=season_note,
            solunar_info=solunar_info,
            tactical_advice=tactical_advice,
        )

    def _calc_wind_speed_modifier(
        self, api: ApiData, tags: List[str]
    ) -> int:
        """风力等级独立评分模块。

        根据风速 m/s 分档加减分，强风时追加风险标签。
        """
        ws = api.wind_speed
        cfg = self.wind_speed_config

        modifier = 0
        for upper, score, _ in cfg.thresholds:
            if ws <= upper:
                modifier = score
                break

        # 追加标签
        if ws <= 0.5:
            tags.append(TacticalTag.WIND_SPEED_CALM.value)
        elif ws <= 3.5:
            tags.append(TacticalTag.WIND_SPEED_BREEZE.value)
        elif ws <= 8.0:
            tags.append(TacticalTag.WIND_SPEED_MODERATE.value)
        else:
            tags.append(TacticalTag.WIND_SPEED_STRONG.value)

        return modifier

