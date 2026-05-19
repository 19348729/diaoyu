const api = require('../../utils/api');

Page({
  data: {
    editId: '',
    
    // 规格定义
    lineSizeOptions: ['0.15号', '0.2号', '0.3号', '0.4号', '0.6号', '0.8号', '1.0号', '1.2号', '1.5号', '2.0号', '2.5号', '3.0号'],
    lineSizes: [0.15, 0.2, 0.3, 0.4, 0.6, 0.8, 1.0, 1.2, 1.5, 2.0, 2.5, 3.0],
    
    hookTypeOptions: ['袖钩', '伊势尼', '伊豆', '新关东', '海夕', '千又', '溪流钩'],
    
    hookSizeOptions: ['0.1号', '0.3号', '0.5号', '0.8号', '1号', '2号', '3号', '4号', '5号', '6号', '7号', '8号', '9号', '10号', '11号', '12号', '13号', '14号', '15号'],

    // 选中索引
    lineSizeIndex: -1,
    hookTypeIndex: -1,
    hookSizeIndex: -1
  },

  onLoad(options) {
    if (options.id) {
      this.setData({ editId: options.id });
      this.loadSubLineHookDetail(options.id);
    }
  },

  loadSubLineHookDetail(id) {
    wx.showLoading({ title: '加载中...' });
    api.getUserSubLineHook(id)
      .then((res) => {
        wx.hideLoading();
        if (res.status === 'ok' && res.data) {
          const sub = res.data;
          
          // 根据值匹配索引
          const lineSizeIndex = this.data.lineSizes.findIndex(s => parseFloat(s) === parseFloat(sub.lineSize));
          const hookTypeIndex = this.data.hookTypeOptions.indexOf(sub.hookType);
          const hookSizeIndex = this.data.hookSizeOptions.indexOf(sub.hookSize);
          
          this.setData({
            lineSizeIndex: lineSizeIndex,
            hookTypeIndex: hookTypeIndex,
            hookSizeIndex: hookSizeIndex
          });
        } else {
          wx.showToast({ title: '加载子线双钩失败', icon: 'none' });
        }
      })
      .catch((err) => {
        wx.hideLoading();
        console.error('[AddSubLineHook] 获取子线双钩详情失败:', err);
        wx.showToast({ title: '获取详情失败', icon: 'none' });
      });
  },

  onLineSizeChange(e) {
    this.setData({
      lineSizeIndex: parseInt(e.detail.value)
    });
  },

  onHookTypeChange(e) {
    this.setData({
      hookTypeIndex: parseInt(e.detail.value)
    });
  },

  onHookSizeChange(e) {
    this.setData({
      hookSizeIndex: parseInt(e.detail.value)
    });
  },

  saveSubLineHook() {
    const { editId, lineSizeIndex, hookTypeIndex, hookSizeIndex, lineSizes, hookTypeOptions, hookSizeOptions } = this.data;

    if (lineSizeIndex < 0) {
      wx.showToast({ title: '请选择子线线号', icon: 'none' });
      return;
    }

    if (hookTypeIndex < 0) {
      wx.showToast({ title: '请选择鱼钩型号', icon: 'none' });
      return;
    }

    if (hookSizeIndex < 0) {
      wx.showToast({ title: '请选择鱼钩大小', icon: 'none' });
      return;
    }

    const payload = {
      line_size: lineSizes[lineSizeIndex],
      hook_type: hookTypeOptions[hookTypeIndex],
      hook_size: hookSizeOptions[hookSizeIndex]
    };

    wx.showLoading({ title: '保存中...' });
    const requestPromise = editId
      ? api.updateUserSubLineHook(editId, payload)
      : api.addUserSubLineHook(payload);

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
        console.error('[AddSubLineHook] 保存子线双钩失败:', err);
        wx.showToast({ title: '网络错误，保存失败', icon: 'none' });
      });
  }
});
