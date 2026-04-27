"""
月相与 Solunar 计算模块 (Solunar Calculator)
===============================================
纯天文算法，零外部依赖。

基于 Solunar Theory (John Alden Knight, 1926)：
  - 月亮的位置（月中天/月对冲/月出/月落）会影响鱼类活跃度
  - 新月和满月期间潮汐力最强，鱼类活跃度最高

月相计算使用简化的天文算法（Conway 方法的改进版），
精度约 ±1 天，对钓鱼预测已足够。
"""
from __future__ import annotations

import math
from datetime import datetime, timezone, timedelta
from typing import Tuple

# 东八区
_CST = timezone(timedelta(hours=8))

# 已知的一个新月时刻（J2000 参考点）
# 2000-01-06 18:14 UTC（新月）
_KNOWN_NEW_MOON_JD = 2451550.1   # 对应的儒略日
_SYNODIC_MONTH = 29.53058868     # 朔望月周期（天）


def _to_julian_day(timestamp: int) -> float:
    """将 Unix 时间戳转换为儒略日。"""
    return timestamp / 86400.0 + 2440587.5


def calc_moon_age(timestamp: int) -> float:
    """计算月龄（自上一个新月以来的天数）。

    Args:
        timestamp: Unix 时间戳（秒）

    Returns:
        月龄（天），范围 [0, 29.53)
    """
    jd = _to_julian_day(timestamp)
    days_since = jd - _KNOWN_NEW_MOON_JD
    moon_age = days_since % _SYNODIC_MONTH
    if moon_age < 0:
        moon_age += _SYNODIC_MONTH
    return moon_age


def calc_moon_phase(timestamp: int) -> Tuple[str, float]:
    """计算月相名称和月龄。

    Args:
        timestamp: Unix 时间戳（秒）

    Returns:
        (月相名称, 月龄天数)

    月相划分（8 个阶段）：
        new_moon:        0.0 ~ 1.85 天
        waxing_crescent: 1.85 ~ 7.38 天
        first_quarter:   7.38 ~ 11.07 天
        waxing_gibbous:  11.07 ~ 14.77 天
        full_moon:       14.77 ~ 16.61 天
        waning_gibbous:  16.61 ~ 22.15 天
        last_quarter:    22.15 ~ 25.84 天
        waning_crescent: 25.84 ~ 29.53 天
    """
    age = calc_moon_age(timestamp)
    fraction = age / _SYNODIC_MONTH  # 0.0 ~ 1.0

    # 8 等分，每段 0.125，但新月和满月窗口稍宽
    if fraction < 0.0625 or fraction >= 0.9375:
        phase = "new_moon"
    elif fraction < 0.25:
        phase = "waxing_crescent"
    elif fraction < 0.375:
        phase = "first_quarter"
    elif fraction < 0.5:
        phase = "waxing_gibbous"
    elif fraction < 0.5625:
        phase = "full_moon"
    elif fraction < 0.75:
        phase = "waning_gibbous"
    elif fraction < 0.875:
        phase = "last_quarter"
    else:
        phase = "waning_crescent"

    return phase, round(age, 2)


def calc_moon_illumination(timestamp: int) -> float:
    """估算月球光照百分比（0~100%）。

    使用简化的余弦模型：
        illumination = (1 - cos(2π × age / synodic_month)) / 2 × 100

    Args:
        timestamp: Unix 时间戳（秒）

    Returns:
        光照百分比 0.0 ~ 100.0
    """
    age = calc_moon_age(timestamp)
    phase_angle = 2 * math.pi * age / _SYNODIC_MONTH
    illumination = (1 - math.cos(phase_angle)) / 2 * 100
    return round(illumination, 1)


def is_solunar_peak_day(timestamp: int) -> bool:
    """判断是否是 Solunar 高峰日（新月或满月前后 2 天）。

    Args:
        timestamp: Unix 时间戳（秒）

    Returns:
        True 表示处于新月/满月 ±2 天窗口内
    """
    age = calc_moon_age(timestamp)
    half_cycle = _SYNODIC_MONTH / 2

    # 距新月（age ≈ 0 或 ≈ 29.53）
    dist_new = min(age, _SYNODIC_MONTH - age)
    # 距满月（age ≈ 14.77）
    dist_full = abs(age - half_cycle)

    return dist_new <= 2.0 or dist_full <= 2.0


def calc_solunar_rating(timestamp: int) -> dict:
    """综合 Solunar 评估。

    Returns:
        {
            "phase": str,           # 月相名称
            "moon_age": float,      # 月龄（天）
            "illumination": float,  # 光照百分比
            "is_peak_day": bool,    # 是否高峰日
        }
    """
    phase, age = calc_moon_phase(timestamp)
    illum = calc_moon_illumination(timestamp)
    peak = is_solunar_peak_day(timestamp)

    return {
        "phase": phase,
        "moon_age": age,
        "illumination": illum,
        "is_peak_day": peak,
    }
