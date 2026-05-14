/**
 * 钓鱼预测小程序 - 全局入口
 * 负责全局状态管理和应用生命周期
 */
const api = require('./utils/api');

App({
  globalData: {
    // 用户信息
    userInfo: null,
    openid: null,

    // BLE 连接状态
    bleConnected: false,
    deviceId: null,
    timeSynced: false,

    // 最新传感器数据
    latestData: {
      timestamp: 0,
      tWater: null,    // 水温
      tAir: null,      // 气温
      pLocal: null,    // 气压 hPa
    },

    // 历史数据缓存（用于趋势展示）
    historyData: [],

    // 后端 API 地址（部署后替换）
    apiBaseUrl: 'https://ks.gzbaoge.com/api',
  },

  onLaunch() {
    console.log('[App] 小程序启动');

    // 先尝试从本地缓存恢复 openid
    const cachedOpenid = wx.getStorageSync('openid');
    if (cachedOpenid) {
      this.globalData.openid = cachedOpenid;
    }

    // 恢复本地存储的历史数据（离线兜底）
    const cachedHistory = wx.getStorageSync('sensor_history');
    if (cachedHistory && Array.isArray(cachedHistory)) {
      this.globalData.historyData = cachedHistory;
      if (cachedHistory.length > 0) {
        this.globalData.latestData = cachedHistory[cachedHistory.length - 1];
      }
      console.log(`[App] 本地恢复历史数据: ${cachedHistory.length} 条`);
    }

    // 检查蓝牙权限
    this.checkBlePermission();

    // 获取用户 openid（静默登录）
    this.silentLogin();
  },

  onShow() {
    console.log('[App] 小程序进入前台');
  },

  onHide() {
    console.log('[App] 小程序进入后台');
  },

  /**
   * 检查蓝牙适配器状态
   */
  checkBlePermission() {
    wx.openBluetoothAdapter({
      mode: 'central',
      success: () => {
        console.log('[App] 蓝牙适配器已就绪');
      },
      fail: (err) => {
        console.error('[App] 蓝牙初始化失败:', err);
        wx.showToast({
          title: '请开启蓝牙',
          icon: 'none',
          duration: 3000,
        });
      },
    });
  },

  /**
   * 静默登录获取 openid
   */
  silentLogin() {
    wx.login({
      success: (res) => {
        if (res.code) {
          // 将 code 发送到后端换取 openid
          wx.request({
            url: `${this.globalData.apiBaseUrl}/login`,
            method: 'POST',
            data: { code: res.code },
            success: (resp) => {
              if (resp.data && resp.data.openid) {
                this.globalData.openid = resp.data.openid;
                wx.setStorageSync('openid', resp.data.openid);
                console.log('[App] 获取 openid 成功:', resp.data.openid);
                
                // 获取到 openid 后，向后端拉取最新的历史数据恢复现场
                this.fetchCloudHistory();
              } else {
                console.error('[App] 后端登录返回异常 (可能未返回 openid):', resp.data);
              }
            },
            fail: (err) => {
              console.error('[App] 调用后端登录接口失败:', err);
            },
          });
          console.log('[App] 获取登录 code:', res.code);
        }
      },
    });
  },

  /**
   * 从云端拉取历史数据并合并
   */
  async fetchCloudHistory() {
    try {
      const res = await api.getSensorRecords(1440);
      if (res && res.data && res.data.length > 0) {
        this.globalData.historyData = res.data;
        this.globalData.latestData = res.data[res.data.length - 1];
        wx.setStorageSync('sensor_history', res.data);
        console.log(`[App] 云端恢复历史数据: ${res.data.length} 条`);
      }
    } catch (e) {
      console.error('[App] 云端恢复历史数据失败 (可忽略，使用本地兜底):', e);
    }
  },

  /**
   * 添加历史数据记录（供 BLE 模块回调）
   */
  addHistoryRecord(record) {
    const history = this.globalData.historyData;
    history.push(record);
    // 最多保留 1440 条（24 小时 @60秒间隔）
    if (history.length > 1440) {
      history.splice(0, history.length - 1440);
    }
    // 异步存入本地缓存，离线兜底
    wx.setStorage({ key: 'sensor_history', data: history });
  },

  /**
   * 批量添加历史数据
   */
  addHistoryBatch(records) {
    for (const record of records) {
      this.addHistoryRecord(record);
    }
    // 按时间戳排序
    this.globalData.historyData.sort((a, b) => a.timestamp - b.timestamp);
    // 异步存入本地缓存，离线兜底
    wx.setStorage({ key: 'sensor_history', data: this.globalData.historyData });
  },

  /**
   * 获取当前位置（带 5 分钟缓存，防止频繁请求）
   */
  getLocationWithCache() {
    return new Promise((resolve) => {
      const now = Date.now();
      if (this.globalData.cachedLocation && now - this.globalData.locationCacheTime < 5 * 60 * 1000) {
        resolve(this.globalData.cachedLocation);
        return;
      }

      wx.getLocation({
        type: 'wgs84',
        success: (res) => {
          const loc = { lat: res.latitude, lng: res.longitude };
          this.globalData.cachedLocation = loc;
          this.globalData.locationCacheTime = now;
          resolve(loc);
        },
        fail: (err) => {
          console.warn('[App] getLocation 失败，使用缓存或默认值', err);
          resolve(this.globalData.cachedLocation || { lat: 0, lng: 0 });
        }
      });
    });
  }
});
