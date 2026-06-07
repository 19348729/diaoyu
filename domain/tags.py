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

    # ── 时段标签 ──
    PERIOD_MORNING_GOLDEN = "PERIOD_MORNING_GOLDEN"      # 早口黄金期（5:00-10:00）
    PERIOD_NOON_REST = "PERIOD_NOON_REST"                # 午休口（10:00-14:00）
    PERIOD_AFTERNOON_ACTIVE = "PERIOD_AFTERNOON_ACTIVE"  # 午后开口期（14:00-18:00）
    PERIOD_EVENING_PEAK = "PERIOD_EVENING_PEAK"          # 傍晚爆口期（18:00-22:00）
    PERIOD_NIGHT_SPECIAL = "PERIOD_NIGHT_SPECIAL"        # 夜钓模式（22:00-5:00）

    # ── 季节标签 ──
    SEASON_SPRING_WARMING = "SEASON_SPRING_WARMING"      # 春季回暖期
    SEASON_SUMMER_HEAT = "SEASON_SUMMER_HEAT"            # 盛夏高温期
    SEASON_AUTUMN_COOLING = "SEASON_AUTUMN_COOLING"      # 秋季肥秋期
    SEASON_WINTER_COLD = "SEASON_WINTER_COLD"            # 冬季严寒期

    # ── 温跃层/分层标签 ──
    STATUS_THERMOCLINE_STRONG = "STATUS_THERMOCLINE_STRONG"  # 温跃层明显（表底温差>3℃）
    STATUS_THERMOCLINE_WEAK = "STATUS_THERMOCLINE_WEAK"      # 温跃层弱（表底温差1~3℃）
    STATUS_TEMP_INVERSION = "STATUS_TEMP_INVERSION"          # 逆温现象（底层温度>表层）

    # ── 趋势标签 ──
    TREND_PRESSURE_RISING_SLOW = "TREND_PRESSURE_RISING_SLOW"    # 气压缓慢回升
    TREND_TEMP_STABLE = "TREND_TEMP_STABLE"                      # 水温稳定
    TREND_IMPROVING = "TREND_IMPROVING"                          # 鱼情转好
    TREND_DETERIORATING = "TREND_DETERIORATING"                  # 鱼情转差

    # ── 月相 / Solunar 标签 ──
    SOLUNAR_NEW_MOON = "SOLUNAR_NEW_MOON"              # 新月（最佳钓鱼日之一）
    SOLUNAR_FULL_MOON = "SOLUNAR_FULL_MOON"            # 满月（最佳钓鱼日之一）
    SOLUNAR_FIRST_QUARTER = "SOLUNAR_FIRST_QUARTER"    # 上弦月（鱼口一般）
    SOLUNAR_LAST_QUARTER = "SOLUNAR_LAST_QUARTER"      # 下弦月（鱼口一般）
    SOLUNAR_WAXING = "SOLUNAR_WAXING"                  # 渐盈期
    SOLUNAR_WANING = "SOLUNAR_WANING"                  # 渐亏期


    # ── 短期气压突变标签 ──
    PRESSURE_SHORT_DROP = "PRESSURE_SHORT_DROP"        # 15~30分钟内气压急降
    PRESSURE_SHORT_SPIKE = "PRESSURE_SHORT_SPIKE"      # 15~30分钟内气压急升
    PRESSURE_HIGH_VOLATILITY = "PRESSURE_HIGH_VOLATILITY"  # 气压波动剧烈

    # ── 温度速率标签 ──
    TEMP_RAPID_RISE = "TEMP_RAPID_RISE"                # 水温快速上升（>1.5℃/h）
    TEMP_RAPID_DROP = "TEMP_RAPID_DROP"                # 水温快速下降（>1.5℃/h）

    # ── 风向标签 ──
    STATUS_WIND_DIRECTION_FAVORABLE = "STATUS_WIND_DIRECTION_FAVORABLE"  # 风向有利
    STATUS_WIND_DIRECTION_ADVERSE = "STATUS_WIND_DIRECTION_ADVERSE"      # 风向不利（东风等）

    # ── 湿度标签 ──
    STATUS_HUMIDITY_MUGGY = "STATUS_HUMIDITY_MUGGY"    # 闷热高湿（>85%），溶氧可能偏低
    STATUS_HUMIDITY_NORMAL = "STATUS_HUMIDITY_NORMAL"  # 湿度正常

    # ── 三层水温空间分布标签 ──
    THERMAL_WELL_MIXED = "THERMAL_WELL_MIXED"          # 水体混合良好（温差<1℃）
    THERMAL_LAYERS_DIVERGING = "THERMAL_LAYERS_DIVERGING"  # 各层温度趋势分化
    THERMOCLINE_SINGLE_SENSOR = "THERMOCLINE_SINGLE_SENSOR"  # V2 单水温探头，无法分析温跃层

    # ── 报告阶段标签 ──
    STAGE_INSTANT = "STAGE_INSTANT"        # 速报阶段
    STAGE_BRIEF = "STAGE_BRIEF"            # 简报阶段（5min+）
    STAGE_STANDARD = "STAGE_STANDARD"      # 标准报告（10min+）
    STAGE_FULL = "STAGE_FULL"              # 完整报告（30min+）
    STAGE_WEATHER_ONLY = "STAGE_WEATHER_ONLY"  # 纯天气模式（无传感器）

    # ── 风力等级标签（基于 WindSpeedConfig 分档） ──
    WIND_SPEED_CALM = "WIND_SPEED_CALM"          # 无风（0~0.5 m/s）
    WIND_SPEED_BREEZE = "WIND_SPEED_BREEZE"      # 微风（最适宜）
    WIND_SPEED_MODERATE = "WIND_SPEED_MODERATE"  # 中风（看漂受影响）
    WIND_SPEED_STRONG = "WIND_SPEED_STRONG"      # 强风/大风（建议取消）

    # ── 气压绝对值标签 ──
    PRESSURE_ABS_EXTREME_LOW = "PRESSURE_ABS_EXTREME_LOW"  # 极端低压（<990 hPa）
    PRESSURE_ABS_LOW = "PRESSURE_ABS_LOW"                  # 低气压（<1000 hPa）
    PRESSURE_ABS_OPTIMAL = "PRESSURE_ABS_OPTIMAL"          # 最适气压（1005-1020 hPa）
    PRESSURE_ABS_HIGH = "PRESSURE_ABS_HIGH"                # 高气压（>1025 hPa）

    # ── 天气转变标签 ──
    WEATHER_POST_RAIN_CLEAR = "WEATHER_POST_RAIN_CLEAR"          # 雨后初晴（绝佳鱼情）
    WEATHER_LONG_RAIN_TO_CLEAR = "WEATHER_LONG_RAIN_TO_CLEAR"    # 连续阴雨后放晴（爆护天气）
    WEATHER_STORM_APPROACHING = "WEATHER_STORM_APPROACHING"      # 雷阵雨逼近（末日口）

    # ── 预报趋势标签（逐时预报推导，无传感器也可用）── [P3 新增]
    WEATHER_COOLING = "WEATHER_COOLING"                # 未来降温（鱼口转差）
    WEATHER_COOLING_STRONG = "WEATHER_COOLING_STRONG"  # 未来强降温/寒潮（应激停口）
    WEATHER_WARMING = "WEATHER_WARMING"                # 未来回暖（活性回升）
    WEATHER_RAIN_RISING = "WEATHER_RAIN_RISING"        # 未来持续降雨/涨水
