Page({
  data: {
    tabs: ['鱼竿', '主线', '子线双钩', '浮漂', '饵料'],
    currentTab: 0,
    
    // Mock inventory data
    inventory: {
      rods: [
        { id: 'r1', length: 3.6, action: '37调', type: '台钓竿', name: '竹山' },
        { id: 'r2', length: 4.5, action: '28调', type: '台钓竿', name: '一味' },
        { id: 'r3', length: 5.4, action: '19调', type: '台钓竿', name: '大物版' }
      ],
      mainLines: [
        { id: 'm1', size: 1.0, length: 3.6 },
        { id: 'm2', size: 1.5, length: 4.5 },
        { id: 'm3', size: 3.0, length: 5.4 }
      ],
      subLineHooks: [
        { id: 's1', lineSize: 0.6, hookType: '袖钩', hookSize: 3, barb: '无刺' },
        { id: 's2', lineSize: 1.0, hookType: '伊豆', hookSize: 4, barb: '有刺' },
        { id: 's3', lineSize: 2.0, hookType: '伊势尼', hookSize: 7, barb: '有刺' }
      ],
      floats: [
        { id: 'f1', name: '浅水漂', material: '芦苇', shape: '细长身', lead: 1.2 },
        { id: 'f2', name: '大底漂', material: '纳米', shape: '枣核型', lead: 3.5 }
      ],
      baits: [
        { id: 'lg_918_yezhan', brand: '老鬼', name: '九一八野战篇', flavor: '麸香' },
        { id: 'lg_yeluans_blue', brand: '老鬼', name: '野战蓝鲫', flavor: '香腥' },
        { id: 'nb_nanbeiling', brand: '南北', name: '南北钓鲮', flavor: '腥香' },
        { id: 'state_lasi_fen', brand: '辅料', name: '拉丝粉', flavor: '状态' }
      ]
    }
  },

  onLoad() {
    this.loadUserInventory();
  },
  
  onShow() {
    // Optionally refresh when coming back from add-rod
    this.loadUserInventory();
  },

  loadUserInventory() {
    const app = getApp();
    wx.request({
      url: 'http://127.0.0.1:8000/api/inventory/rods/user', // 替换为正式域名
      method: 'GET',
      header: {
        'X-OpenID': app.globalData?.openid || 'test_openid_user_001'
      },
      success: (res) => {
        if (res.data.status === 'ok') {
          this.setData({
            'inventory.rods': res.data.data
          });
        }
      }
    });
  },

  switchTab(e) {
    const index = parseInt(e.currentTarget.dataset.index);
    this.setData({ currentTab: index });
  },

  addGear() {
    if (this.data.currentTab === 0) {
      wx.navigateTo({
        url: '/pages/add-rod/add-rod'
      });
    } else {
      wx.showToast({
        title: '该类目暂未开放录入',
        icon: 'none'
      });
    }
  }
});
