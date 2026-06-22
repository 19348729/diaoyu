const app = getApp()
const ble = require('../../utils/ble')
const api = require('../../utils/api')

// 「智能推荐」对应后端 fish_type = 'auto'
const AUTO_LABEL = '智能推荐'

// 各鱼种的习性提示（仅信息展示；具体钓法/用饵由大屏的智能策略给出，开局不再让用户预选）
const FISH_TIP = {
  '智能推荐': '💡 系统会综合水温/气压/季节/月相，自动推荐当前最适宜的鱼种与策略',
  '鲫鱼': '💡 鲫鱼分布广、群集索食，四季可钓，最适合新手与多数水域',
  '鲤鱼': '💡 鲤鱼生性警惕、偏爱自然谷物，多在深水底层活动',
  '罗非鱼': '💡 罗非喜温、抢食凶猛，水温高时鱼口好',
  '鲢鳙': '💡 鲢鳙滤食、喜温喜酸臭，多在中上层水域',
  '草鱼': '💡 草鱼喜嫩草谷物，体型大、冲击力强',
  '翘嘴': '💡 翘嘴行动迅速、中上层掠食，多用路亚/浮钓',
  '土鲮': '💡 土鲮喜腥甜、底栖掘泥，南方水域常见',
  '塘鲺': '💡 塘鲺肉食底栖、喜大腥，耐低氧',
  '大口黑鲈': '💡 黑鲈掠食性强，路亚对象鱼',
}

Page({
  data: {
    // 第一项为「智能推荐」(auto)，其余为具体目标鱼种
    fishOptions: [AUTO_LABEL, '鲫鱼', '鲤鱼', '罗非鱼', '鲢鳙', '草鱼', '翘嘴', '土鲮', '塘鲺', '大口黑鲈'],

    targetFish: AUTO_LABEL,
    recommendationTip: FISH_TIP[AUTO_LABEL],

    // 钓点情况（仅影响战术建议，不改开口指数）。默认值=不确定/正常 视为未填
    spotTypeOptions: ['不确定', '黑坑', '野河', '水库', '江河', '池塘'],
    spotDensityOptions: ['不确定', '鱼多', '一般', '鱼少'],
    spotClarityOptions: ['正常', '清', '浑浊'],
    spotType: '不确定',
    spotDensity: '不确定',
    spotClarity: '正常',

    // 本次出钓装备（默认全选；钓友可勾掉没带的）
    showEquip: false,
    equipLoaded: false,
    equip: { rods: [], mainLines: [], subLineHooks: [], floats: [], baits: [] },

    isConnecting: false,
    isConnected: false,
    isModifying: false,
    savedContext: null
  },

  onLoad() {
    const bleManager = ble.getBLEManager()
    this._ble = bleManager

    // 注册连接状态回调，使 setup 页能跟随实时监测页的断开/连接事件刷新
    bleManager.onConnect((connected) => {
      this._syncConnectionState(connected)
    })

    // 首次进入：若已连接则恢复全局上下文（'auto' 回显为「智能推荐」）
    if (bleManager.isConnected) {
      const fishContext = app.globalData.fishContext || {}
      const tf = (!fishContext.target || fishContext.target === 'auto')
        ? AUTO_LABEL : fishContext.target
      this.setData({
        isConnected: true,
        targetFish: tf,
        recommendationTip: FISH_TIP[tf] || ''
      })
    }

    // 拉取数字钓箱，渲染「本次出钓装备」勾选列表（默认全选）
    this._loadEquipment()
  },

  onShow() {
    // 从其他页面（如实时监测大屏）切回时，强制以 BLE 真实状态为准刷新
    if (this._ble) {
      this._syncConnectionState(this._ble.isConnected)
    }
  },

  /**
   * 同步 BLE 连接状态到页面 data
   * 断开时清除 isModifying，避免卡在修改态
   */
  _syncConnectionState(connected) {
    if (this.data.isConnected === connected) return
    if (connected) {
      this.setData({ isConnected: true })
    } else {
      this.setData({
        isConnected: false,
        isModifying: false,
        savedContext: null,
        isConnecting: false
      })
    }
  },

  // ── 目标鱼种选择（开局只需声明目标鱼种或智能推荐） ──────────

  selectFish(e) {
    const fish = e.currentTarget.dataset.val
    this.setData({
      targetFish: fish,
      recommendationTip: FISH_TIP[fish] || ''
    })
  },

  selectSpotType(e) { this.setData({ spotType: e.currentTarget.dataset.val }) },
  selectSpotDensity(e) { this.setData({ spotDensity: e.currentTarget.dataset.val }) },
  selectSpotClarity(e) { this.setData({ spotClarity: e.currentTarget.dataset.val }) },

  // ── 本次出钓装备勾选 ────────────────────────────────────

  /** 拉取全量钓箱并初始化为全选 */
  _loadEquipment() {
    api.getUserInventoryAll().then(inv => {
      const mark = (arr) => (arr || []).map(it => Object.assign({}, it, { _checked: true }))
      this.setData({
        equipLoaded: true,
        equip: {
          rods: mark(inv.rods),
          mainLines: mark(inv.mainLines),
          subLineHooks: mark(inv.subLineHooks),
          floats: mark(inv.floats),
          baits: mark(inv.baits),
        }
      })
    }).catch(err => {
      console.warn('[Setup] 拉取装备库失败，跳过本次装备勾选:', err)
      this.setData({ equipLoaded: true })
    })
  },

  toggleEquipPanel() {
    this.setData({ showEquip: !this.data.showEquip })
  },

  /** 勾选/取消单件装备 */
  toggleEquipItem(e) {
    const cat = e.currentTarget.dataset.cat
    const idx = e.currentTarget.dataset.idx
    const key = `equip.${cat}[${idx}]._checked`
    const cur = this.data.equip[cat][idx]._checked
    this.setData({ [key]: !cur })
  },

  /** 全选 / 全不选 */
  toggleEquipAll(e) {
    const checked = e.currentTarget.dataset.checked === 'true'
    const equip = this.data.equip
    const next = {}
    Object.keys(equip).forEach(cat => {
      next[cat] = equip[cat].map(it => Object.assign({}, it, { _checked: checked }))
    })
    this.setData({ equip: next })
  },

  /** 组装本次勾选的装备为后端 user_inventory 结构（剔除 _checked 标记） */
  _buildTripEquipment() {
    const equip = this.data.equip
    const pick = (arr) => (arr || []).filter(it => it._checked).map(it => {
      const o = Object.assign({}, it)
      delete o._checked
      return o
    })
    return {
      rods: pick(equip.rods),
      mainLines: pick(equip.mainLines),
      subLineHooks: pick(equip.subLineHooks),
      floats: pick(equip.floats),
      baits: pick(equip.baits),
    }
  },

  /** 保存出钓上下文（目标鱼种 + 钓点情况）与本次装备到全局 */
  _saveContext() {
    app.globalData.fishContext = {
      target: this.data.targetFish === AUTO_LABEL ? 'auto' : this.data.targetFish,
    }
    // 钓点情况：默认项（不确定/正常）视为未填，置空
    app.globalData.spotContext = {
      type: this.data.spotType === '不确定' ? '' : this.data.spotType,
      density: this.data.spotDensity === '不确定' ? '' : this.data.spotDensity,
      clarity: this.data.spotClarity === '正常' ? '' : this.data.spotClarity,
    }
    if (this.data.equipLoaded) {
      app.globalData.tripEquipment = this._buildTripEquipment()
    }
  },

  // ── 出钓动作 ───────────────────────────────────────────

  startSession() {
    this.setData({ isConnecting: true })
    const bleManager = ble.getBLEManager()
    bleManager.connectDevice().then(success => {
      this.setData({
        isConnecting: false,
        isConnected: success,
        isModifying: false,
        savedContext: null
      })
      if (success) {
        this._saveContext()
        wx.showToast({ title: '设备已连接', icon: 'success' })
        setTimeout(() => {
          this.goToDashboard()
        }, 1500)
      }
    }).catch(err => {
      this.setData({ isConnecting: false })
      wx.showToast({ title: '连接失败', icon: 'none' })
    })
  },

  goToDashboard() {
    wx.navigateTo({
      url: '/pages/index/index',
    })
  },

  goToDecision() {
    this._saveContext()
    wx.navigateTo({
      url: '/pages/decision/decision',
    })
  },

  onTapModify() {
    this.setData({
      isModifying: true,
      savedContext: {
        targetFish: this.data.targetFish
      }
    })
  },

  onTapSaveModification() {
    this._saveContext()
    this.setData({
      isModifying: false,
      savedContext: null
    })
    wx.showToast({ title: '配置已更新', icon: 'success' })
  },

  onTapCancelModification() {
    if (this.data.savedContext) {
      const s = this.data.savedContext
      this.setData({
        targetFish: s.targetFish,
        recommendationTip: FISH_TIP[s.targetFish] || '',
        isModifying: false,
        savedContext: null
      })
    } else {
      this.setData({
        isModifying: false
      })
    }
  }
})
