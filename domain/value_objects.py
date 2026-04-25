"""
值对象层 (Value Objects)
========================
定义所有领域内的不可变数据载体，包含入参与出参。
遵循 DDD 中 Value Object 的设计原则：无身份标识、不可变、自校验。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple


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
#  入参：传感器单条读数（与小程序 protocol.js 实时帧对齐）
# ──────────────────────────────────────────────
@dataclass(frozen=True)
class SensorReading:
    """来自 ESP32 的单条传感器读数。

    Attributes:
        timestamp:  Unix 时间戳（秒）
        t_bottom:   水底温度（3m），可为 None
        t_mid:      水下1米温度，可为 None
        t_surface:  水面温度，可为 None
        p_local:    本地绝对气压（hPa），可为 None
    """

    timestamp: int
    t_bottom: Optional[float] = None
    t_mid: Optional[float] = None
    t_surface: Optional[float] = None
    p_local: Optional[float] = None


@dataclass(frozen=True)
class SensorTimeSeries:
    """传感器时序数据集（小程序上报的历史 + 实时数据汇总）。

    Attributes:
        readings:  按时间升序排列的传感器读数列表
    """

    readings: Tuple[SensorReading, ...] = field(default_factory=tuple)

    @property
    def latest(self) -> Optional[SensorReading]:
        """最新一条读数。"""
        return self.readings[-1] if self.readings else None

    @property
    def earliest(self) -> Optional[SensorReading]:
        """最早一条读数。"""
        return self.readings[0] if self.readings else None

    @property
    def duration_seconds(self) -> int:
        """数据跨度（秒）。"""
        if len(self.readings) < 2:
            return 0
        return self.readings[-1].timestamp - self.readings[0].timestamp

    @property
    def count(self) -> int:
        return len(self.readings)


@dataclass(frozen=True)
class SessionContext:
    """会话上下文：时段、季节、连接时长、报告阶段。

    Attributes:
        time_period:      当前时段 "morning"/"noon"/"afternoon"/"evening"
        season:           当前季节 "spring"/"summer"/"autumn"/"winter"
        duration_seconds: 已连续采集时长（秒）
        report_stage:     报告阶段 "instant"/"brief"/"standard"/"full"
    """

    time_period: str
    season: str
    duration_seconds: int
    report_stage: str


# ──────────────────────────────────────────────
#  出参：预测结果
# ──────────────────────────────────────────────
@dataclass(frozen=True)
class PredictionResult:
    """多因子融合预测的最终输出。

    Attributes:
        do_trend:            虚拟溶解氧指数（mg/L 量纲的估算值）
        bite_index:          最终开口评分（0-100，整数）
        tactical_tags:       触发的战术标签集合，供下游 Agent 组装话术
        report_stage:        报告阶段 "instant"/"brief"/"standard"/"full"
        confidence:          置信度（0-100），随采集时长递增
        time_period_advice:  时段建议文案
        season_note:         季节备注
    """

    do_trend: float
    bite_index: int
    tactical_tags: List[str] = field(default_factory=list)
    report_stage: str = "instant"
    confidence: int = 30
    time_period_advice: str = ""
    season_note: str = ""

    def __post_init__(self) -> None:
        if not (0 <= self.bite_index <= 100):
            raise ValueError(
                f"bite_index 超出 [0, 100] 范围：{self.bite_index}"
            )
