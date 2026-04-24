"""
领域服务层 (Domain Services)
============================
封装跨值对象的纯业务逻辑。高内聚、低耦合。
纯面向对象，不依赖任何数据库或外部框架，方便被 Django Service 层直接调用。
"""
import math
from typing import List, Tuple

from .value_objects import HardwareData, ApiData, PredictionResult
from .constants import DissolvedOxygenConfig, FishSpeciesProfile, BiteIndexConfig
from .tags import TacticalTag


class FishingPredictionService:
    """AI 钓鱼多因子融合预测核心服务类。
    
    负责数据的综合计算、虚拟溶解氧的推演、以及最终开口指数（0-100）的综合评价，
    并生成供 Agent 组装话术的战术标签。
    """

    def __init__(
        self,
        do_config: DissolvedOxygenConfig = None,
        fish_profile: FishSpeciesProfile = None,
        bite_config: BiteIndexConfig = None,
    ):
        """支持依赖注入配置，方便针对不同水域/鱼种动态实例化。"""
        self.do_config = do_config or DissolvedOxygenConfig()
        self.fish_profile = fish_profile or FishSpeciesProfile()
        self.bite_config = bite_config or BiteIndexConfig()

    def predict(self, hardware: HardwareData, api: ApiData) -> PredictionResult:
        """执行核心预测流程，输出最终预测结果。"""
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
