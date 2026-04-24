"""
值对象层 (Value Objects)
========================
定义所有领域内的不可变数据载体，包含入参与出参。
遵循 DDD 中 Value Object 的设计原则：无身份标识、不可变、自校验。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


# ──────────────────────────────────────────────
#  入参：边缘硬件数据
# ──────────────────────────────────────────────
@dataclass(frozen=True)
class HardwareData:
    """来自边缘设备（传感器/气象站）的实测数据。

    Attributes:
        t_water:  深层实测水温（℃），合理范围 0 ~ 45
        p_local:  本地绝对气压（hPa），合理范围 900 ~ 1100
        delta_p:  过去 2 小时气压变化率（hPa/2h），正值=升压，负值=降压
    """

    t_water: float
    p_local: float
    delta_p: float

    def __post_init__(self) -> None:
        if not (0.0 <= self.t_water <= 45.0):
            raise ValueError(
                f"t_water 超出合理范围 [0, 45]：{self.t_water}"
            )
        if not (900.0 <= self.p_local <= 1100.0):
            raise ValueError(
                f"p_local 超出合理范围 [900, 1100]：{self.p_local}"
            )


# ──────────────────────────────────────────────
#  入参：云端气象 API 数据
# ──────────────────────────────────────────────
@dataclass(frozen=True)
class ApiData:
    """来自云端气象服务的补充数据。

    Attributes:
        wind_speed:     风速（m/s），用于推算风力等级及增氧修正
        altitude:       海拔（米），用于修正标准气压
        weather_trend:  短临天气标签，枚举值示例：
                        "sunny" / "cloudy" / "rainy" / "stormy" / "overcast"
    """

    wind_speed: float
    altitude: float
    weather_trend: str

    # 允许的天气标签白名单（可按需扩展）
    _VALID_TRENDS = frozenset(
        {"sunny", "cloudy", "rainy", "stormy", "overcast"}
    )

    def __post_init__(self) -> None:
        if self.wind_speed < 0:
            raise ValueError(
                f"wind_speed 不能为负：{self.wind_speed}"
            )
        if self.altitude < 0:
            raise ValueError(
                f"altitude 不能为负：{self.altitude}"
            )
        if self.weather_trend not in self._VALID_TRENDS:
            raise ValueError(
                f"weather_trend 不在白名单中：{self.weather_trend}，"
                f"允许值：{self._VALID_TRENDS}"
            )


# ──────────────────────────────────────────────
#  出参：预测结果
# ──────────────────────────────────────────────
@dataclass(frozen=True)
class PredictionResult:
    """多因子融合预测的最终输出。

    Attributes:
        do_trend:       虚拟溶解氧指数（mg/L 量纲的估算值）
        bite_index:     最终开口评分（0-100，整数）
        tactical_tags:  触发的战术标签集合，供下游 Agent 组装话术
    """

    do_trend: float
    bite_index: int
    tactical_tags: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not (0 <= self.bite_index <= 100):
            raise ValueError(
                f"bite_index 超出 [0, 100] 范围：{self.bite_index}"
            )
