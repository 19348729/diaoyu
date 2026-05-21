/**
 * 出钓决策页面
 * 纯天气模式，帮助钓鱼人出发前判断"今天值不值得去"
 */
const api = require('../../utils/api');
const { translateTags } = require('../../utils/tagMap');

Page({
  data: {
    loading: false,
    hasResult: false,

    // 今日概况
    overallScore: 0,
    overallRating: '',
    ratingCn: '',
    peakHour: 0,
    peakScore: 0,

    // 最佳窗口
    bestWindows: [],

    // 推荐鱼种
    recommendedFish: '',
    fishRanking: [],
    weatherInfo: null,
    tacticalAdvice: null,
    tacticalTags: [],
    biteIndex: 0,
    confidence: 0,

    // 3天日历
    calendar: null,
    calendarDays: [],

    // 逐时评分（简化展示）
    hourlyScores: [],

    // 鱼种选择
    fishTypes: ['auto', '鲫鱼', '鲤鱼', '罗非鱼', '鲢鳙', '草鱼', '翘嘴', '土鲮', '塘鲺', '大口黑鲈'],
    fishTypeNames: ['智能推荐', '鲫鱼', '鲤鱼', '罗非鱼', '鲢鳙', '草鱼', '翘嘴', '土鲮', '塘鲺', '大口黑鲈'],
    selectedFishIndex: 0,
  },

  onLoad() {
    this.fetchDecision();
  },

  onPullDownRefresh() {
    this.fetchDecision().then(() => {
      wx.stopPullDownRefresh();
    });
  },

  onFishTypeChange(e) {
    this.setData({ selectedFishIndex: e.detail.value });
    this.fetchDecision();
  },

  async fetchDecision() {
    this.setData({ loading: true });

    try {
      const location = await this._getLocation();
      const lat = location.latitude;
      const lng = location.longitude;
      const fishType = this.data.fishTypes[this.data.selectedFishIndex];

      // 并发请求 3 个接口
      const [weatherResult, forecastResult, calendarResult] = await Promise.all([
        api.getWeatherPredict(lat, lng, fishType),
        api.getForecastToday(lat, lng, fishType === 'auto' ? '鲫鱼' : fishType),
        api.getForecast3Day(lat, lng, fishType === 'auto' ? '鲫鱼' : fishType),
      ]);

      // 解析天气预测结果
      const ds = forecastResult.daily_summary || {};

      this.setData({
        loading: false,
        hasResult: true,

        // 今日概况
        overallScore: ds.overall_score || 0,
        overallRating: ds.overall_rating || 'fair',
        ratingCn: ds.rating_cn || '--',
        peakHour: ds.peak_hour || 0,
        peakScore: ds.peak_score || 0,

        // 最佳窗口
        bestWindows: forecastResult.best_windows || [],

        // 天气预测结果
        recommendedFish: weatherResult.recommended_fish || '',
        fishRanking: (weatherResult.recommended_fishes || []).slice(0, 5),
        weatherInfo: weatherResult.weather_info || null,
        tacticalAdvice: weatherResult.tactical_advice || null,
        tacticalTags: translateTags(weatherResult.tactical_tags || []),
        biteIndex: weatherResult.bite_index || 0,
        confidence: weatherResult.confidence || 30,

        // 3天日历
        calendar: calendarResult,
        calendarDays: calendarResult.days || [],

        // 逐时评分
        hourlyScores: forecastResult.hourly_scores || [],
      });
    } catch (e) {
      console.error('[Decision] 获取决策数据失败:', e);
      wx.showToast({ title: '获取失败，请重试', icon: 'none' });
      this.setData({ loading: false });
    }
  },

  _getLocation() {
    return new Promise((resolve, reject) => {
      wx.getLocation({
        type: 'wgs84',
        success: resolve,
        fail: (err) => {
          console.error('[Decision] 定位失败:', err);
          wx.showToast({ title: '定位失败', icon: 'error' });
          reject(err);
        },
      });
    });
  },
});
