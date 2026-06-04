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
    selectedMethod: '',   // 用户在出钓配置选择的钓法（用于建议兜底，统一术语）
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

    // 注册 BLE 回调
    this._ble.onConnect((connected) => {
      this._updateConnectionStatus(connected);
    });

    this._ble.onData((data) => {
      this._handleData(data);
    });

    this._ble.onTimeSync(() => {
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
    const fishCtx = app.globalData.fishContext || {};
    this.setData({
      targetFish: fishCtx.target || '',
      selectedMethod: fishCtx.method || '',
    });

    // 恢复前台时立即刷新预测新鲜度显示
    if (this.data.lastPredictTime) {
      this._updatePredictFreshness();
      this._startPredictAgeTimer();
    }

    // 无设备（气象预测模式）：进入页面即触发一次气象预测，无需 BLE 数据
    if (!this._ble.isConnected) {
      this._tryTriggerPrediction();
    }
  },

  /**
   * 点击连接按钮
   */
  async onTapConnect() {
    if (this._ble.isConnected) {
      // 已连接则直接断开（不再保存会话日志）
      await this._ble.disconnect();
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

    // 检测到鱼经过：震动提醒（钓友盯漂时无需盯屏）
    if (data.fishEvent && !this.data.sonarFishEvent) {
      wx.vibrateShort({ type: 'medium' });
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
    const hasSensor = historyData.length > 0 ||
      (app.globalData.latestData && app.globalData.latestData.timestamp);
    // 已连接且有传感器数据 → 传感器预测；否则（无设备）→ 纯气象预测
    const useSensor = this._ble.isConnected && hasSensor;

    this.setData({ predicting: true, predictStatusText: '正在获取预测...' });

    // 复用 app 的带缓存定位（5 分钟内不重复请求，失败有兜底，钓点固定无需反复定位）
    app.getLocationWithCache().then(async (loc) => {
      try {
        const fishType = (app.globalData.fishContext && app.globalData.fishContext.target) || 'auto';
        let prediction;
        if (useSensor) {
          const sensors = historyData.length > 0 ? historyData : [app.globalData.latestData];
          prediction = await api.getPrediction(sensors, loc.lat, loc.lng, fishType);
        } else {
          prediction = await api.getWeatherPredict(loc.lat, loc.lng, fishType);
        }

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
    // 无设备（气象模式）无需传感器数据也可刷新
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
