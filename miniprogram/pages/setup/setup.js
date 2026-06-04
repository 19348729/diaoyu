const app = getApp()
const ble = require('../../utils/ble')
const api = require('../../utils/api')

// 全量钓法 / 饵料选项（始终全部可选，不再因鱼种收窄）
const ALL_METHODS = ['底钓', '浮钓', '行程', '路亚']
const ALL_BAITS = ['香腥', '本味', '活饵', '玉米/颗粒', '酸臭/发酵', '拟饵']

// 各鱼种的「推荐」钓法/饵料与默认首选（仅作高亮与默认值，用户可自由改选）
const FISH_RECO = {
  '土鲮':   { methods: ['底钓'],               defMethod: '底钓', baits: ['香腥', '本味', '活饵'],        defBait: '香腥',
              tip: '💡 土鲮喜腥甜、底栖掘泥，推荐「底钓」+腥香型饵料（仍可自由改选）' },
  '鲤鱼':   { methods: ['底钓'],               defMethod: '底钓', baits: ['本味', '玉米/颗粒', '香腥'],   defBait: '本味',
              tip: '💡 鲤鱼警惕、偏爱自然谷物，推荐「底钓」+「本味/谷物」颗粒饵' },
  '塘鲺':   { methods: ['底钓'],               defMethod: '底钓', baits: ['活饵', '香腥'],                defBait: '活饵',
              tip: '💡 塘鲺肉食底栖、喜大腥，推荐「底钓」+高活性「活饵」' },
  '鲢鳙':   { methods: ['浮钓'],               defMethod: '浮钓', baits: ['酸臭/发酵', '香腥'],           defBait: '酸臭/发酵',
              tip: '💡 鲢鳙滤食、喜温喜酸臭，推荐「浮钓」+「酸臭/发酵」雾化饵' },
  '大口黑鲈': { methods: ['路亚'],             defMethod: '路亚', baits: ['拟饵'],                       defBait: '拟饵',
              tip: '💡 黑鲈掠食性，推荐「路亚」+运动「拟饵」' },
  '翘嘴':   { methods: ['路亚', '浮钓', '行程'], defMethod: '路亚', baits: ['拟饵', '活饵', '本味'],       defBait: '拟饵',
              tip: '💡 翘嘴迅猛、中上层觅食，推荐「路亚/浮钓」+「拟饵/活饵」' },
  '罗非鱼': { methods: ['底钓', '浮钓'],        defMethod: '底钓', baits: ['香腥', '本味', '活饵'],        defBait: '香腥',
              tip: '💡 罗非喜温、抢食凶猛，推荐「底钓/浮钓」+「香腥/活饵」' },
  '草鱼':   { methods: ['底钓', '浮钓'],        defMethod: '底钓', baits: ['玉米/颗粒', '本味'],          defBait: '玉米/颗粒',
              tip: '💡 草鱼喜嫩草谷物，推荐「底钓/浮钓」+「玉米/颗粒」' },
  '鲫鱼':   { methods: ['底钓', '浮钓', '行程'], defMethod: '底钓', baits: ['香腥', '本味', '活饵'],       defBait: '香腥',
              tip: '💡 鲫鱼分布广、群集索食，推荐高灵敏「底/浮/行程」+「香腥/本味/活饵」' },
}

Page({
  data: {
    fishOptions: ['土鲮', '鲢鳙', '草鱼', '罗非鱼', '鲫鱼', '鲤鱼', '塘鲺', '大口黑鲈', '翘嘴'],

    // 钓法 / 饵料：始终全量展示，recommended 标记仅用于高亮
    methodList: ALL_METHODS.map(n => ({ name: n, recommended: n === '底钓' })),
    baitList: ALL_BAITS.map(n => ({ name: n, recommended: n === '香腥' })),

    targetFish: '土鲮',
    method: '底钓',
    bait: '香腥',
    recommendationTip: '💡 土鲮底栖掘泥，已为你高亮推荐「底钓」与腥香饵料，可自由改选',

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

    // 首次进入：若已连接则恢复全局上下文
    if (bleManager.isConnected) {
      const fishContext = app.globalData.fishContext || {}
      this.setData({
        isConnected: true,
        targetFish: fishContext.target || '土鲮',
        method: fishContext.method || '底钓',
        bait: fishContext.bait || '香腥'
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

  // ── 鱼种 / 钓法 / 饵料选择 ──────────────────────────────

  selectFish(e) {
    const fish = e.currentTarget.dataset.val
    const reco = FISH_RECO[fish] || { methods: [], defMethod: this.data.method, baits: [], defBait: this.data.bait, tip: '' }

    // 仅更新「推荐高亮」与默认首选，绝不收窄可选项
    const methodList = ALL_METHODS.map(n => ({ name: n, recommended: reco.methods.includes(n) }))
    const baitList = ALL_BAITS.map(n => ({ name: n, recommended: reco.baits.includes(n) }))

    this.setData({
      targetFish: fish,
      methodList,
      baitList,
      method: reco.defMethod || this.data.method,
      bait: reco.defBait || this.data.bait,
      recommendationTip: reco.tip ? reco.tip + '（可自由改选）' : ''
    })
  },

  selectMethod(e) { this.setData({ method: e.currentTarget.dataset.val }) },
  selectBait(e) { this.setData({ bait: e.currentTarget.dataset.val }) },

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

  /** 保存出钓上下文（鱼种/钓法/饵料）与本次装备到全局 */
  _saveContext() {
    app.globalData.fishContext = {
      target: this.data.targetFish,
      method: this.data.method,
      bait: this.data.bait
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

  /** 无设备：直接进入实时大屏（气象预测模式） */
  goToWeatherMode() {
    this._saveContext()
    this.goToDashboard()
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
        targetFish: this.data.targetFish,
        method: this.data.method,
        bait: this.data.bait,
        methodList: this.data.methodList,
        baitList: this.data.baitList
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
        method: s.method,
        bait: s.bait,
        methodList: s.methodList,
        baitList: s.baitList,
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
