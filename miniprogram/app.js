/**
 * 钓鱼预测小程序 - 全局入口
 * 负责全局状态管理和应用生命周期
 */
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
      tBottom: null,   // 水底温度
      tMid: null,      // 水下1米温度
      tSurface: null,  // 水面温度
      tDiff: null,     // 温差
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
              } else {
                console.error('[App] 后端登录返回异常:', resp.data);
              }
            },
            fail: (err) => {
              console.error('[App] 获取 openid 失败:', err);
            },
          });
          console.log('[App] 获取登录 code:', res.code);
        }
      },
    });
  },

  /**
   * 添加历史数据记录（供 BLE 模块回调）
   */
  addHistoryRecord(record) {
    const history = this.globalData.historyData;
    history.push(record);
    // 最多保留 720 条（1 小时 @5秒间隔）
    if (history.length > 720) {
      history.splice(0, history.length - 720);
    }
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
  },
});
