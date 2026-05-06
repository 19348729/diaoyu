/**
 * 获取后端 API 基础地址
 */
function getBaseUrl() {
  const app = getApp();
  return (app && app.globalData && app.globalData.apiBaseUrl) || 'https://ks.gzbaoge.com/api';
}

function request(path, method = 'POST', data = {}) {
  const app = getApp();
  // 优先从全局变量获取，如果没有则尝试从缓存恢复（兜底）
  let openid = '';
  if (app && app.globalData && app.globalData.openid) {
    openid = app.globalData.openid;
  } else {
    openid = wx.getStorageSync('openid') || '';
  }

  return new Promise((resolve, reject) => {
    wx.request({
      url: `${getBaseUrl()}${path}`,
      method,
      header: {
        'Content-Type': 'application/json',
        'X-OpenID': openid,
      },
      data,
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data);
        } else {
          reject(new Error(`HTTP ${res.statusCode}: ${JSON.stringify(res.data)}`));
        }
      },
      fail: (err) => {
        reject(new Error(`网络请求失败: ${err.errMsg}`));
      },
    });
  });
}

/**
 * 上报实时传感器数据
 * @param {object} sensorData - 传感器数据
 * @param {number} sensorData.timestamp - Unix 时间戳
 * @param {number|null} sensorData.tBottom - 水底温度
 * @param {number|null} sensorData.tMid - 水下1米温度
 * @param {number|null} sensorData.tSurface - 水面温度
 * @param {number|null} sensorData.pLocal - 气压
 * @param {object} [location] - 位置信息
 * @returns {Promise<object>}
 */
function reportRealtimeData(sensorData, location = null) {
  return request('/sensor/realtime', 'POST', {
    ...sensorData,
    location,
  });
}

/**
 * 批量上报历史传感器数据
 * @param {Array} records - 历史数据数组
 * @param {object} [location] - 位置信息
 * @returns {Promise<object>}
 */
function reportHistoryBatch(records, location = null) {
  return request('/sensor/history', 'POST', {
    records,
    location,
  });
}

/**
 * 获取预测结果
 * @param {Array} sensors - 传感器历史数据数组
 * @param {number} lat - 纬度
 * @param {number} lng - 经度
 * @param {string} fishType - 目标鱼种名称
 * @returns {Promise<object>} 预测结果
 */
function getPrediction(sensors, lat, lng, fishType = 'auto') {
  const formattedSensors = sensors.map(s => ({
    timestamp: s.timestamp,
    t_bottom: s.tBottom !== undefined ? s.tBottom : null,
    t_mid: s.tMid !== undefined ? s.tMid : null,
    t_surface: s.tSurface !== undefined ? s.tSurface : null,
    p_local: s.pLocal !== undefined ? s.pLocal : null
  }));

  return request('/predict', 'POST', {
    fish_type: fishType,
    sensors: formattedSensors,
    lat: lat,
    lng: lng,
    altitude: 0
  });
}

/**
 * 获取预测报告（含渐进式阶段信息）
 * @param {string} fishType - 目标鱼种
 * @returns {Promise<object>}
 */
function getPredictionReport(fishType = '鲫鱼') {
  return request('/predict/report', 'POST', {
    fishType,
  });
}

/**
 * 获取用户的智能作钓预测日志
 * @param {number} limit - 返回条数
 * @returns {Promise<object>}
 */
function getPredictionLogs(limit = 20) {
  return request(`/history/logs?limit=${limit}`, 'GET');
}

/**
 * 纯天气预测（出发前决策，无需传感器）
 * @param {number} lat - 纬度
 * @param {number} lng - 经度
 * @param {string} fishType - 目标鱼种（'auto' 全鱼种排行）
 * @returns {Promise<object>} 预测结果
 */
function getWeatherPredict(lat, lng, fishType = 'auto') {
  return request('/predict/weather', 'POST', {
    lat,
    lng,
    fish_type: fishType,
  });
}

/**
 * 获取今日逐小时鱼情预报
 * @param {number} lat - 纬度
 * @param {number} lng - 经度
 * @param {string} fishType - 目标鱼种
 * @returns {Promise<object>} { daily_summary, best_windows, hourly_scores }
 */
function getForecastToday(lat, lng, fishType = '鲫鱼') {
  return request(`/forecast/today?lat=${lat}&lng=${lng}&fish_type=${encodeURIComponent(fishType)}`, 'GET');
}

/**
 * 获取未来 3 天鱼情日历
 * @param {number} lat - 纬度
 * @param {number} lng - 经度
 * @param {string} fishType - 目标鱼种
 * @returns {Promise<object>} { best_day, best_day_score, days, comparison }
 */
function getForecast3Day(lat, lng, fishType = '鲫鱼') {
  return request(`/forecast/3day?lat=${lat}&lng=${lng}&fish_type=${encodeURIComponent(fishType)}`, 'GET');
}

module.exports = {
  reportRealtimeData,
  reportHistoryBatch,
  getPrediction,
  getPredictionReport,
  getPredictionLogs,
  getWeatherPredict,
  getForecastToday,
  getForecast3Day,
};
