/**
 * 战术标签 (Tactical Tags) 汉化映射表
 * 用于将后端返回的枚举字符串翻译为前端易懂的中文
 */
const TAG_MAP = {
  // ── 气压相关 ──
  STATUS_PRESSURE_RISING: "气压回升",
  STATUS_PRESSURE_STABLE: "气压平稳",
  STATUS_PRESSURE_DROPPING: "气压下降",
  STATUS_PRESSURE_CRASH: "气压骤降 (难开口)",

  // ── 溶氧相关 ──
  STATUS_DO_RICH: "溶氧极佳",
  STATUS_DO_HEALTHY: "溶氧正常",
  STATUS_DO_MARGINAL: "溶氧偏低 (建议钓浮)",
  STATUS_DO_DANGER: "严重缺氧 (极易翻坑)",

  // ── 水温相关 ──
  STATUS_TEMP_OPTIMAL: "水温极佳",
  STATUS_TEMP_TOLERABLE: "水温适宜",
  STATUS_TEMP_EXTREME_HOT: "极端高温 (需避暑)",
  STATUS_TEMP_EXTREME_COLD: "极端低温 (需避寒)",
  STATUS_TEMP_RISING: "水温回升期",
  STATUS_TEMP_DROPPING: "水温骤降期",

  // ── 天气与风力相关 ──
  STATUS_WEATHER_FAVORABLE: "天气适宜",
  STATUS_WEATHER_ADVERSE: "天气恶劣",
  STATUS_WIND_CALM: "无风 (注意防缺氧)",
  STATUS_WIND_SUITABLE: "微风增氧",
  STATUS_WIND_STRONG: "大风 (抛竿看漂难)",

  // ── 具体战术建议 ──
  TACTIC_FISH_SHALLOW_BANK: "建议钓浅滩",
  TACTIC_FISH_DEEP_POOL: "建议钓深坑",
  TACTIC_FISH_BOTTOM: "建议钓底",
  TACTIC_FISH_MID: "建议打行程/钓半水",
  TACTIC_FISH_TOP: "建议钓浮/打水皮",
  TACTIC_FISH_SUSPENDED: "鱼上浮 (建议离底)",
  TACTIC_NIGHT_FISHING: "建议夜钓/早晚",
  TACTIC_USE_STRONG_FLAVOR: "建议重腥味/活饵",

  // ── 综合评级 ──
  RATING_EXCELLENT: "🏆 综合极佳",
  RATING_GOOD: "🌟 综合良好",
  RATING_FAIR: "👍 综合一般",
  RATING_POOR: "⚠️ 综合较差",
  RATING_VETO: "❌ 不宜作钓",

  // ── 时段标签 ──
  PERIOD_MORNING_GOLDEN: "🌅 早口黄金期",
  PERIOD_NOON_REST: "☀️ 午休停口期",
  PERIOD_AFTERNOON_ACTIVE: "🌤️ 午后活跃期",
  PERIOD_EVENING_PEAK: "🌆 傍晚爆口期",
  PERIOD_NIGHT_SPECIAL: "🌙 夜钓模式",

  // ── 季节标签 ──
  SEASON_SPRING_WARMING: "🌸 春季回暖",
  SEASON_SUMMER_HEAT: "🌞 盛夏高温",
  SEASON_AUTUMN_COOLING: "🍂 秋季降温",
  SEASON_WINTER_COLD: "❄️ 冬季严寒",

  // ── 温跃层/分层标签 ──
  STATUS_THERMOCLINE_STRONG: "温跃层明显 (表底温差大)",
  STATUS_THERMOCLINE_WEAK: "温跃层较弱",
  STATUS_TEMP_INVERSION: "水底反温 (底层比表层暖)",

  // ── 趋势标签 ──
  TREND_PRESSURE_RISING_SLOW: "气压缓慢回升",
  TREND_TEMP_STABLE: "水温稳定",
  TREND_IMPROVING: "📈 鱼情趋好",
  TREND_DETERIORATING: "📉 鱼情趋差",

  // ── 月相 ──
  SOLUNAR_NEW_MOON: "🌑 新月 (适宜作钓)",
  SOLUNAR_FULL_MOON: "🌕 满月 (适宜作钓)",
  SOLUNAR_FIRST_QUARTER: "🌓 上弦月",
  SOLUNAR_LAST_QUARTER: "🌗 下弦月",
  SOLUNAR_WAXING: "渐盈期",
  SOLUNAR_WANING: "渐亏期",

  // ── 突变标签 ──
  PRESSURE_SHORT_DROP: "气压急降",
  PRESSURE_SHORT_SPIKE: "气压急升",
  PRESSURE_HIGH_VOLATILITY: "气压大幅波动",
  TEMP_RAPID_RISE: "水温急升",
  TEMP_RAPID_DROP: "水温急降",

  // ── 风向/湿度 ──
  STATUS_WIND_DIRECTION_FAVORABLE: "风向有利",
  STATUS_WIND_DIRECTION_ADVERSE: "风向不利",
  STATUS_HUMIDITY_MUGGY: "闷热高湿",
  STATUS_HUMIDITY_NORMAL: "湿度正常",

  // ── 阶段标签 ──
  STAGE_INSTANT: "速报数据",
  STAGE_BRIEF: "简略分析",
  STAGE_STANDARD: "标准分析",
  STAGE_FULL: "深度分析",
  STAGE_WEATHER_ONLY: "📡 纯天气模式",

  // ── 风速等级 (P0) ──
  WIND_SPEED_CALM: "🍃 无风",
  WIND_SPEED_BREEZE: "🍃 微风宜钓",
  WIND_SPEED_MODERATE: "💨 中等风力",
  WIND_SPEED_STRONG: "🌬️ 大风预警",

  // ── 气压绝对值 (P1) ──
  PRESSURE_ABS_EXTREME_LOW: "⛔ 气压极低 (<990hPa)",
  PRESSURE_ABS_LOW: "⚠️ 气压偏低",
  PRESSURE_ABS_OPTIMAL: "✅ 气压最适",
  PRESSURE_ABS_HIGH: "气压偏高",

  // ── 天气转变 (P2) ──
  WEATHER_POST_RAIN_CLEAR: "🎉 雨后初晴",
  WEATHER_LONG_RAIN_TO_CLEAR: "🔥 久雨放晴",
  WEATHER_STORM_APPROACHING: "⚡ 雷暴逼近",

  // ── 温跃层单探头 ──
  THERMOCLINE_SINGLE_SENSOR: "单水温探头模式",
  THERMAL_WELL_MIXED: "水体混合良好"
};

/**
 * 翻译标签数组
 * @param {Array<string>} tags 英文标签数组
 * @returns {Array<string>} 翻译后的中文标签数组
 */
function translateTags(tags) {
  if (!tags || !Array.isArray(tags)) return [];
  // 翻译并在字典中找不到时保留原词
  return tags.map(tag => TAG_MAP[tag] || tag);
}

module.exports = {
  translateTags
};
