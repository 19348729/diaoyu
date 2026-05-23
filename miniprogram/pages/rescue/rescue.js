const api = require('../../utils/api')
const ble = require('../../utils/ble')
const app = getApp()

Page({
  data: {
    symptoms: [
      { label: '有地星跑泡但不咬钩', val: 'SYM_BUBBLES_NO_BITE', checked: false },
      { label: '杂鱼截口严重', val: 'SYM_SMALL_FISH_INTERCEPT', checked: false },
      { label: '完全无口无鱼星', val: 'SYM_NO_ACTIVITY', checked: false },
      { label: '浮漂频繁走水', val: 'SYM_FLOAT_DRIFT', checked: false },
      { label: '看到鱼跳但不吃饵', val: 'SYM_FISH_JUMP', checked: false },
      { label: '原本连杆突然停口', val: 'SYM_SUDDEN_STOP', checked: false },
      { label: '鱼口极轻，有动作打不到', val: 'SYM_WEAK_BITE', checked: false },
      { label: '鱼层明显上浮', val: 'SYM_FISH_UP', checked: false }
    ],
    isRescuing: false,
    prescription: null
  },

  onShow() {
    // 进入页面时尝试全量 Dump
    const bleManager = ble.getBLEManager()
    if (bleManager.isConnected && bleManager.isTimeSynced) {
      wx.showToast({ title: '正在同步设备数据', icon: 'loading', duration: 2000 })
      bleManager.sendBulkDump()
    }
  },

  toggleSymptom(e) {
    const idx = e.currentTarget.dataset.idx
    const syms = this.data.symptoms
    syms[idx].checked = !syms[idx].checked
    this.setData({ symptoms: syms })
  },

  resetRescue() {
    this.setData({ prescription: null })
  },

  async requestRescue() {
    this.setData({ isRescuing: true })
    try {
      const selectedTags = this.data.symptoms.filter(s => s.checked).map(s => s.val)
      const loc = await app.getLocationWithCache()
      
      // Get recent records for AI engine calculation
      const recordsRes = await api.getSensorRecords(60) // get last hour or so
      const sensors = recordsRes.data || []
      
      const context = app.globalData.fishContext || { target: '未知', method: '未知', bait: '未知' }
      
      // 拉取数字钓箱全量装备，让 AI 处方能精准到型号
      let userInventory = null
      try {
        userInventory = await api.getUserInventoryAll()
      } catch (invErr) {
        console.warn('[Rescue] 拉取装备库失败，降级为通用建议:', invErr)
      }
      
      const res = await api.getAiRescue(sensors, selectedTags, context, loc.lat, loc.lng, userInventory)
      if (res.status === 'ok') {
        this.setData({ prescription: res.prescription })
        wx.showToast({ title: '分析完成', icon: 'success' })
      } else {
        wx.showToast({ title: '救场分析失败', icon: 'none' })
      }
    } catch (e) {
      wx.showToast({ title: e.message || '网络错误', icon: 'none' })
    } finally {
      this.setData({ isRescuing: false })
    }
  }
})
