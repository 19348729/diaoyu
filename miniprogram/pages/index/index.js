/**
 * 实时监测页面
 * 展示 BLE 连接状态、实时传感器数据、简要预测结果
 */
const { getBLEManager } = require('../../utils/ble');
const protocol = require('../../utils/protocol');

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
        break;

      case protocol.CMD.HISTORY_DATA:
        this.setData({ historyCount: this.data.historyCount + data.count });
        // 更新为最新一条历史数据的显示
        if (data.records && data.records.length > 0) {
          this._updateRealtimeDisplay(data.records[data.records.length - 1]);
        }
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
});
