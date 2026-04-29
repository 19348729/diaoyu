/**
 * 后端 API 通信模块
 * 负责将传感器数据上报到后端服务，获取预测结果
 */

const app = getApp();

/**
 * 获取后端 API 基础地址
 */
function getBaseUrl() {
  return app.globalData.apiBaseUrl;
}

/**
 * 通用请求封装
 * @param {string} path - API 路径
 * @param {string} method - HTTP 方法
 * @param {object} data - 请求数据
 * @returns {Promise<object>}
 */
function request(path, method = 'POST', data = {}) {
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${getBaseUrl()}${path}`,
      method,
      header: {
        'Content-Type': 'application/json',
        'X-OpenID': app.globalData.openid || '',
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
 * 获取用户的钓鱼会话历史
 * @param {number} limit - 返回条数
 * @returns {Promise<object>}
 */
function getSessionHistory(limit = 10) {
  return request(`/sessions?limit=${limit}`, 'GET');
}

module.exports = {
  reportRealtimeData,
  reportHistoryBatch,
  getPrediction,
  getPredictionReport,
  getSessionHistory,
};
