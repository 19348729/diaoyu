const app = getApp()
const ble = require('../../utils/ble')

Page({
  data: {
    fishOptions: ['土鲮', '鲫鱼', '鲤鱼', '罗非', '草鱼'],
    methodOptions: ['底钓', '浮钓', '行程', '路亚'],
    baitOptions: ['香腥', '本味', '活饵', '玉米/颗粒'],
    
    targetFish: '土鲮',
    method: '底钓',
    bait: '香腥',

    isConnecting: false,
    isConnected: false
  },

  onLoad() {
    // If already connected, maybe update state
    const bleManager = ble.getBLEManager()
    if (bleManager.isConnected) {
      this.setData({ isConnected: true })
    }
  },

  selectFish(e) { this.setData({ targetFish: e.currentTarget.dataset.val }) },
  selectMethod(e) { this.setData({ method: e.currentTarget.dataset.val }) },
  selectBait(e) { this.setData({ bait: e.currentTarget.dataset.val }) },

  startSession() {
    this.setData({ isConnecting: true })
    const bleManager = ble.getBLEManager()
    bleManager.connectDevice().then(success => {
      this.setData({ 
        isConnecting: false,
        isConnected: success
      })
      if (success) {
        // Save to global context
        app.globalData.fishContext = {
          target: this.data.targetFish,
          method: this.data.method,
          bait: this.data.bait
        }
        wx.showToast({ title: '设备已连接', icon: 'success' })
        // We could also call POST /api/v2/session/start here
      }
    }).catch(err => {
      this.setData({ isConnecting: false })
      wx.showToast({ title: '连接失败', icon: 'none' })
    })
  }
})
