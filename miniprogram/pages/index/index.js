/**
 * 实时监测页面
 * 展示 BLE 连接状态、实时传感器数据、简要预测结果
 *
 * 硬件版本: v2（水温 + 气温 + 气压）
 */
const { getBLEManager } = require('../../utils/ble');
const protocol = require('../../utils/protocol');
const api = require('../../utils/api');
const { translateTags } = require('../../utils/tagMap');

Page({
  data: {
    // 连接状态
    bleConnected: false,
    timeSynced: false,
    connecting: false,
    statusText: '未连接',
    statusClass: 'disconnected',

    // 实时数据
    tWater: '--',
    tAir: '--',
    pLocal: '--',
    updateTime: '--',

    // 水下声呐数据（来自 ESP32-B 测距板，通过 ESP-NOW -> ESP32-A -> BLE）
    sonarHasData: false,
    sonarDistance: '--',     // 当前距离 cm
    sonarBaseline: '--',     // 基线（30秒滑动均值）cm
    sonarStatus: -1,         // 0/1/2/3
    sonarStatusText: '等待数据',
    sonarStatusClass: 'idle',
    sonarFishEvent: false,   // 当前帧是否检测到鱼经过
    sonarFishCount: 0,       // 累计鱼经过次数
    sonarUpdateTime: '--',

    // 设备状态
    bufferUnsent: 0,
    bufferCount: 0,

    // 数据接收计数
    realtimeCount: 0,
    historyCount: 0,

    // 预测相关
    predicting: false,
    lastPredictTime: 0,
    targetFish: '',
    biteIndex: '--',
    tacticalTags: [],
    recommendedFish: '',
    fishRanking: [],
    weatherInfo: null,
    tacticalAdvice: null,

    // 预测新鲜度显示
    predictTimeText: '',       // "2分钟前" / "刚刚"
    predictFreshness: 'none',  // none / fresh / normal / stale / expired
    predictStatusText: '',     // 底部状态栏文案

    // 开口指数解读
    biteRatingText: '',        // "🔥 爆护信号" / "👍 适合出钓" / ...
    biteRatingColor: '',       // 颜色值
    biteRatingBg: '',          // 背景色
  },

  onLoad() {
    this._ble = getBLEManager();
    this._predictAgeTimer = null;
    this._sessionStartTs = 0;  // 本次 BLE 会话起始时间戳（秒）

    // 注册 BLE 回调
    this._ble.onConnect((connected) => {
      this._updateConnectionStatus(connected);
    });

    this._ble.onData((data) => {
      this._handleData(data);
    });

    this._ble.onTimeSync(() => {
      // 记录本次会话起始时间，用于断开时精确计算本次作钓时长
      this._sessionStartTs = Math.floor(Date.now() / 1000);
      this.setData({
        timeSynced: true,
        statusText: '已连接 - 数据传输中',
        statusClass: 'connected',
      });
    });
  },

  onUnload() {
    // 清理预测新鲜度定时器
    if (this._predictAgeTimer) {
      clearInterval(this._predictAgeTimer);
      this._predictAgeTimer = null;
    }
  },

  onShow() {
    // 恢复前台时刷新状态
    this._updateConnectionStatus(this._ble.isConnected);
    this._refreshLatestData();

    // 获取用户在上一页选择的目标鱼种并更新
    const app = getApp();
    const targetFish = (app.globalData.fishContext && app.globalData.fishContext.target) || '';
    this.setData({ targetFish });

    // 恢复前台时立即刷新预测新鲜度显示
    if (this.data.lastPredictTime) {
      this._updatePredictFreshness();
      this._startPredictAgeTimer();
    }
  },

  /**
   * 点击连接按钮
   */
  async onTapConnect() {
    if (this._ble.isConnected) {
      // 已连接则断开 — 检查是否需要保存日志
      await this._handleDisconnect();
      return;
    }

    // 如果未连接，直接优雅跳转回出钓准备页面进行连接与配置
    wx.navigateTo({
      url: '/pages/setup/setup'
    });
  },

  /**
   * 点击查询设备状态
   */
  async onTapQueryStatus() {
    if (!this._ble.isConnected) return;
    try {
      await this._ble.sendStatusQuery();
    } catch (e) {
      console.error('[Index] 状态查询失败:', e);
    }
  },

  /**
   * 点击手动拉取一批历史数据
   * 每点一次发一批（最多 BLE_BATCH_SIZE 条），收到后会自动 ACK 并刷新状态
   */
  async onTapPullHistory() {
    if (!this._ble.isConnected) {
      wx.showToast({ title: '未连接设备', icon: 'none' });
      return;
    }
    if (!this._ble.isTimeSynced) {
      wx.showToast({ title: '等待对表完成', icon: 'none' });
      return;
    }
    if (this.data.bufferUnsent <= 0) {
      wx.showToast({ title: '当前无待补数据', icon: 'none' });
      return;
    }
    try {
      await this._ble.sendPullHistory();
      wx.showToast({ title: '已请求一批', icon: 'none' });
    } catch (e) {
      console.error('[Index] 手动拉取失败:', e);
      wx.showToast({ title: '拉取失败', icon: 'none' });
    }
  },

  /**
   * 更新连接状态显示
   */
  _updateConnectionStatus(connected) {
    if (connected) {
      this.setData({
        bleConnected: true,
        statusText: this._ble.isTimeSynced ? '已连接 - 数据传输中' : '已连接 - 等待对表',
        statusClass: this._ble.isTimeSynced ? 'connected' : 'syncing',
        timeSynced: this._ble.isTimeSynced,
      });
    } else {
      this.setData({
        bleConnected: false,
        timeSynced: false,
        statusText: '未连接',
        statusClass: 'disconnected',
      });
    }
  },

  /**
   * 处理从 BLE 收到的数据
   */
  _handleData(data) {
    switch (data.cmd) {
      case protocol.CMD.REALTIME_DATA:
        this._updateRealtimeDisplay(data);
        this.setData({ realtimeCount: this.data.realtimeCount + 1 });
        this._tryTriggerPrediction();
        break;

      case protocol.CMD.HISTORY_DATA:
        this.setData({ historyCount: this.data.historyCount + data.count });
        // 更新为最新一条历史数据的显示
        if (data.records && data.records.length > 0) {
          this._updateRealtimeDisplay(data.records[data.records.length - 1]);
        }
        this._tryTriggerPrediction();
        break;

      case protocol.CMD.STATUS_REPLY:
        this.setData({
          bufferUnsent: data.unsent,
          bufferCount: data.count,
        });
        break;

      case protocol.CMD.SONAR_DATA:
        this._updateSonarDisplay(data);
        break;
    }
  },

  /**
   * 更新水下声呐显示
   * @param {object} data - 解码后的声呐帧 {timestamp, distanceCm, baselineCm, status, fishEvent}
   */
  _updateSonarDisplay(data) {
    const app = getApp();
    const fmt = (v) => (v !== null && v !== undefined) ? v.toFixed(1) : '--';

    // 状态码 -> 文案 + 样式 class
    const statusMap = {
      0: { text: '正常', cls: 'ok' },
      1: { text: '超出量程', cls: 'warn' },
      2: { text: '距离过近', cls: 'warn' },
      3: { text: '通讯失败', cls: 'err' },
    };
    const st = statusMap[data.status] || { text: '未知', cls: 'idle' };

    let timeStr = '--';
    if (data.timestamp) {
      const d = new Date(data.timestamp * 1000);
      timeStr = `${this._pad(d.getHours())}:${this._pad(d.getMinutes())}:${this._pad(d.getSeconds())}`;
    }

    this.setData({
      sonarHasData: true,
      sonarDistance: fmt(data.distanceCm),
      sonarBaseline: fmt(data.baselineCm),
      sonarStatus: data.status,
      sonarStatusText: st.text,
      sonarStatusClass: st.cls,
      sonarFishEvent: !!data.fishEvent,
      sonarFishCount: app.globalData.sonarFishEventCount || 0,
      sonarUpdateTime: timeStr,
    });
  },

  /**
   * 更新实时数据显示
   */
  _updateRealtimeDisplay(data) {
    const formatVal = (v) => v !== null && v !== undefined ? v.toFixed(1) : '--';
    const formatPress = (v) => v !== null && v !== undefined ? v.toFixed(1) : '--';

    // 格式化时间
    let timeStr = '--';
    if (data.timestamp) {
      const d = new Date(data.timestamp * 1000);
      timeStr = `${this._pad(d.getHours())}:${this._pad(d.getMinutes())}:${this._pad(d.getSeconds())}`;
    }

    this.setData({
      tWater: formatVal(data.tWater),
      tAir: formatVal(data.tAir),
      pLocal: formatPress(data.pLocal),
      updateTime: timeStr,
    });
  },

  /**
   * 从全局数据刷新显示（页面恢复前台时）
   */
  _refreshLatestData() {
    const app = getApp();
    const latest = app.globalData.latestData;
    if (latest && latest.timestamp > 0) {
      this._updateRealtimeDisplay(latest);
    }
    // 恢复声呐显示
    const sonar = app.globalData.latestSonar;
    if (sonar && sonar.timestamp > 0) {
      this._updateSonarDisplay(sonar);
    }
  },

  _pad(n) {
    return n < 10 ? '0' + n : '' + n;
  },

  /**
   * 尝试触发后端预测请求（带 5 分钟防抖限流）
   * @param {boolean} force - 是否强制触发（跳过冷却限制）
   */
  _tryTriggerPrediction(force = false) {
    const now = Date.now();
    // 5 分钟 = 300,000 毫秒
    if (!force && (now - this.data.lastPredictTime < 300000 || this.data.predicting)) {
      return;
    }
    // 即使强制触发，也不允许并发
    if (this.data.predicting) {
      return;
    }

    const app = getApp();
    const historyData = app.globalData.historyData || [];
    if (historyData.length === 0 && !app.globalData.latestData.timestamp) {
      return; // 暂无任何数据
    }

    this.setData({ predicting: true, predictStatusText: '正在获取预测...' });

    // 获取位置
    wx.getLocation({
      type: 'wgs84',
      success: async (res) => {
        try {
          const sensors = historyData.length > 0 ? historyData : [app.globalData.latestData];
          const fishType = (app.globalData.fishContext && app.globalData.fishContext.target) || 'auto';
          const prediction = await api.getPrediction(sensors, res.latitude, res.longitude, fishType);
          
          const predictTime = Date.now();
          const biteRating = this._calcBiteRating(prediction.bite_index);
          this.setData({
            lastPredictTime: predictTime,
            biteIndex: prediction.bite_index !== undefined ? prediction.bite_index : '--',
            biteRatingText: biteRating.text,
            biteRatingColor: biteRating.color,
            biteRatingBg: biteRating.bg,
            tacticalTags: translateTags(prediction.tactical_tags || []),
            recommendedFish: prediction.recommended_fish || '',
            fishRanking: prediction.recommended_fishes || [],
            weatherInfo: prediction.weather_info || null,
            tacticalAdvice: prediction.tactical_advice || null,
            predicting: false,
          });
          // 更新新鲜度显示并启动定时刷新
          this._updatePredictFreshness();
          this._startPredictAgeTimer();
        } catch (e) {
          console.error('[Index] 预测请求失败:', e);
          this.setData({ predicting: false, predictStatusText: '预测请求失败' });
        }
      },
      fail: (err) => {
        console.error('[Index] 获取位置失败，无法预测:', err);
        this.setData({ predicting: false, predictStatusText: '定位失败，无法预测' });
        wx.showToast({ title: '定位失败', icon: 'error' });
      }
    });
  },

  /**
   * 更新预测新鲜度显示文案和状态
   */
  _updatePredictFreshness() {
    const lastTime = this.data.lastPredictTime;
    if (!lastTime) {
      this.setData({
        predictTimeText: '',
        predictFreshness: 'none',
        predictStatusText: '暂无预测数据',
      });
      return;
    }

    const elapsed = Date.now() - lastTime;
    const minutes = Math.floor(elapsed / 60000);

    let timeText = '';
    let freshness = 'fresh';
    let statusText = '';

    if (minutes < 1) {
      timeText = '刚刚更新';
      freshness = 'fresh';
      statusText = '数据最新';
    } else if (minutes < 5) {
      timeText = `${minutes}分钟前`;
      freshness = 'fresh';
      statusText = '数据最新';
    } else if (minutes < 10) {
      timeText = `${minutes}分钟前`;
      freshness = 'normal';
      statusText = '即将自动刷新';
    } else if (minutes < 30) {
      timeText = `${minutes}分钟前`;
      freshness = 'stale';
      statusText = '数据较旧，建议刷新';
    } else if (minutes < 60) {
      timeText = `${minutes}分钟前`;
      freshness = 'expired';
      statusText = '数据已过期，请刷新';
    } else {
      const hours = Math.floor(minutes / 60);
      timeText = `${hours}小时前`;
      freshness = 'expired';
      statusText = '数据已过期，请刷新';
    }

    this.setData({ predictTimeText: timeText, predictFreshness: freshness, predictStatusText: statusText });
  },

  /**
   * 启动预测新鲜度定时器（每 30 秒刷新一次相对时间）
   */
  _startPredictAgeTimer() {
    if (this._predictAgeTimer) {
      clearInterval(this._predictAgeTimer);
    }
    this._predictAgeTimer = setInterval(() => {
      this._updatePredictFreshness();
    }, 30000);
  },


  /**
   * 用户主动刷新预测（强制触发，跳过冷却）
   */
  onTapRefreshPredict() {
    if (this.data.predicting) {
      wx.showToast({ title: '正在预测中...', icon: 'none' });
      return;
    }
    const app = getApp();
    if (!app.globalData.latestData.timestamp) {
      wx.showToast({ title: '暂无传感器数据', icon: 'none' });
      return;
    }
    this._tryTriggerPrediction(true);
  },

  /**
   * 跳转到历史趋势折线图页面
   */
  goToHistory() {
    wx.navigateTo({
      url: '/pages/history/history'
    });
  },

  // ============================================
  //  钓鱼会话日志
  // ============================================

  /**
   * 处理主动断开连接
   * 判断会话时长，≥30 分钟则弹窗询问是否保存日志
   */
  async _handleDisconnect() {
    const app = getApp();
    const allHistory = app.globalData.historyData || [];

    // 只取本次会话期间（_sessionStartTs 之后）的数据
    const sessionHistory = this._sessionStartTs
      ? allHistory.filter(r => r.timestamp >= this._sessionStartTs)
      : [];

    // 计算本次会话时长
    let durationMin = 0;
    if (sessionHistory.length >= 2) {
      const first = sessionHistory[0];
      const last = sessionHistory[sessionHistory.length - 1];
      durationMin = Math.round((last.timestamp - first.timestamp) / 60);
    }

    // 先断开 BLE
    await this._ble.disconnect();

    // 不足 30 分钟视为测试连接，不提示保存
    if (durationMin < 30) {
      if (durationMin > 0) {
        wx.showToast({ title: `本次仅 ${durationMin} 分钟，未生成日志`, icon: 'none', duration: 2000 });
      }
      return;
    }

    // ≥30 分钟，弹窗询问
    const hours = Math.floor(durationMin / 60);
    const mins = durationMin % 60;
    const durationText = hours > 0 ? `${hours}小时${mins}分钟` : `${mins}分钟`;

    wx.showModal({
      title: '保存作钓日志',
      content: `本次作钓 ${durationText}，共采集 ${sessionHistory.length} 条数据。是否保存日志？`,
      confirmText: '保存',
      cancelText: '暂不',
      success: (res) => {
        if (res.confirm) {
          this._saveSessionToBackend();
        }
      }
    });
  },

  /**
   * 从当前 historyData 聚合构建会话摘要
   * @returns {object|null}
   */
  _buildSessionSummary() {
    const app = getApp();
    const allHistory = app.globalData.historyData || [];

    // 只取本次会话期间的数据
    const history = this._sessionStartTs
      ? allHistory.filter(r => r.timestamp >= this._sessionStartTs)
      : allHistory;
    if (history.length < 2) return null;

    const first = history[0];
    const last = history[history.length - 1];
    const durationMin = Math.round((last.timestamp - first.timestamp) / 60);

    // 过滤有效值
    const waters = history.filter(r => r.tWater != null).map(r => r.tWater);
    const airs = history.filter(r => r.tAir != null).map(r => r.tAir);
    const pressures = history.filter(r => r.pLocal != null).map(r => r.pLocal);

    const summary = {
      start_time: first.timestamp,
      end_time: last.timestamp,
      duration_min: durationMin,
      data_points: history.length,
    };

    // 水温
    if (waters.length > 0) {
      summary.t_water_start = waters[0];
      summary.t_water_end = waters[waters.length - 1];
      summary.t_water_min = Math.min(...waters);
      summary.t_water_max = Math.max(...waters);
    }

    // 气温
    if (airs.length > 0) {
      summary.t_air_start = airs[0];
      summary.t_air_end = airs[airs.length - 1];
    }

    // 气压
    if (pressures.length > 0) {
      summary.p_start = pressures[0];
      summary.p_end = pressures[pressures.length - 1];
      summary.p_trend = this._calcPressureTrend(pressures);
    }

    // 天气（取当前预测结果中的天气信息）
    if (this.data.weatherInfo) {
      summary.weather_text = this.data.weatherInfo.text || null;
      const w = this.data.weatherInfo;
      summary.wind_desc = w.wind_dir ? `${w.wind_dir} ${w.wind_speed || ''}m/s` : null;
    }

    // 开口指数（取页面已有的预测数据）
    if (this.data.biteIndex !== '--') {
      summary.bite_index_max = this.data.biteIndex;
      summary.bite_index_avg = this.data.biteIndex; // 单次快照，最高=平均
    }

    // 推荐鱼种
    if (this.data.recommendedFish) {
      summary.recommended_fish = this.data.recommendedFish;
    }

    return summary;
  },

  /**
   * 计算气压趋势描述
   * @param {number[]} pressures - 气压序列
   * @returns {string}
   */
  _calcPressureTrend(pressures) {
    if (pressures.length < 2) return '数据不足';

    const diff = pressures[pressures.length - 1] - pressures[0];
    const threshold = 0.5; // hPa

    // 检查中间点判断"先升后降"或"先降后升"
    if (pressures.length >= 4) {
      const midIdx = Math.floor(pressures.length / 2);
      const firstHalf = pressures[midIdx] - pressures[0];
      const secondHalf = pressures[pressures.length - 1] - pressures[midIdx];

      if (firstHalf > threshold && secondHalf < -threshold) return '先升后降';
      if (firstHalf < -threshold && secondHalf > threshold) return '先降后升';
    }

    if (diff > threshold) return '持续上升';
    if (diff < -threshold) return '持续下降';
    return '基本平稳';
  },

  /**
   * 保存会话到后端
   */
  async _saveSessionToBackend() {
    const summary = this._buildSessionSummary();
    if (!summary) {
      wx.showToast({ title: '数据不足，无法保存', icon: 'none' });
      return;
    }

    // 获取位置
    const app = getApp();
    const loc = app.globalData.cachedLocation || { lat: 0, lng: 0 };
    summary.lat = loc.lat;
    summary.lng = loc.lng;

    wx.showLoading({ title: '保存中...' });
    try {
      await api.saveSession(summary);
      wx.hideLoading();
      wx.showToast({ title: '日志已保存', icon: 'success' });
    } catch (e) {
      wx.hideLoading();
      console.error('[Index] 保存会话失败:', e);
      wx.showToast({ title: '保存失败', icon: 'none' });
    }
  },

  /**
   * 根据 bite_index 分值计算颜色、文案、背景色
   * @param {number} score
   * @returns {{text: string, color: string, bg: string}}
   */
  _calcBiteRating(score) {
    if (score === undefined || score === null || score === '--') {
      return { text: '', color: '#999', bg: '#f5f5f5' };
    }
    if (score >= 80) {
      return { text: '🔥 爆护信号！心动不如行动', color: '#2e7d32', bg: 'linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%)' };
    } else if (score >= 60) {
      return { text: '👍 鱼情不错，适合出钓', color: '#f57f17', bg: 'linear-gradient(135deg, #fff8e1 0%, #ffecb3 100%)' };
    } else if (score >= 40) {
      return { text: '⚠️ 鱼口一般，考验技术', color: '#e65100', bg: 'linear-gradient(135deg, #fff3e0 0%, #ffe0b2 100%)' };
    } else {
      return { text: '💀 建议改日或换钓点', color: '#c62828', bg: 'linear-gradient(135deg, #fce4ec 0%, #f8bbd0 100%)' };
    }
  }
});
