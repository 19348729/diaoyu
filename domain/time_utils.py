"""
时间工具模块 (Time Utilities)
==============================
提供时段判断、季节判断、报告阶段判断等时间相关的工具函数。
"""
from __future__ import annotations

import time as _time
from datetime import datetime, timezone, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .value_objects import SensorReading, SessionContext

from .constants import (
    TimePeriodConfig,
    SeasonConfig,
    ProgressiveStageConfig,
)

# 默认使用东八区（北京时间）
_CST = timezone(timedelta(hours=8))

# 默认配置单例
_DEFAULT_PERIOD_CFG = TimePeriodConfig()
_DEFAULT_SEASON_CFG = SeasonConfig()
_DEFAULT_STAGE_CFG = ProgressiveStageConfig()


def get_time_period(timestamp: int, config: TimePeriodConfig = None) -> str:
    """根据 Unix 时间戳判断当前处于哪个时段。

    Args:
        timestamp: Unix 时间戳（秒）
        config:    时段配置，默认使用 TimePeriodConfig()

    Returns:
        时段名: "morning" / "noon" / "afternoon" / "evening"
    """
    cfg = config or _DEFAULT_PERIOD_CFG
    dt = datetime.fromtimestamp(timestamp, tz=_CST)
    hour = dt.hour

    for period_name, (start, end) in cfg.periods.items():
        if start < end:
            # 不跨午夜：如 morning (5, 10) -> 5 <= hour < 10
            if start <= hour < end:
                return period_name
        else:
            # 跨午夜：如 evening (18, 5) -> hour >= 18 或 hour < 5
            if hour >= start or hour < end:
                return period_name

    # 兜底（理论上不会到达，因为 evening 覆盖了剩余时间）
    return "evening"


def get_season(timestamp: int, config: SeasonConfig = None) -> str:
    """根据 Unix 时间戳判断当前季节。

    Args:
        timestamp: Unix 时间戳（秒）
        config:    季节配置，默认使用 SeasonConfig()

    Returns:
        季节名: "spring" / "summer" / "autumn" / "winter"
    """
    cfg = config or _DEFAULT_SEASON_CFG
    dt = datetime.fromtimestamp(timestamp, tz=_CST)
    month = dt.month

    for season_name, months in cfg.months_map.items():
        if month in months:
            return season_name

    return "spring"  # 兜底


def get_report_stage(duration_seconds: int, config: ProgressiveStageConfig = None) -> str:
    """根据已连续采集时长判断报告阶段。

    阶段按 min_seconds 降序匹配，取满足条件的最高阶段。

    Args:
        duration_seconds: 已采集时长（秒）
        config:           阶段配置

    Returns:
        阶段名: "instant" / "brief" / "standard" / "full"
    """
    cfg = config or _DEFAULT_STAGE_CFG

    # 按 min_seconds 降序排序，匹配第一个满足条件的阶段
    sorted_stages = sorted(
        cfg.stages.items(),
        key=lambda x: x[1]["min_seconds"],
        reverse=True,
    )

    for stage_name, stage_info in sorted_stages:
        if duration_seconds >= stage_info["min_seconds"]:
            return stage_name

    return "instant"


def get_confidence(duration_seconds: int, config: ProgressiveStageConfig = None) -> int:
    """根据采集时长获取当前置信度。"""
    cfg = config or _DEFAULT_STAGE_CFG
    stage_name = get_report_stage(duration_seconds, cfg)
    return cfg.stages[stage_name]["confidence"]


def get_stage_features(duration_seconds: int, config: ProgressiveStageConfig = None) -> list:
    """根据采集时长获取当前阶段启用的分析特征。"""
    cfg = config or _DEFAULT_STAGE_CFG
    stage_name = get_report_stage(duration_seconds, cfg)
    return cfg.stages[stage_name]["features"]


def build_session_context(
    readings: list,
    period_config: TimePeriodConfig = None,
    season_config: SeasonConfig = None,
    stage_config: ProgressiveStageConfig = None,
) -> "SessionContext":
    """从传感器读数列表自动构建会话上下文。

    Args:
        readings: SensorReading 列表（按时间升序）
        period_config: 时段配置
        season_config: 季节配置
        stage_config:  阶段配置

    Returns:
        SessionContext 值对象
    """
    from .value_objects import SessionContext

    if not readings:
        now_ts = int(_time.time())
        return SessionContext(
            time_period=get_time_period(now_ts, period_config),
            season=get_season(now_ts, season_config),
            duration_seconds=0,
            report_stage="instant",
        )

    latest_ts = readings[-1].timestamp
    earliest_ts = readings[0].timestamp
    duration = latest_ts - earliest_ts if len(readings) > 1 else 0

    return SessionContext(
        time_period=get_time_period(latest_ts, period_config),
        season=get_season(latest_ts, season_config),
        duration_seconds=duration,
        report_stage=get_report_stage(duration, stage_config),
    )
