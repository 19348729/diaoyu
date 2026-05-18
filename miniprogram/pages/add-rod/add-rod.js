const app = getApp();

Page({
  data: {
    brands: [],
    brandNames: [],
    selectedBrandIndex: -1,
    
    seriesList: [],
    seriesNames: [],
    selectedSeriesIndex: -1,
    
    lengths: [],
    selectedLengthIndex: -1,

    isCustom: false, // 是否是手填品牌
    customBrand: '',
    customSeries: '',
    customLength: ''
  },

  onLoad() {
    this.fetchRodDatabase();
  },

  fetchRodDatabase() {
    // In real app, call wx.request to /api/inventory/rods
    // For demo, we use hardcoded from domain/rods.py to avoid networking issues during preview
    const mockData = [
      {
        brand: "化氏",
        seriesList: [
          { id: "hs_yiwei_ex", series: "一味EX", action: "28调", lengths: [3.6, 4.5, 5.4, 6.3, 7.2, 8.1] },
          { id: "hs_longwen_li", series: "龙纹鲤", action: "19调", lengths: [4.5, 5.4, 6.3, 7.2, 8.1, 9.0] }
        ]
      },
      {
        brand: "汉鼎",
        seriesList: [
          { id: "hd_luowengang", series: "螺纹钢", action: "19调", lengths: [4.5, 5.4, 6.3, 7.2, 8.1, 9.0, 10.0] },
          { id: "hd_yihao", series: "汉鼎1号", action: "37调", lengths: [2.7, 3.6, 4.5, 5.4, 6.3, 7.2] }
        ]
      },
      {
        brand: "达亿瓦",
        seriesList: [
          { id: "dw_bowen_li", series: "波纹鲤", action: "28调", lengths: [3.6, 4.5, 5.4, 6.3, 7.2] },
          { id: "dw_yige", series: "一击", action: "19调", lengths: [4.5, 5.4, 6.3, 7.2] }
        ]
      },
      {
        brand: "其它品牌 (手动验证)...",
        seriesList: []
      }
    ];

    const brandNames = mockData.map(item => item.brand);
    this.setData({ 
      brands: mockData,
      brandNames: brandNames
    });
  },

  onBrandChange(e) {
    const index = parseInt(e.detail.value);
    const selectedBrandName = this.data.brandNames[index];
    
    if (selectedBrandName.includes('其它')) {
      this.setData({
        isCustom: true,
        selectedBrandIndex: index,
        seriesList: [],
        seriesNames: [],
        lengths: [],
        selectedSeriesIndex: -1,
        selectedLengthIndex: -1
      });
      return;
    }

    const series = this.data.brands[index].seriesList;
    const seriesNames = series.map(s => s.series + ' (' + s.action + ')');

    this.setData({
      isCustom: false,
      selectedBrandIndex: index,
      seriesList: series,
      seriesNames: seriesNames,
      selectedSeriesIndex: -1,
      lengths: [],
      selectedLengthIndex: -1
    });
  },

  onSeriesChange(e) {
    const index = parseInt(e.detail.value);
    const lengths = this.data.seriesList[index].lengths;
    const lengthNames = lengths.map(l => l + '米');

    this.setData({
      selectedSeriesIndex: index,
      lengths: lengthNames,
      selectedLengthIndex: -1
    });
  },

  onLengthChange(e) {
    this.setData({
      selectedLengthIndex: parseInt(e.detail.value)
    });
  },

  onCustomBrandInput(e) {
    this.setData({ customBrand: e.detail.value });
  },
  onCustomSeriesInput(e) {
    this.setData({ customSeries: e.detail.value });
  },
  onCustomLengthInput(e) {
    this.setData({ customLength: e.detail.value });
  },

  saveRod() {
    let payload = {};

    if (this.data.isCustom) {
      if (!this.data.customBrand || !this.data.customSeries || !this.data.customLength) {
        wx.showToast({ title: '请填写完整信息', icon: 'none' });
        return;
      }
      payload = {
        brand: this.data.customBrand,
        series: this.data.customSeries,
        length: parseFloat(this.data.customLength),
        action: "未知调性",
        is_custom: true
      };
    } else {
      if (this.data.selectedBrandIndex < 0 || this.data.selectedSeriesIndex < 0 || this.data.selectedLengthIndex < 0) {
        wx.showToast({ title: '请完整选择鱼竿信息', icon: 'none' });
        return;
      }
      const brand = this.data.brandNames[this.data.selectedBrandIndex];
      const seriesObj = this.data.seriesList[this.data.selectedSeriesIndex];
      const length = parseFloat(this.data.lengths[this.data.selectedLengthIndex].replace('米', ''));
      
      payload = {
        brand: brand,
        series: seriesObj.series,
        length: length,
        action: seriesObj.action,
        is_custom: false
      };
    }

    wx.showLoading({ title: '保存中...' });
    wx.request({
      url: 'http://127.0.0.1:8000/api/inventory/rod', // 替换为正式域名
      method: 'POST',
      data: payload,
      header: {
        'X-OpenID': app.globalData.openid || 'test_openid_user_001'
      },
      success: (res) => {
        wx.hideLoading();
        if (res.data.status === 'ok') {
          wx.showToast({ title: '保存成功', icon: 'success' });
          // Notify previous page to refresh
          const pages = getCurrentPages();
          const prevPage = pages[pages.length - 2];
          if (prevPage && prevPage.loadUserInventory) {
            prevPage.loadUserInventory();
          }
          setTimeout(() => {
            wx.navigateBack();
          }, 1500);
        } else {
          wx.showToast({ title: '保存失败', icon: 'none' });
        }
      },
      fail: () => {
        wx.hideLoading();
        wx.showToast({ title: '网络错误', icon: 'none' });
      }
    });
  }
});
