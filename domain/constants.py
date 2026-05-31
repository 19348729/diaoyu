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
    """目标鱼种的温度适宜区间配置 + 专属战术建议。

    Attributes:
        name:              鱼种名称
        water_layer:       天生栖息水层（bottom/mid/top）
        optimal_temp:      最适水温区间 (min, max)，℃
        tolerable_temp:    可忍受水温区间 (min, max)，℃
        base_score_optimal:    落在最适区间的基准分
        base_score_tolerable:  落在可忍受区间的基准分
        base_score_outside:    超出可忍受区间的基准分
        bait_by_season:    季节 → 推荐饵料（鱼种专属）
        default_layer_advice:  默认水层建议文案（空则按 water_layer 自动生成）
        fishing_method:    作钓方式：台钓 / 路亚 / 筏钓
    """

    name: str = "鲫鱼"
    water_layer: str = "bottom"  # 默认底层鱼
    optimal_temp: Tuple[float, float] = (15.0, 25.0)
    tolerable_temp: Tuple[float, float] = (5.0, 32.0)
    base_score_optimal: int = 70
    base_score_tolerable: int = 40
    base_score_outside: int = 10
    bait_by_season: Dict[str, str] = field(default_factory=lambda: {
        "spring": "腥香饵，适当加拉丝粉",
        "summer": "谷物本味清淡饵，减少雾化",
        "autumn": "浓腥浓香饵，加大雾化",
        "winter": "红虫/蚯蚓活饵，或极腥拉饵",
    })
    default_layer_advice: str = "钓底为主，口轻时上推浮漂钓灵"
    fishing_method: str = "台钓"


# ── 预设多鱼种配置库 ──
FISH_PROFILES = {
    "鲫鱼": FishSpeciesProfile(
        water_layer="bottom",
        bait_by_season={
            "spring": "腥香饵，适当加拉丝粉",
            "summer": "谷物本味清淡饵，减少雾化",
            "autumn": "浓腥浓香饵，加大雾化",
            "winter": "红虫/蚯蚓活饵，或极腥拉饵",
        },
        default_layer_advice="钓底为主，口轻时上推浮漂钓灵",
    ),
    "鲤鱼": FishSpeciesProfile(
        name="鲤鱼",
        water_layer="bottom",
        optimal_temp=(20.0, 28.0),
        tolerable_temp=(10.0, 35.0),
        bait_by_season={
            "spring": "螺鲤+腥香基础饵",
            "summer": "发酵玉米粒/谷物本味",
            "autumn": "薯味+螺肉饵，加大窝量",
            "winter": "红虫颗粒+腥味商品饵",
        },
        default_layer_advice="钓底守大物，子线放长",
    ),
    "罗非鱼": FishSpeciesProfile(
        name="罗非鱼",
        water_layer="bottom",
        optimal_temp=(25.0, 35.0),
        tolerable_temp=(15.0, 40.0),
        base_score_optimal=75,
        base_score_outside=5,
        bait_by_season={
            "spring": "冻料+虾粉",
            "summer": "冻料/肝味饵/挂虾肉",
            "autumn": "冻料+赤尾青",
            "winter": "虾肉/活虾挂钩，重腥",
        },
        default_layer_advice="钓底，挂虾肉效果极佳",
    ),
    "大口黑鲈": FishSpeciesProfile(
        name="大口黑鲈",
        water_layer="mid",
        optimal_temp=(20.0, 29.0),
        tolerable_temp=(4.0, 32.0),
        bait_by_season={
            "spring": "软虫(T尾/卷尾) Texas钓组",
            "summer": "Crankbait/Spinnerbait，搜索结构区",
            "autumn": "米诺/VIB 快速搜索",
            "winter": "铅头钩+软虫，慢拖底",
        },
        default_layer_advice="搜索中下层结构区（水草/石堆/倒树）",
        fishing_method="路亚",
    ),
    # ── 广东及南方地区常见目标鱼 ──
    "土鲮": FishSpeciesProfile(
        name="土鲮",
        water_layer="bottom",
        optimal_temp=(18.0, 30.0),
        tolerable_temp=(14.0, 32.0),
        base_score_optimal=75,
        base_score_outside=0,
        bait_by_season={
            "spring": "花生枯+南北鲮，搓饵",
            "summer": "花生枯+甜味添加剂",
            "autumn": "花生枯+九一八",
            "winter": "不建议作钓（14℃以下基本停口）",
        },
        default_layer_advice="必须钓底（下口鱼，贴底刮食）",
    ),
    "草鱼": FishSpeciesProfile(
        name="草鱼",
        water_layer="mid",
        optimal_temp=(18.0, 28.0),
        tolerable_temp=(10.0, 35.0),
        bait_by_season={
            "spring": "嫩玉米/嫩草尖",
            "summer": "鲜嫩玉米粒/芦苇芯/南瓜藤",
            "autumn": "老玉米粒/发酵玉米",
            "winter": "不建议作钓（低温极不活跃）",
        },
        default_layer_advice="中下层为主，高温天钓半水或钓浮",
    ),
    "鲢鳙": FishSpeciesProfile(
        name="鲢鳙",
        water_layer="top",
        optimal_temp=(25.0, 32.0),
        tolerable_temp=(15.0, 35.0),
        base_score_optimal=80,
        base_score_outside=5,
        bait_by_season={
            "spring": "酸臭饵，增加雾化（水温>18℃方可）",
            "summer": "酸臭发酵饵+蒜味，强雾化",
            "autumn": "酸甜饵+草莓香精",
            "winter": "不建议作钓（15℃以下极难开口）",
        },
        default_layer_advice="钓浮 1.5-3 米，搜索中上层",
    ),
    "塘鲺": FishSpeciesProfile(
        name="塘鲺",
        water_layer="bottom",
        optimal_temp=(20.0, 30.0),
        tolerable_temp=(12.0, 38.0),
        base_score_optimal=75,
        base_score_outside=5,
        bait_by_season={
            "spring": "鸡肝/蚯蚓",
            "summer": "鸡肝/鸭肝/腥味重饵",
            "autumn": "鸡肝/活虾",
            "winter": "蚯蚓/鸡肝（仅限夜间有口）",
        },
        default_layer_advice="钓底，夜间出钓效果最佳",
    ),
    "翘嘴": FishSpeciesProfile(
        name="翘嘴",
        water_layer="top",
        optimal_temp=(18.0, 30.0),
        tolerable_temp=(3.0, 36.0),
        base_score_tolerable=45,
        bait_by_season={
            "spring": "亮片/米诺，慢收",
            "summer": "亮片/波趴/铅笔，清晨傍晚水面系",
            "autumn": "米诺/VIB，中速搜索",
            "winter": "VIB/金属饵，慢速跳底",
        },
        default_layer_advice="搜索中上层，fan cast 扇形覆盖",
        fishing_method="路亚",
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
    # 危险线按“实际溶氧估算”（含高温缺氧折减）标定，使盛夏高温能真正触发缺氧判定
    do_danger_line: float = 5.5
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


# ──────────────────────────────────────────────
#  溶解氧饱和度查找表（Benson & Krause 标准）
# ──────────────────────────────────────────────
# 标准大气压（1013.25 hPa）下，纯淡水中的溶解氧饱和浓度 (mg/L)
# 数据来源：USGS DOTABLES / Benson & Krause (1984)
DO_SAT_TABLE: dict = {
    0: 14.62, 1: 14.22, 2: 13.83, 3: 13.46, 4: 13.11,
    5: 12.77, 6: 12.45, 7: 12.14, 8: 11.84, 9: 11.56,
    10: 11.29, 11: 11.03, 12: 10.78, 13: 10.54, 14: 10.31,
    15: 10.08, 16: 9.87, 17: 9.67, 18: 9.47, 19: 9.28,
    20: 9.09, 21: 8.92, 22: 8.74, 23: 8.58, 24: 8.42,
    25: 8.26, 26: 8.11, 27: 7.97, 28: 7.83, 29: 7.69,
    30: 7.56, 31: 7.43, 32: 7.31, 33: 7.18, 34: 7.07,
    35: 6.95, 36: 6.84, 37: 6.73, 38: 6.62, 39: 6.52,
    40: 6.41,
}


def interpolate_do_saturation(t_water: float) -> float:
    """从查找表中线性插值获取指定水温下的饱和溶解氧。

    Args:
        t_water: 水温（℃），范围 0~40

    Returns:
        标准大气压下的饱和溶解氧 (mg/L)
    """
    t_clamped = max(0.0, min(40.0, t_water))
    t_low = int(t_clamped)
    t_high = min(t_low + 1, 40)

    if t_low == t_high:
        return DO_SAT_TABLE[t_low]

    frac = t_clamped - t_low
    return DO_SAT_TABLE[t_low] + frac * (DO_SAT_TABLE[t_high] - DO_SAT_TABLE[t_low])


# ──────────────────────────────────────────────
#  Solunar 月相评分配置
# ──────────────────────────────────────────────
@dataclass(frozen=True)
class SolunarConfig:
    """月相 (Solunar) 对鱼类活跃度的影响配置。

    基于 Solunar Theory（John Alden Knight, 1926）：
    新月和满月期间，潮汐力最强，鱼类活跃度最高。

    Attributes:
        phase_modifiers:     月相名称 → 开口分加减分
        major_period_bonus:  处于大口期时的额外加分
        minor_period_bonus:  处于小口期时的额外加分
    """

    phase_modifiers: Dict[str, int] = field(default_factory=lambda: {
        "new_moon": 8,           # 新月：潮汐力最强，鱼口最好
        "waxing_crescent": 3,
        "first_quarter": -2,     # 上弦月：潮汐力最弱
        "waxing_gibbous": 2,
        "full_moon": 8,          # 满月：潮汐力最强
        "waning_gibbous": 3,
        "last_quarter": -2,      # 下弦月：潮汐力最弱
        "waning_crescent": 2,
    })
    major_period_bonus: int = 5   # 大口期（月中天/月对冲）额外加分
    minor_period_bonus: int = 3   # 小口期（月出/月落）额外加分


# ──────────────────────────────────────────────
#  多窗口气压分析配置
# ──────────────────────────────────────────────
@dataclass(frozen=True)
class PressureAnalysisConfig:
    """多窗口气压分析参数。

    Attributes:
        windows:            分析窗口列表 (秒)
        short_drop_threshold:   短窗口(15min)气压急降阈值 (hPa)
        short_spike_threshold:  短窗口(15min)气压急升阈值 (hPa)
        volatility_threshold:   波动标准差阈值 (hPa)
        short_drop_penalty:     短期急降扣分
        short_spike_bonus:      短期急升加分
        volatility_penalty:     高波动扣分
    """

    windows: Tuple[int, ...] = (900, 1800, 3600, 7200)  # 15min, 30min, 1h, 2h
    short_drop_threshold: float = -1.5   # 15min 内降 1.5hPa 视为急降
    short_spike_threshold: float = 1.5   # 15min 内升 1.5hPa 视为急升
    volatility_threshold: float = 1.0    # 1h 内标准差 > 1.0 hPa 视为高波动
    short_drop_penalty: int = 8
    short_spike_bonus: int = 5
    volatility_penalty: int = 5


# ──────────────────────────────────────────────
#  风向配置
# ──────────────────────────────────────────────
@dataclass(frozen=True)
class WindDirectionConfig:
    """风向 × 季节组合评分矩阵。

    中国钓鱼谚语："东风不钓鱼，西风钓鱼勤"。
    北风降温鱼下底，南风回暖促开口。

    Attributes:
        direction_modifiers:  风向 → 基础加减分
        season_overrides:     (风向, 季节) → 覆盖分数（优先级高于基础分）
    """

    direction_modifiers: Dict[str, int] = field(default_factory=lambda: {
        "N": -3,      # 北风：降温，鱼活性降低
        "NE": -2,
        "E": -5,      # 东风：最不利钓鱼的风向
        "SE": 0,
        "S": 3,       # 南风：回暖，促开口
        "SW": 4,      # 西南风：最适宜
        "W": 2,       # 西风
        "NW": -1,     # 西北风：降温但氧气充足
    })
    season_overrides: Dict[Tuple[str, str], int] = field(default_factory=lambda: {
        # (风向, 季节) → 覆盖分数
        ("N", "winter"): -6,     # 冬季北风雪上加霜
        ("S", "winter"): 6,      # 冬季南风回暖是强正面信号
        ("N", "summer"): 2,      # 夏季北风降温反而好（解暑）
        ("S", "summer"): -3,     # 夏季南风闷热，溶氧低
        ("SW", "summer"): -2,    # 夏季西南风闷热
    })


# ──────────────────────────────────────────────
#  湿度配置
# ──────────────────────────────────────────────
@dataclass(frozen=True)
class HumidityConfig:
    """湿度对鱼情的影响配置。

    高湿度通常伴随低气压、闷热，水体溶氧差。

    Attributes:
        muggy_threshold:  闷热阈值（%），高于此值触发扣分
        muggy_penalty:    闷热扣分
        comfort_range:    舒适湿度范围
    """

    muggy_threshold: float = 85.0
    muggy_penalty: int = 5
    comfort_range: Tuple[float, float] = (40.0, 75.0)


# ──────────────────────────────────────────────
#  风速评分配置
# ──────────────────────────────────────────────
@dataclass(frozen=True)
class WindSpeedConfig:
    """风速（m/s）对作钓体验和鱼情的影响。

    分档：
      0 ~ 0.5 m/s   无风，水面缺氧，扣分
      0.5 ~ 3.5      微风，最适宜，加分
      3.5 ~ 5.5      轻风，稍有走水
      5.5 ~ 8.0      中风，看漂受影响
      8.0 ~ 10.5     强风，手竿困难
      > 10.5         大风，建议取消出钓

    Attributes:
        thresholds: 每档 (上限 m/s, 加减分, 描述)
    """

    thresholds: Tuple[Tuple[float, int, str], ...] = (
        (0.5,  -3, "无风，水面缺氧"),
        (3.5,   5, "微风，最适宜"),
        (5.5,   2, "轻风，稍有走水"),
        (8.0,  -5, "中风，看漂受影响"),
        (10.5, -12, "强风，手竿困难"),
        (99.0, -25, "大风，建议取消出钓"),
    )


# ──────────────────────────────────────────────
#  气压绝对值评分配置
# ──────────────────────────────────────────────
@dataclass(frozen=True)
class PressureAbsoluteConfig:
    """气压绝对值对鱼情的影响。

    钓鱼人常说"闷天不上鱼"，气压绝对值偏低往往意味着闷热、
    溶氧差，鱼口极差。本配置补全了系统此前仅关注气压变化率
    而忽略绝对值的缺陷。

    Attributes:
        extreme_low:     极端低压阈值（hPa），如台风前兆
        extreme_penalty: 极端低压扣分
        low_threshold:   低压阈值
        low_penalty:     低压扣分
        optimal_range:   最适气压范围
        high_threshold:  高压阈值（晴好天气利好）
        high_bonus:      高压加分
    """

    extreme_low: float = 990.0
    extreme_penalty: int = 15      # 极端低压，几乎不可能有口
    low_threshold: float = 1000.0
    low_penalty: int = 8           # 低气压闷天，鱼口差
    optimal_range: Tuple[float, float] = (1005.0, 1020.0)
    optimal_bonus: int = 3         # 最适气压范围加分
    high_threshold: float = 1025.0
    high_bonus: int = 2            # 高压晴好天，轻微利好


# ──────────────────────────────────────────────
#  气温推算水温配置
# ──────────────────────────────────────────────
@dataclass(frozen=True)
class AirToWaterConfig:
    """纯天气模式下，用气温估算水温的季节性偏移。

    水温通常低于气温，偏差受季节和水体热容量影响。
    春夏水温落后于气温（偏差大），秋冬水体保温（偏差小）。

    Attributes:
        season_offset: 季节 → (偏移下限, 偏移上限)，取均值使用
    """

    season_offset: Dict[str, Tuple[float, float]] = field(default_factory=lambda: {
        "spring": (2.0, 4.0),   # 春季水温明显低于气温
        "summer": (2.0, 3.0),   # 夏季日晒强但水体蓄热
        "autumn": (1.0, 2.0),   # 秋季水体缓慢散热
        "winter": (0.5, 1.5),   # 冬季水温反而高于气温（水体保温）
    })

    def estimate_water_temp(self, air_temp: float, season: str) -> float:
        """用气温估算水温。"""
        offsets = self.season_offset.get(season, (2.0, 3.0))
        avg_offset = (offsets[0] + offsets[1]) / 2
        return air_temp - avg_offset

