const app = getApp();
const api = require('../../utils/api');

Page({
  data: {
    editId: '', // 修改时的鱼竿ID
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

  onLoad(options) {
    if (options && options.id) {
      this.setData({
        editId: options.id
      });
    }
    this.fetchRodDatabase();
  },

  fetchRodDatabase() {
    api.getRodDatabase()
      .then((res) => {
        if (res.status === 'ok' && res.data) {
          let list = res.data;
          // 确保 "其它品牌 (手动验证)..." 始终在末尾，提供手动录入入口
          if (!list.some(item => item.brand.includes('其它'))) {
            list.push({
              brand: "其它品牌 (手动验证)...",
              seriesList: []
            });
          }
          const brandNames = list.map(item => item.brand);
          this.setData({ 
            brands: list,
            brandNames: brandNames
          }, () => {
            // 在官方库数据加载并渲染完成后，再触发详情拉取回显，避免 Picker 选项因异步导致索引计算错乱
            if (this.data.editId) {
              this.loadRodDetail(this.data.editId);
            }
          });
        } else {
          this.useFallbackDatabase();
        }
      })
      .catch((err) => {
        console.error('[AddRod] 异步获取官方品牌库失败，启用离线缓存兜底:', err);
        this.useFallbackDatabase();
      });
  },

  useFallbackDatabase() {
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
        brand: "光威",
        seriesList: [
          { id: "gw_zhushan", series: "竹山", action: "37调", lengths: [2.7, 3.6, 4.5, 5.4, 6.3] }
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
    }, () => {
      if (this.data.editId) {
        this.loadRodDetail(this.data.editId);
      }
    });
  },

  loadRodDetail(id) {
    wx.showLoading({ title: '加载中...' });
    api.getUserRod(id)
      .then((res) => {
        wx.hideLoading();
        if (res.status === 'ok' && res.data) {
          const rod = res.data;
          if (rod.is_custom) {
            this.setData({
              isCustom: true,
              customBrand: rod.brand,
              customSeries: rod.series,
              customLength: rod.length.toString(),
              selectedBrandIndex: this.data.brandNames.findIndex(b => b.includes('其它'))
            });
          } else {
            // Find matched brand
            const brandIndex = this.data.brands.findIndex(b => b.brand === rod.brand);
            if (brandIndex >= 0) {
              const seriesList = this.data.brands[brandIndex].seriesList || [];
              const seriesNames = seriesList.map(s => s.series + ' (' + s.action + ')');
              seriesNames.push("其它系列 (手动输入)...");
              const seriesIndex = seriesList.findIndex(s => s.series === rod.series);
              
              if (seriesIndex >= 0) {
                const lengths = seriesList[seriesIndex].lengths;
                const lengthNames = lengths.map(l => l + '米');
                const lengthIndex = lengths.findIndex(l => parseFloat(l) === parseFloat(rod.length));
                
                this.setData({
                  isCustom: false,
                  selectedBrandIndex: brandIndex,
                  seriesList: seriesList,
                  seriesNames: seriesNames,
                  selectedSeriesIndex: seriesIndex,
                  lengths: lengthNames,
                  selectedLengthIndex: lengthIndex
                });
              } else {
                this.setToCustom(rod);
              }
            } else {
              this.setToCustom(rod);
            }
          }
        }
      })
      .catch((err) => {
        wx.hideLoading();
        console.error('[AddRod] 加载鱼竿详情失败:', err);
        wx.showToast({ title: '加载失败', icon: 'none' });
      });
  },

  setToCustom(rod) {
    this.setData({
      isCustom: true,
      customBrand: rod.brand,
      customSeries: rod.series,
      customLength: rod.length.toString(),
      selectedBrandIndex: this.data.brandNames.findIndex(b => b.includes('其它'))
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

    const series = this.data.brands[index].seriesList || [];
    const seriesNames = series.map(s => s.series + ' (' + s.action + ')');
    seriesNames.push("其它系列 (手动输入)...");

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
    const selectedSeriesName = this.data.seriesNames[index];
    
    if (selectedSeriesName.includes('其它系列')) {
      const officialBrand = this.data.brandNames[this.data.selectedBrandIndex];
      this.setData({
        isCustom: true,
        customBrand: officialBrand,
        customSeries: '',
        customLength: '',
        selectedSeriesIndex: index,
        lengths: [],
        selectedLengthIndex: -1
      });
      return;
    }

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
    const requestPromise = this.data.editId 
      ? api.updateUserRod(this.data.editId, payload)
      : api.addUserRod(payload);

    requestPromise
      .then((res) => {
        wx.hideLoading();
        if (res.status === 'ok') {
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
          wx.showToast({ title: res.message || '保存失败', icon: 'none' });
        }
      })
      .catch((err) => {
        wx.hideLoading();
        console.error('[AddRod] 保存失败:', err);
        wx.showToast({ title: '网络错误', icon: 'none' });
      });
  }
});
