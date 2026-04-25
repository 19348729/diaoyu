"""
领域常量与配置 (Domain Constants)
=================================
将所有可调参数集中管理，便于后续从 Django settings / 配置中心注入。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Tuple


@dataclass(frozen=True)
class DissolvedOxygenConfig:
    """虚拟溶解氧估算公式的可配置系数。

    公式：DO_est ≈ P_local × (1 + k × Wind_api) / exp(α × T_water)

    Attributes:
        k:      风力增氧补偿系数，默认 0.015
                ─ 经验值：每 1 m/s 风速约提升 1.5% 溶氧
        alpha:  水温衰减系数，默认 0.035
                ─ 物理规律：水温每升高 1℃，溶氧约下降 3~4%
    """

    k: float = 0.015
    alpha: float = 0.035


@dataclass(frozen=True)
class FishSpeciesProfile:
    """目标鱼种的温度适宜区间配置。

    Attributes:
        name:              鱼种名称
        water_layer:       天生栖息水层（bottom/mid/top）
        optimal_temp:      最适水温区间 (min, max)，℃
        tolerable_temp:    可忍受水温区间 (min, max)，℃
        base_score_optimal:    落在最适区间的基准分
        base_score_tolerable:  落在可忍受区间的基准分
        base_score_outside:    超出可忍受区间的基准分
    """

    name: str = "鲫鱼"
    water_layer: str = "bottom"  # 默认底层鱼
    optimal_temp: Tuple[float, float] = (15.0, 25.0)
    tolerable_temp: Tuple[float, float] = (5.0, 32.0)
    base_score_optimal: int = 70
    base_score_tolerable: int = 40
    base_score_outside: int = 10


# ── 预设多鱼种配置库 (添加其他鱼种示例) ──
FISH_PROFILES = {
    "鲫鱼": FishSpeciesProfile(
        water_layer="bottom"
    ),
    "鲤鱼": FishSpeciesProfile(
        name="鲤鱼",
        water_layer="bottom",
        optimal_temp=(20.0, 28.0),   # 鲤鱼比鲫鱼更喜温
        tolerable_temp=(10.0, 35.0)
    ),
    "罗非鱼": FishSpeciesProfile(
        name="罗非鱼",
        water_layer="bottom",        # 罗非正常觅食在底层
        optimal_temp=(25.0, 35.0),   # 典型的热带鱼类
        tolerable_temp=(15.0, 40.0),
        base_score_optimal=75,       # 在合适的极端高温下活性可能更强
        base_score_outside=5         # 低温极其非活跃
    ),
    "大口黑鲈": FishSpeciesProfile(
        name="大口黑鲈",
        water_layer="mid",           # 路亚鱼种，通常在中下层或结构处
        optimal_temp=(20.0, 29.0),   # 调整为更真实的夏秋狂口水温
        tolerable_temp=(4.0, 32.0)
    ),
    # ── 广东及南方地区常见目标鱼 ──
    "土鲮": FishSpeciesProfile(
        name="土鲮",
        water_layer="bottom",        # 典型下口鱼，贴底刮食
        optimal_temp=(18.0, 30.0),   # 典型的亚热带鱼类，喜温怕寒
        tolerable_temp=(14.0, 32.0), # 13度以下基本停口，7度以下有冻死风险
        base_score_optimal=75,
        base_score_outside=0         # 低温完全闭口
    ),
    "草鱼": FishSpeciesProfile(
        name="草鱼",
        water_layer="mid",           # 中下层鱼，天热也会上浮
        optimal_temp=(18.0, 28.0),   # 黄金摄食温度
        tolerable_temp=(10.0, 35.0)  # 高于35度或低于10度食欲极差
    ),
    "鲢鳙": FishSpeciesProfile(
        name="鲢鳙",
        water_layer="top",           # 典型中上层滤食鱼
        optimal_temp=(25.0, 32.0),   # 极其喜高温和高溶氧，盛夏最活跃
        tolerable_temp=(15.0, 35.0), # 低于15度极难开口
        base_score_optimal=80,       # 高温期疯狂进食
        base_score_outside=5
    ),
    "塘鲺": FishSpeciesProfile(
        name="塘鲺",
        water_layer="bottom",        # 极端的底层夜行鱼
        optimal_temp=(20.0, 30.0),   # 喜温怕冷，夜间活跃
        tolerable_temp=(12.0, 38.0), # 12度开始闭口，极度耐低氧
        base_score_optimal=75,
        base_score_outside=5
    ),
    "翘嘴": FishSpeciesProfile(
        name="翘嘴",
        water_layer="top",           # 典型的中上层掠食鱼
        optimal_temp=(18.0, 30.0),   # 广温性中上层掠食鱼
        tolerable_temp=(3.0, 36.0),  # 耐寒能力极强，3度依然可能摄食
        base_score_tolerable=45      # 在非最佳水温下依然保留较强的掠食性
    ),
}


@dataclass(frozen=True)
class BiteIndexConfig:
    """开口指数计算的阈值与权重参数。

    Attributes:
        pressure_rise_bonus:      气压回升加分上限
        pressure_drop_penalty:    气压缓降扣分上限
        pressure_crash_threshold: 气压骤降阈值（hPa/2h），触发一票否决
        pressure_crash_score:     一票否决后的强制分数
        do_danger_line:           溶解氧危险线（mg/L 估算值）
        do_bonus:                 溶解氧高于危险线的加分
        do_penalty:               溶解氧低于危险线的扣分
        weather_bonus_map:        天气标签 → 额外加/扣分
    """

    pressure_rise_bonus: int = 15
    pressure_drop_penalty: int = 10
    pressure_crash_threshold: float = -3.0
    pressure_crash_score: int = 5
    do_danger_line: float = 4.0
    do_bonus: int = 10
    do_penalty: int = 15
    weather_bonus_map: dict = field(default_factory=lambda: {
        "sunny": 5,
        "cloudy": 3,
        "overcast": 0,
        "rainy": -5,
        "stormy": -15,
    })


# ──────────────────────────────────────────────
#  四时段配置
# ──────────────────────────────────────────────
@dataclass(frozen=True)
class TimePeriodConfig:
    """四时段划分与基础权重。

    早口期 (5:00-10:00) ─ 早晨气温回升，溶氧较高，鱼类活跃
    午休口 (10:00-14:00) ─ 日照强烈，表层水温升高，底层鱼不活跃
    午后开口 (14:00-18:00) ─ 水温达到峰值后开始回落，鱼类重新活跃
    晚间/夜铓 (18:00-5:00) ─ 应激口期 + 夜铓模式

    Attributes:
        periods:    时段名 -> (开始小时, 结束小时)。注意 evening 跨午夜。
        modifiers:  时段名 -> 开口分加减分
    """

    periods: Dict[str, Tuple[int, int]] = field(default_factory=lambda: {
        "morning":   (5, 10),     # 05:00 ~ 10:00
        "noon":      (10, 14),    # 10:00 ~ 14:00
        "afternoon": (14, 18),    # 14:00 ~ 18:00
        "evening":   (18, 5),     # 18:00 ~ 05:00 (跨午夜)
    })
    modifiers: Dict[str, int] = field(default_factory=lambda: {
        "morning":    8,   # 早口黄金期，加分
        "noon":      -5,   # 午休口，扣分
        "afternoon":  3,   # 午后恢复期，小幅加分
        "evening":   10,   # 傍晚爆口期，加分最多
    })


# ──────────────────────────────────────────────
#  四季节配置
# ──────────────────────────────────────────────
@dataclass(frozen=True)
class SeasonConfig:
    """四季节的铓鱼影响配置。

    每个季节包含：
      - score_modifier: 开口分加减
      - optimal_temp_shift: 对鱼种最适温度的季节性偏移（℃）
      - advice: 季节性铓鱼建议文案

    Attributes:
        months_map:       季节名 -> 包含的月份列表
        season_modifiers:  季节名 -> {配置参数}
    """

    months_map: Dict[str, Tuple[int, ...]] = field(default_factory=lambda: {
        "spring": (3, 4, 5),
        "summer": (6, 7, 8),
        "autumn": (9, 10, 11),
        "winter": (12, 1, 2),
    })
    season_modifiers: Dict[str, dict] = field(default_factory=lambda: {
        "spring": {
            "score_modifier": 5,
            "optimal_temp_shift": -2.0,    # 春季水温偏低，鱼对稍低温度更敏感
            "advice": "春季回暖期，鱼类经过冬天休眠后急需补充能量，食欲逐渐增强。"
              "建议铓浅滩向阳处，使用腔味饵料。",
        },
        "summer": {
            "score_modifier": -3,
            "optimal_temp_shift": 0.0,
            "advice": "盛夏高温期，水面温度过高，底层鱼可能转移至深水或荐草区。"
              "建议早晚作铓，避开正午高温时段。",
        },
        "autumn": {
            "score_modifier": 8,
            "optimal_temp_shift": 1.0,     # 秋季降温前鱼类抢食肥秋，对稍高温度仍有食欲
            "advice": "秋季肥秋期，鱼类为越冬抢食储能，食欲旺盛，是全年最佳作铓季节。"
              "全天候均可作铓，营养型饵料效果极佳。",
        },
        "winter": {
            "score_modifier": -8,
            "optimal_temp_shift": 0.0,
            "advice": "冬季低温期，鱼类代谢放缓，开口轻、吃口小。"
              "建议重腔味小钩细线，铓向阳深水区，午后升温后作铓。",
        },
    })


# ──────────────────────────────────────────────
#  渐进式报告阶段配置
# ──────────────────────────────────────────────
@dataclass(frozen=True)
class ProgressiveStageConfig:
    """渐进式报告阶段定义。

    随着连接时长增加，提供递进式的分析深度：
      - instant:  0s+，仅基于最新单帧，置信度 30%
      - brief:    300s (5min)+，含气压趋势 + 温度趋势，置信度 55%
      - standard: 600s (10min)+，含完整趋势分析，置信度 75%
      - full:     1800s (30min)+，含深度时序分析 + 高置信度建议，置信度 90%

    Attributes:
        stages: 阶段名 -> {min_seconds, confidence, features}
    """

    stages: Dict[str, dict] = field(default_factory=lambda: {
        "instant": {
            "min_seconds": 0,
            "confidence": 30,
            "features": ["base_score", "pressure_snapshot"],
        },
        "brief": {
            "min_seconds": 300,     # 5 分钟
            "confidence": 55,
            "features": ["base_score", "pressure_trend", "temp_trend"],
        },
        "standard": {
            "min_seconds": 600,     # 10 分钟
            "confidence": 75,
            "features": ["base_score", "pressure_trend", "temp_trend",
                         "thermocline", "do_estimate"],
        },
        "full": {
            "min_seconds": 1800,    # 30 分钟
            "confidence": 90,
            "features": ["base_score", "pressure_trend", "temp_trend",
                         "thermocline", "do_estimate", "deep_analysis",
                         "time_period_advice", "season_advice"],
        },
    })


# ──────────────────────────────────────────────
#  温跃层阈值配置
# ──────────────────────────────────────────────
@dataclass(frozen=True)
class ThermoclineConfig:
    """温跃层（表底温差）分析配置。

    Attributes:
        strong_threshold:  强温跃层阈值（℃）─ 表底温差 > 此值视为明显分层
        weak_threshold:    弱温跃层阈值（℃）
        inversion_threshold: 逆温阈值（底层 > 表层，差值超过此值）
        strong_penalty:    强温跃层扣分
        inversion_penalty: 逆温扣分
    """

    strong_threshold: float = 3.0
    weak_threshold: float = 1.0
    inversion_threshold: float = 1.5
    strong_penalty: int = 8
    inversion_penalty: int = 10
