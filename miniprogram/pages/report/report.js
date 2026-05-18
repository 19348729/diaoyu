const api = require('../../utils/api')
const ble = require('../../utils/ble')
const app = getApp()

Page({
  data: {
    catchLevel: '稳赚',
    isGenerating: false,
    posterData: null
  },

  selectLevel(e) {
    this.setData({ catchLevel: e.currentTarget.dataset.val })
  },

  async finishSession() {
    this.setData({ isGenerating: true })
    try {
      // 1. 获取基础位置数据
      const loc = await app.getLocationWithCache()
      
      // 2. 构造 session 保存数据 (simplified)
      const sessionData = {
        start_time: Math.floor(Date.now()/1000) - 7200, // mock 2 hours ago
        end_time: Math.floor(Date.now()/1000),
        duration_min: 120,
        data_points: 120,
        lat: loc.lat,
        lng: loc.lng,
        bite_index_avg: this.getBiteIndex(this.data.catchLevel)
      }
      
      const saveRes = await api.saveSession(sessionData)
      
      // 3. 断开蓝牙连接
      const bleManager = ble.getBLEManager()
      if (bleManager.isConnected) {
        bleManager.disconnect()
        wx.showToast({ title: '设备已休眠', icon: 'none' })
      }
      
      // 4. 获取海报数据
      if (saveRes.status === 'ok') {
        const posterRes = await api.getPoster(saveRes.session_id)
        if (posterRes.status === 'ok') {
          this.setData({ posterData: posterRes.poster })
        }
      }
    } catch (e) {
      wx.showToast({ title: e.message || '生成失败', icon: 'none' })
    } finally {
      this.setData({ isGenerating: false })
    }
  },
  
  getBiteIndex(level) {
    if (level === '爆护') return 90;
    if (level === '稳赚') return 70;
    if (level === '惨淡') return 50;
    return 30; // 空军
  },
  
  sharePoster() {
    wx.showToast({ title: '已保存到相册，快去分享吧', icon: 'none' })
  }
})
