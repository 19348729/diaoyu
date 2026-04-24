"""
战术标签枚举 (Tactical Tags)
============================
可被下游 Agent 消费的结构化状态标签。
每个标签代表一条可解释的钓鱼策略信号。
"""
from enum import Enum


class TacticalTag(str, Enum):
    """战术标签枚举。

    继承 str 使其可直接 JSON 序列化，方便下游 API 使用。
    """

    # ── 气压相关 ──
    STATUS_PRESSURE_RISING = "STATUS_PRESSURE_RISING"
    STATUS_PRESSURE_STABLE = "STATUS_PRESSURE_STABLE"
    STATUS_PRESSURE_DROPPING = "STATUS_PRESSURE_DROPPING"
    STATUS_PRESSURE_CRASH = "STATUS_PRESSURE_CRASH"

    # ── 溶氧相关 ──
    STATUS_DO_RICH = "STATUS_DO_RICH"          # 溶氧极佳（如风大、刚下过雨）
    STATUS_DO_HEALTHY = "STATUS_DO_HEALTHY"    # 溶氧正常
    STATUS_DO_MARGINAL = "STATUS_DO_MARGINAL"  # 溶氧偏低（鱼可能上浮，建议钓浮）
    STATUS_DO_DANGER = "STATUS_DO_DANGER"      # 溶氧危险（极易翻坑，一票否决）

    # ── 水温相关 ──
    STATUS_TEMP_OPTIMAL = "STATUS_TEMP_OPTIMAL"
    STATUS_TEMP_TOLERABLE = "STATUS_TEMP_TOLERABLE"
    STATUS_TEMP_EXTREME_HOT = "STATUS_TEMP_EXTREME_HOT"    # 极端高温（需避暑）
    STATUS_TEMP_EXTREME_COLD = "STATUS_TEMP_EXTREME_COLD"  # 极端低温（需避寒）
    STATUS_TEMP_RISING = "STATUS_TEMP_RISING"              # 水温回升期
    STATUS_TEMP_DROPPING = "STATUS_TEMP_DROPPING"          # 水温骤降期

    # ── 天气与风力相关 ──
    STATUS_WEATHER_FAVORABLE = "STATUS_WEATHER_FAVORABLE"
    STATUS_WEATHER_ADVERSE = "STATUS_WEATHER_ADVERSE"
    STATUS_WIND_CALM = "STATUS_WIND_CALM"                  # 无风（可能导致溶氧低）
    STATUS_WIND_SUITABLE = "STATUS_WIND_SUITABLE"          # 微风（最适宜，增氧）
    STATUS_WIND_STRONG = "STATUS_WIND_STRONG"              # 大风（抛竿困难，看漂难，走水）

    # ── 🎣 具体战术建议 (Tactics) ──
    # 地形选择（钓多深的水）
    TACTIC_FISH_SHALLOW_BANK = "TACTIC_FISH_SHALLOW_BANK"  # 建议钓浅滩（如春季连续晴天回暖，鱼上滩觅食）
    TACTIC_FISH_DEEP_POOL = "TACTIC_FISH_DEEP_POOL"        # 建议钓深水/深坑（如极寒避寒、盛夏避暑）
    
    # 水层选择（饵料在水下什么位置）
    TACTIC_FISH_BOTTOM = "TACTIC_FISH_BOTTOM"              # 建议钓底（针对底层鱼，或天气寒冷鱼贴底）
    TACTIC_FISH_MID = "TACTIC_FISH_MID"                    # 建议钓中层/打行程（针对草鱼、鳊鱼等）
    TACTIC_FISH_TOP = "TACTIC_FISH_TOP"                    # 建议钓浮/打水皮（针对鲢鳙、翘嘴等中上层鱼）
    TACTIC_FISH_SUSPENDED = "TACTIC_FISH_SUSPENDED"        # 建议钓离底/半水（异常天气：因气压低/缺氧导致的底层鱼被迫上浮）
    
    # 时机与用饵
    TACTIC_NIGHT_FISHING = "TACTIC_NIGHT_FISHING"          # 建议夜钓或早晚作钓（盛夏极端高温）
    TACTIC_USE_STRONG_FLAVOR = "TACTIC_USE_STRONG_FLAVOR"  # 建议重腥味/活饵（低温期鱼口轻，促开口）

    # ── 综合评级 ──
    RATING_EXCELLENT = "RATING_EXCELLENT"
    RATING_GOOD = "RATING_GOOD"
    RATING_FAIR = "RATING_FAIR"
    RATING_POOR = "RATING_POOR"
    RATING_VETO = "RATING_VETO"
