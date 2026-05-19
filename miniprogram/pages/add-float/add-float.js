const api = require('../../utils/api');

Page({
  data: {
    editId: '',
    
    // 规格定义
    leadOptions: ['0.1克', '0.2克', '0.3克', '0.4克', '0.5克', '0.6克', '0.8克', '1.0克', '1.2克', '1.5克', '2.0克', '2.5克', '3.0克', '3.5克', '4.0克', '5.0克', '6.0克', '7.0克', '8.0克', '10.0克'],
    leads: [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 1.0, 1.2, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0, 7.0, 8.0, 10.0],
    
    materialOptions: ['芦苇', '纳米', '孔雀羽', '巴尔沙木', '碳纤维'],
    
    shapeOptions: ['细长身', '枣核型', '短身', '橄榄型', '球型'],
    
    tailTypeOptions: ['软尾', '硬尾'],

    // 选中索引
    leadIndex: -1,
    materialIndex: -1,
    shapeIndex: -1,
    tailTypeIndex: -1,

    // 是否展示对照图
    showGuide: false
  },

  onLoad(options) {
    if (options.id) {
      this.setData({ editId: options.id });
      this.loadFloatDetail(options.id);
    }
  },

  loadFloatDetail(id) {
    wx.showLoading({ title: '加载中...' });
    api.getUserFloat(id)
      .then((res) => {
        wx.hideLoading();
        if (res.status === 'ok' && res.data) {
          const f = res.data;
          
          // 根据值匹配索引
          const leadIndex = this.data.leads.findIndex(l => parseFloat(l) === parseFloat(f.lead));
          const materialIndex = this.data.materialOptions.indexOf(f.material);
          const shapeIndex = this.data.shapeOptions.indexOf(f.shape);
          const tailTypeIndex = this.data.tailTypeOptions.indexOf(f.tail_type);
          
          this.setData({
            leadIndex: leadIndex,
            materialIndex: materialIndex,
            shapeIndex: shapeIndex,
            tailTypeIndex: tailTypeIndex
          });
        } else {
          wx.showToast({ title: '加载浮漂失败', icon: 'none' });
        }
      })
      .catch((err) => {
        wx.hideLoading();
        console.error('[AddFloat] 获取浮漂详情失败:', err);
        wx.showToast({ title: '获取详情失败', icon: 'none' });
      });
  },

  toggleGuide() {
    this.setData({
      showGuide: !this.data.showGuide
    });
  },

  onLeadChange(e) {
    this.setData({
      leadIndex: parseInt(e.detail.value)
    });
  },

  onMaterialChange(e) {
    this.setData({
      materialIndex: parseInt(e.detail.value)
    });
  },

  onShapeChange(e) {
    this.setData({
      shapeIndex: parseInt(e.detail.value),
      // 当用户选择漂型时，自动展开对照图供用户确认
      showGuide: true
    });
  },

  onTailTypeChange(e) {
    this.setData({
      tailTypeIndex: parseInt(e.detail.value)
    });
  },

  saveFloat() {
    const { editId, leadIndex, materialIndex, shapeIndex, tailTypeIndex, leads, materialOptions, shapeOptions, tailTypeOptions } = this.data;

    if (leadIndex < 0) {
      wx.showToast({ title: '请选择浮漂吃铅量', icon: 'none' });
      return;
    }

    if (materialIndex < 0) {
      wx.showToast({ title: '请选择浮漂材质', icon: 'none' });
      return;
    }

    if (shapeIndex < 0) {
      wx.showToast({ title: '请选择浮漂漂型', icon: 'none' });
      return;
    }

    if (tailTypeIndex < 0) {
      wx.showToast({ title: '请选择漂尾类型', icon: 'none' });
      return;
    }

    const payload = {
      lead: leads[leadIndex],
      material: materialOptions[materialIndex],
      shape: shapeOptions[shapeIndex],
      tail_type: tailTypeOptions[tailTypeIndex]
    };

    wx.showLoading({ title: '保存中...' });
    const requestPromise = editId
      ? api.updateUserFloat(editId, payload)
      : api.addUserFloat(payload);

    requestPromise
      .then((res) => {
        wx.hideLoading();
        if (res.status === 'ok') {
          wx.showToast({ title: '保存成功', icon: 'success' });
          
          // 通知上级页面刷新装备库
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
        console.error('[AddFloat] 保存浮漂失败:', err);
        wx.showToast({ title: '网络错误，保存失败', icon: 'none' });
      });
  }
});
