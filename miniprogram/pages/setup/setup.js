const app = getApp()
const ble = require('../../utils/ble')

Page({
  data: {
    fishOptions: ['土鲮', '鲢鳙', '草鱼', '罗非鱼', '鲫鱼', '鲤鱼', '塘鲺', '大口黑鲈', '翘嘴'],
    methodOptions: ['底钓'],
    baitOptions: ['香腥', '本味', '活饵', '玉米/颗粒', '酸臭/发酵', '拟饵'],
    
    targetFish: '土鲮',
    method: '底钓',
    bait: '香腥',
    recommendationTip: '💡 土鲮底栖掘泥，已自动为您锁定最适合的「底钓」与腥香饵料',

    isConnecting: false,
    isConnected: false,
    isModifying: false,
    savedContext: null
  },

  onLoad() {
    // If already connected, restore global fishContext and update state
    const bleManager = ble.getBLEManager()
    if (bleManager.isConnected) {
      const fishContext = app.globalData.fishContext || {}
      this.setData({
        isConnected: true,
        targetFish: fishContext.target || '土鲮',
        method: fishContext.method || '底钓',
        bait: fishContext.bait || '香腥'
      })
    }
  },

  selectFish(e) { 
    const fish = e.currentTarget.dataset.val;
    let methods = ['底钓', '浮钓', '行程', '路亚'];
    let baits = ['香腥', '本味', '活饵', '玉米/颗粒', '酸臭/发酵', '拟饵'];
    let defaultMethod = this.data.method;
    let defaultBait = this.data.bait;
    let tip = '';

    // 逻辑纠错与智能推荐
    if (fish === '土鲮' || fish === '鲤鱼' || fish === '塘鲺') {
      methods = ['底钓'];
      defaultMethod = '底钓';
      if (fish === '土鲮') {
        baits = ['香腥', '本味', '活饵'];
        defaultBait = '香腥';
        tip = '💡 土鲮喜腥甜、底栖掘泥，已自动锁定「底钓」并推荐腥香型饵料';
      } else if (fish === '鲤鱼') {
        baits = ['本味', '玉米/颗粒', '香腥'];
        defaultBait = '本味';
        tip = '💡 鲤鱼生性警惕、偏爱自然谷物，已锁定「底钓」并推荐原塘「本味/谷物」颗粒饵';
      } else if (fish === '塘鲺') {
        baits = ['活饵', '香腥'];
        defaultBait = '活饵';
        tip = '💡 塘鲺为肉食性底栖鱼，喜大腥，已锁定「底钓」与高活性「活饵」配置';
      }
    } else if (fish === '鲢鳙') {
      methods = ['浮钓'];
      defaultMethod = '浮钓';
      baits = ['酸臭/发酵', '香腥'];
      defaultBait = '酸臭/发酵';
      tip = '💡 鲢鳙喜温喜酸臭，滤食性强，已推荐「浮钓」及主攻「酸臭/发酵」雾化饵';
    } else if (fish === '大口黑鲈') {
      methods = ['路亚'];
      defaultMethod = '路亚';
      baits = ['拟饵'];
      defaultBait = '拟饵';
      tip = '💡 黑鲈属于掠食性鱼类，已为您锁定「路亚」及最吸引它的运动「拟饵」';
    } else if (fish === '翘嘴') {
      methods = ['路亚', '浮钓', '行程'];
      baits = ['拟饵', '活饵', '本味'];
      if (defaultMethod === '底钓') defaultMethod = '路亚';
      if (defaultBait === '酸臭/发酵' || defaultBait === '玉米/颗粒') defaultBait = '拟饵';
      tip = '💡 翘嘴行动迅速、中上层觅食，已过滤底钓，推荐「路亚/浮钓」和「拟饵/活饵」';
    } else if (fish === '罗非鱼' || fish === '草鱼') {
      methods = ['底钓', '浮钓'];
      if (defaultMethod === '行程' || defaultMethod === '路亚') defaultMethod = '底钓';
      if (fish === '罗非鱼') {
        baits = ['香腥', '本味', '活饵'];
        defaultBait = '香腥';
        tip = '💡 罗非喜温、抢食凶猛，已适配「底钓/浮钓」并推荐诱惑力强的「香腥/活饵」';
      } else {
        baits = ['玉米/颗粒', '本味'];
        defaultBait = '玉米/颗粒';
        tip = '💡 草鱼喜食嫩草与谷物，已匹配「底钓/浮钓」和原生态「玉米/颗粒」饵';
      }
    } else if (fish === '鲫鱼') {
      methods = ['底钓', '浮钓', '行程'];
      baits = ['香腥', '本味', '活饵'];
      if (defaultMethod === '路亚') defaultMethod = '底钓';
      if (defaultBait === '拟饵' || defaultBait === '酸臭/发酵') defaultBait = '香腥';
      tip = '💡 鲫鱼分布广泛、群集索食，已匹配高灵敏「底/浮/行程」与「香腥/本味/活饵」';
    }

    this.setData({ 
      targetFish: fish,
      methodOptions: methods,
      method: methods.includes(this.data.method) ? this.data.method : defaultMethod,
      baitOptions: baits,
      bait: baits.includes(this.data.bait) ? this.data.bait : defaultBait,
      recommendationTip: tip
    });
  },
  selectMethod(e) { this.setData({ method: e.currentTarget.dataset.val }) },
  selectBait(e) { this.setData({ bait: e.currentTarget.dataset.val }) },

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
        // Save to global context
        app.globalData.fishContext = {
          target: this.data.targetFish,
          method: this.data.method,
          bait: this.data.bait
        }
        wx.showToast({ title: '设备已连接', icon: 'success' })
        // We could also call POST /api/v2/session/start here
        setTimeout(() => {
          this.goToDashboard();
        }, 1500);
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
        methodOptions: this.data.methodOptions,
        baitOptions: this.data.baitOptions
      }
    })
  },

  onTapSaveModification() {
    app.globalData.fishContext = {
      target: this.data.targetFish,
      method: this.data.method,
      bait: this.data.bait
    }
    this.setData({
      isModifying: false,
      savedContext: null
    })
    wx.showToast({ title: '配置已更新', icon: 'success' })
  },

  onTapCancelModification() {
    if (this.data.savedContext) {
      const s = this.data.savedContext;
      this.setData({
        targetFish: s.targetFish,
        method: s.method,
        bait: s.bait,
        methodOptions: s.methodOptions,
        baitOptions: s.baitOptions,
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
