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
    // 当前正在用的钓法 / 饵料（救场时填写，给 AI 针对性开方；可不填）
    methodOptions: ['底钓', '浮钓', '行程', '路亚'],
    baitOptions: ['香腥', '本味', '活饵', '玉米/颗粒', '酸臭/发酵', '拟饵'],
    curMethod: '',
    curBait: '',

    isRescuing: false,
    prescription: null
  },

  selectMethod(e) { this.setData({ curMethod: e.currentTarget.dataset.val }) },
  selectBait(e) { this.setData({ curBait: e.currentTarget.dataset.val }) },

  onShow() {
    // 仅在已连接且对表完成时尝试全量 Dump；无设备时直接跳过（气象模式照常可用）
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

      // 获取近期传感器数据；无设备/拉取失败时降级为空数组（后端可基于气象+定位出方案）
      let sensors = []
      try {
        const recordsRes = await api.getSensorRecords(60) // 最近一小时左右
        sensors = recordsRes.data || []
      } catch (recErr) {
        console.warn('[Rescue] 无设备或拉取传感器失败，降级为纯气象救场:', recErr)
      }

      // 目标鱼种来自出钓上下文；钓法/饵料用救场时现填的（未填则「未知」）
      const fc = app.globalData.fishContext || {}
      const context = {
        target: fc.target || 'auto',
        method: this.data.curMethod || '未知',
        bait: this.data.curBait || '未知',
      }

      // 装备上下文：优先用本次出钓勾选的装备，未设置时回退全量钓箱
      let userInventory = app.globalData.tripEquipment || null
      if (!userInventory) {
        try {
          userInventory = await api.getUserInventoryAll()
        } catch (invErr) {
          console.warn('[Rescue] 拉取装备库失败，降级为通用建议:', invErr)
        }
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
