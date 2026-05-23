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
 * 上报实时传感器数据 (v2)
 * @param {object} sensorData - 传感器数据
 * @param {number} sensorData.timestamp - Unix 时间戳
 * @param {number|null} sensorData.tWater - 水温
 * @param {number|null} sensorData.tAir - 气温
 * @param {number|null} sensorData.pLocal - 气压
 * @param {object} [location] - 位置信息
 * @returns {Promise<object>}
 */
function reportRealtimeData(sensorData, location = null) {
  return request('/sensor/realtime', 'POST', {
    sensor: {
      timestamp: sensorData.timestamp,
      t_water: sensorData.tWater !== undefined ? sensorData.tWater : null,
      t_air: sensorData.tAir !== undefined ? sensorData.tAir : null,
      p_local: sensorData.pLocal !== undefined ? sensorData.pLocal : null
    },
    lat: location ? location.lat : 0.0,
    lng: location ? location.lng : 0.0
  });
}

/**
 * 批量上报历史传感器数据 (v2)
 * @param {Array} records - 历史数据数组
 * @param {object} [location] - 位置信息
 * @returns {Promise<object>}
 */
function reportHistoryBatch(records, location = null) {
  const formattedRecords = records.map(s => ({
    timestamp: s.timestamp,
    t_water: s.tWater !== undefined ? s.tWater : null,
    t_air: s.tAir !== undefined ? s.tAir : null,
    p_local: s.pLocal !== undefined ? s.pLocal : null
  }));

  return request('/sensor/history', 'POST', {
    records: formattedRecords,
    lat: location ? location.lat : 0.0,
    lng: location ? location.lng : 0.0
  });
}

/**
 * 获取预测结果 (v2)
 * @param {Array} sensors - 传感器历史数据数组
 * @param {number} lat - 纬度
 * @param {number} lng - 经度
 * @param {string} fishType - 目标鱼种名称
 * @returns {Promise<object>} 预测结果
 */
function getPrediction(sensors, lat, lng, fishType = 'auto') {
  const formattedSensors = sensors.map(s => ({
    timestamp: s.timestamp,
    t_water: s.tWater !== undefined ? s.tWater : null,
    t_air: s.tAir !== undefined ? s.tAir : null,
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

/**
 * 拉取最近的传感器历史记录（用于重启恢复趋势图）
 * @param {number} limit - 返回条数，默认 1440
 * @returns {Promise<object>}
 */
function getSensorRecords(limit = 1440) {
  return request(`/sensor/records?limit=${limit}`, 'GET');
}

/**
 * 保存钓鱼会话摘要（一次出钓 = 一条记录）
 * @param {object} sessionData - 会话聚合数据
 * @returns {Promise<object>}
 */
function saveSession(sessionData) {
  return request('/session/save', 'POST', sessionData);
}

/**
 * 获取钓鱼会话日志列表
 * @param {number} limit - 返回条数
 * @returns {Promise<object>}
 */
function getSessionList(limit = 20) {
  return request(`/session/list?limit=${limit}`, 'GET');
}

/**
 * AI 鱼情救场 (V2)
 * @param {Array} sensors 
 * @param {Array} symptomTags 
 * @param {object} fishContext 
 * @param {number} lat 
 * @param {number} lng 
 * @param {object} [userInventory] - 用户数字钓箱快照 {rods, mainLines, subLineHooks, floats, baits}
 * @returns {Promise<object>}
 */
function getAiRescue(sensors, symptomTags, fishContext, lat, lng, userInventory) {
  const formattedSensors = sensors.map(s => ({
    timestamp: s.timestamp,
    t_water: s.tWater !== undefined ? s.tWater : null,
    t_air: s.tAir !== undefined ? s.tAir : null,
    p_local: s.pLocal !== undefined ? s.pLocal : null
  }));
  return request('/v2/rescue', 'POST', {
    sensors: formattedSensors,
    symptom_tags: symptomTags,
    fish_context: fishContext,
    lat,
    lng,
    user_inventory: userInventory || null
  });
}

/**
 * 一次性拉取数字钓箱全量装备，组装成后端期望的 user_inventory 结构
 * 钓鱼实战：装备库即出钓清单（钓友习惯全部带上）
 * @returns {Promise<object>} {rods, mainLines, subLineHooks, floats, baits}
 */
function getUserInventoryAll() {
  return Promise.all([
    getUserRods().catch(() => ({ data: [] })),
    getUserMainLines().catch(() => ({ data: [] })),
    getUserSubLineHooks().catch(() => ({ data: [] })),
    getUserFloats().catch(() => ({ data: [] })),
    getUserBaits().catch(() => ({ data: [] })),
  ]).then(([rodsRes, mlRes, slRes, flRes, btRes]) => ({
    rods: (rodsRes && rodsRes.data) || [],
    mainLines: (mlRes && mlRes.data) || [],
    subLineHooks: (slRes && slRes.data) || [],
    floats: (flRes && flRes.data) || [],
    baits: (btRes && btRes.data) || [],
  }));
}

/**
 * 获取战报海报数据 (V2)
 * @param {number} sessionId 
 * @returns {Promise<object>}
 */
function getPoster(sessionId) {
  return request(`/v2/poster/${sessionId}`, 'GET');
}

/**
 * 获取官方支持的鱼竿品牌与系列库
 * @returns {Promise<object>}
 */
function getRodDatabase() {
  return request('/inventory/rods', 'GET');
}

/**
 * 用户录入新的鱼竿到私有钓箱
 * @param {object} rodData 
 * @returns {Promise<object>}
 */
function addUserRod(rodData) {
  return request('/inventory/rod', 'POST', rodData);
}

/**
 * 获取用户钓箱里现有的所有鱼竿
 * @returns {Promise<object>}
 */
function getUserRods() {
  return request('/inventory/rods/user', 'GET');
}

/**
 * 获取单根鱼竿详情
 * @param {number|string} rodId 
 * @returns {Promise<object>}
 */
function getUserRod(rodId) {
  const cleanId = typeof rodId === 'string' && rodId.startsWith('r') ? rodId.substring(1) : rodId;
  return request(`/inventory/rod/${cleanId}`, 'GET');
}

/**
 * 修改用户私有钓箱中的鱼竿
 * @param {number|string} rodId 
 * @param {object} rodData 
 * @returns {Promise<object>}
 */
function updateUserRod(rodId, rodData) {
  const cleanId = typeof rodId === 'string' && rodId.startsWith('r') ? rodId.substring(1) : rodId;
  return request(`/inventory/rod/${cleanId}`, 'PUT', rodData);
}

/**
 * 从用户私有钓箱中删除鱼竿
 * @param {number|string} rodId 
 * @returns {Promise<object>}
 */
function deleteUserRod(rodId) {
  const cleanId = typeof rodId === 'string' && rodId.startsWith('r') ? rodId.substring(1) : rodId;
  return request(`/inventory/rod/${cleanId}`, 'DELETE');
}

/**
 * 获取用户钓箱里现有的所有主线
 * @returns {Promise<object>}
 */
function getUserMainLines() {
  return request('/inventory/mainlines/user', 'GET');
}

/**
 * 用户录入新的主线到私有钓箱
 * @param {object} mainlineData 
 * @returns {Promise<object>}
 */
function addUserMainLine(mainlineData) {
  return request('/inventory/mainline', 'POST', mainlineData);
}

/**
 * 获取单条主线详情
 * @param {number|string} mainlineId 
 * @returns {Promise<object>}
 */
function getUserMainLine(mainlineId) {
  const cleanId = typeof mainlineId === 'string' && mainlineId.startsWith('m') ? mainlineId.substring(1) : mainlineId;
  return request(`/inventory/mainline/${cleanId}`, 'GET');
}

/**
 * 修改用户私有钓箱中的主线
 * @param {number|string} mainlineId 
 * @param {object} mainlineData 
 * @returns {Promise<object>}
 */
function updateUserMainLine(mainlineId, mainlineData) {
  const cleanId = typeof mainlineId === 'string' && mainlineId.startsWith('m') ? mainlineId.substring(1) : mainlineId;
  return request(`/inventory/mainline/${cleanId}`, 'PUT', mainlineData);
}

/**
 * 从用户私有钓箱中删除主线
 * @param {number|string} mainlineId 
 * @returns {Promise<object>}
 */
function deleteUserMainLine(mainlineId) {
  const cleanId = typeof mainlineId === 'string' && mainlineId.startsWith('m') ? mainlineId.substring(1) : mainlineId;
  return request(`/inventory/mainline/${cleanId}`, 'DELETE');
}

/**
 * 获取用户钓箱里现有的所有子线双钩
 * @returns {Promise<object>}
 */
function getUserSubLineHooks() {
  return request('/inventory/sublinehooks/user', 'GET');
}

/**
 * 用户录入新的子线双钩到私有钓箱
 * @param {object} sublineData 
 * @returns {Promise<object>}
 */
function addUserSubLineHook(sublineData) {
  return request('/inventory/sublinehook', 'POST', sublineData);
}

/**
 * 获取单条子线双钩详情
 * @param {number|string} sublineId 
 * @returns {Promise<object>}
 */
function getUserSubLineHook(sublineId) {
  const cleanId = typeof sublineId === 'string' && sublineId.startsWith('s') ? sublineId.substring(1) : sublineId;
  return request(`/inventory/sublinehook/${cleanId}`, 'GET');
}

/**
 * 修改用户私有钓箱中的子线双钩
 * @param {number|string} sublineId 
 * @param {object} sublineData 
 * @returns {Promise<object>}
 */
function updateUserSubLineHook(sublineId, sublineData) {
  const cleanId = typeof sublineId === 'string' && sublineId.startsWith('s') ? sublineId.substring(1) : sublineId;
  return request(`/inventory/sublinehook/${cleanId}`, 'PUT', sublineData);
}

/**
 * 从用户私有钓箱中删除子线双钩
 * @param {number|string} sublineId 
 * @returns {Promise<object>}
 */
function deleteUserSubLineHook(sublineId) {
  const cleanId = typeof sublineId === 'string' && sublineId.startsWith('s') ? sublineId.substring(1) : sublineId;
  return request(`/inventory/sublinehook/${cleanId}`, 'DELETE');
}

/**
 * 获取用户钓箱里现有的所有浮漂
 * @returns {Promise<object>}
 */
function getUserFloats() {
  return request('/inventory/floats/user', 'GET');
}

/**
 * 用户录入新的浮漂到私有钓箱
 * @param {object} floatData 
 * @returns {Promise<object>}
 */
function addUserFloat(floatData) {
  return request('/inventory/float', 'POST', floatData);
}

/**
 * 获取单条浮漂详情
 * @param {number|string} floatId 
 * @returns {Promise<object>}
 */
function getUserFloat(floatId) {
  const cleanId = typeof floatId === 'string' && floatId.startsWith('f') ? floatId.substring(1) : floatId;
  return request(`/inventory/float/${cleanId}`, 'GET');
}

/**
 * 修改用户私有钓箱中的浮漂
 * @param {number|string} floatId 
 * @param {object} floatData 
 * @returns {Promise<object>}
 */
function updateUserFloat(floatId, floatData) {
  const cleanId = typeof floatId === 'string' && floatId.startsWith('f') ? floatId.substring(1) : floatId;
  return request(`/inventory/float/${cleanId}`, 'PUT', floatData);
}

/**
 * 从用户私有钓箱中删除浮漂
 * @param {number|string} floatId 
 * @returns {Promise<object>}
 */
function deleteUserFloat(floatId) {
  const cleanId = typeof floatId === 'string' && floatId.startsWith('f') ? floatId.substring(1) : floatId;
  return request(`/inventory/float/${cleanId}`, 'DELETE');
}

/**
 * 获取用户钓箱里现有的所有饵料
 * @returns {Promise<object>}
 */
function getUserBaits() {
  return request('/inventory/baits/user', 'GET');
}

/**
 * 用户录入新的饵料到私有钓箱
 * @param {object} baitData 
 * @returns {Promise<object>}
 */
function addUserBait(baitData) {
  return request('/inventory/bait', 'POST', baitData);
}

/**
 * 一键添加老三样
 * @returns {Promise<object>}
 */
function addOldThreeBait() {
  return request('/inventory/bait/old-three', 'POST');
}

/**
 * 获取单款饵料详情
 * @param {number|string} baitId 
 * @returns {Promise<object>}
 */
function getUserBait(baitId) {
  const cleanId = typeof baitId === 'string' && baitId.startsWith('b') ? baitId.substring(1) : baitId;
  return request(`/inventory/bait/${cleanId}`, 'GET');
}

/**
 * 修改用户私有钓箱中的饵料
 * @param {number|string} baitId 
 * @param {object} baitData 
 * @returns {Promise<object>}
 */
function updateUserBait(baitId, baitData) {
  const cleanId = typeof baitId === 'string' && baitId.startsWith('b') ? baitId.substring(1) : baitId;
  return request(`/inventory/bait/${cleanId}`, 'PUT', baitData);
}

/**
 * 从用户私有钓箱中删除饵料
 * @param {number|string} baitId 
 * @returns {Promise<object>}
 */
function deleteUserBait(baitId) {
  const cleanId = typeof baitId === 'string' && baitId.startsWith('b') ? baitId.substring(1) : baitId;
  return request(`/inventory/bait/${cleanId}`, 'DELETE');
}

/**
 * 获取公共标准饵料库，供下拉级联选择
 * @returns {Promise<object>}
 */
function getPublicBaits() {
  return request('/inventory/baits/public', 'GET');
}

module.exports = {
  getPublicBaits,
  reportRealtimeData,
  reportHistoryBatch,
  getPrediction,
  getPredictionReport,
  getPredictionLogs,
  getWeatherPredict,
  getForecastToday,
  getForecast3Day,
  getSensorRecords,
  saveSession,
  getSessionList,
  getAiRescue,
  getUserInventoryAll,
  getPoster,
  getRodDatabase,
  addUserRod,
  getUserRods,
  getUserRod,
  updateUserRod,
  deleteUserRod,
  getUserMainLines,
  addUserMainLine,
  getUserMainLine,
  updateUserMainLine,
  deleteUserMainLine,
  getUserSubLineHooks,
  addUserSubLineHook,
  getUserSubLineHook,
  updateUserSubLineHook,
  deleteUserSubLineHook,
  getUserFloats,
  addUserFloat,
  getUserFloat,
  updateUserFloat,
  deleteUserFloat,
  getUserBaits,
  addUserBait,
  addOldThreeBait,
  getUserBait,
  updateUserBait,
  deleteUserBait,
};

