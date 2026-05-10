/**
 * 实时监测页面
 * 展示 BLE 连接状态、实时传感器数据、简要预测结果
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
    tBottom: '--',
    tMid: '--',
    tSurface: '--',
    tDiff: '--',
    pLocal: '--',
    updateTime: '--',

    // 设备状态
    bufferUnsent: 0,
    bufferCount: 0,

    // 数据接收计数
    realtimeCount: 0,
    historyCount: 0,

    // 预测相关
    predicting: false,
    lastPredictTime: 0,
    biteIndex: '--',
    tacticalTags: [],
    recommendedFish: '',
    fishRanking: [],
    weatherInfo: null,
    tacticalAdvice: null,
  },

  onLoad() {
    this._ble = getBLEManager();

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

  onShow() {
    // 恢复前台时刷新状态
    this._updateConnectionStatus(this._ble.isConnected);
    this._refreshLatestData();
  },

  /**
   * 点击连接按钮
   */
  async onTapConnect() {
    if (this._ble.isConnected) {
      // 已连接则断开
      await this._ble.disconnect();
      return;
    }

    this.setData({ connecting: true, statusText: '搜索中...', statusClass: 'syncing' });

    try {
      const success = await this._ble.connectDevice();
      if (success) {
        this._updateConnectionStatus(true);
      } else {
        this._updateConnectionStatus(false);
      }
    } catch (e) {
      console.error('[Index] 连接失败:', e);
      this._updateConnectionStatus(false);
    }

    this.setData({ connecting: false });
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
    }
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
      tBottom: formatVal(data.tBottom),
      tMid: formatVal(data.tMid),
      tSurface: formatVal(data.tSurface),
      tDiff: formatVal(data.tDiff),
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
  },

  _pad(n) {
    return n < 10 ? '0' + n : '' + n;
  },

  /**
   * 尝试触发后端预测请求（带 5 分钟防抖限流）
   */
  _tryTriggerPrediction() {
    const now = Date.now();
    // 5 分钟 = 300,000 毫秒
    if (now - this.data.lastPredictTime < 300000 || this.data.predicting) {
      return;
    }

    const app = getApp();
    const historyData = app.globalData.historyData || [];
    if (historyData.length === 0 && !app.globalData.latestData.timestamp) {
      return; // 暂无任何数据
    }

    this.setData({ predicting: true });

    // 获取位置
    wx.getLocation({
      type: 'wgs84',
      success: async (res) => {
        try {
          const sensors = historyData.length > 0 ? historyData : [app.globalData.latestData];
          const prediction = await api.getPrediction(sensors, res.latitude, res.longitude);
          
          this.setData({
            lastPredictTime: now,
            biteIndex: prediction.bite_index !== undefined ? prediction.bite_index : '--',
            tacticalTags: translateTags(prediction.tactical_tags || []),
            recommendedFish: prediction.recommended_fish || '',
            fishRanking: prediction.recommended_fishes || [],
            weatherInfo: prediction.weather_info || null,
            tacticalAdvice: prediction.tactical_advice || null,
            predicting: false
          });
        } catch (e) {
          console.error('[Index] 预测请求失败:', e);
          this.setData({ predicting: false });
        }
      },
      fail: (err) => {
        console.error('[Index] 获取位置失败，无法预测:', err);
        this.setData({ predicting: false });
        wx.showToast({ title: '定位失败', icon: 'error' });
      }
    });
  },

  /**
   * 调试：生成 3 条模拟数据
   */
  onTapMockData() {
    const app = getApp();
    const now = Math.floor(Date.now() / 1000);
    const mockRecords = [
      { timestamp: now - 10, tBottom: 20.1, tMid: 21.0, tSurface: 22.5, pLocal: 1012.3 },
      { timestamp: now - 5, tBottom: 20.2, tMid: 21.1, tSurface: 22.4, pLocal: 1012.5 },
      { timestamp: now, tBottom: 20.1, tMid: 21.2, tSurface: 22.6, pLocal: 1012.4 }
    ];
    
    // 更新全局状态
    app.globalData.historyData = mockRecords;
    app.globalData.latestData = mockRecords[2];

    // 更新页面展示
    const latest = mockRecords[2];
    this.setData({
      tBottom: latest.tBottom.toFixed(1),
      tMid: latest.tMid.toFixed(1),
      tSurface: latest.tSurface.toFixed(1),
      tDiff: (latest.tSurface - latest.tBottom).toFixed(1),
      pLocal: latest.pLocal.toFixed(1),
      updateTime: new Date(latest.timestamp * 1000).toLocaleTimeString(),
      historyCount: this.data.historyCount + 3
    });

    wx.showToast({ title: '模拟数据已生成', icon: 'success' });
  },

  /**
   * 调试：无视时间限制，强制触发一次后端预测
   */
  onTapManualPredict() {
    // 强制把最后预测时间归零，绕过防抖检查
    this.setData({ lastPredictTime: 0 });
    this._tryTriggerPrediction();
  }
});
