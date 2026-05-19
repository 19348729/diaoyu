const api = require('../../utils/api');

Page({
  data: {
    editId: '',
    
    // 规格定义
    sizeOptions: ['0.4号', '0.6号', '0.8号', '1.0号', '1.2号', '1.5号', '2.0号', '2.5号', '3.0号', '3.5号', '4.0号', '5.0号', '6.0号', '7.0号', '8.0号', '10.0号'],
    sizes: [0.4, 0.6, 0.8, 1.0, 1.2, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0, 7.0, 8.0, 10.0],
    
    lengthOptions: ['2.7米', '3.6米', '3.9米', '4.5米', '4.8米', '5.4米', '5.7米', '6.3米', '7.2米', '8.1米', '9.0米', '10.0米'],
    lengths: [2.7, 3.6, 3.9, 4.5, 4.8, 5.4, 5.7, 6.3, 7.2, 8.1, 9.0, 10.0],

    // 选中索引
    sizeIndex: -1,
    lengthIndex: -1
  },

  onLoad(options) {
    if (options.id) {
      this.setData({ editId: options.id });
      this.loadMainLineDetail(options.id);
    }
  },

  loadMainLineDetail(id) {
    wx.showLoading({ title: '加载中...' });
    api.getUserMainLine(id)
      .then((res) => {
        wx.hideLoading();
        if (res.status === 'ok' && res.data) {
          const line = res.data;
          
          // 根据值匹配索引
          const sizeIndex = this.data.sizes.findIndex(s => parseFloat(s) === parseFloat(line.size));
          const lengthIndex = this.data.lengths.findIndex(l => parseFloat(l) === parseFloat(line.length));
          
          this.setData({
            sizeIndex: sizeIndex,
            lengthIndex: lengthIndex
          });
        } else {
          wx.showToast({ title: '加载主线失败', icon: 'none' });
        }
      })
      .catch((err) => {
        wx.hideLoading();
        console.error('[AddMainLine] 获取主线详情失败:', err);
        wx.showToast({ title: '获取详情失败', icon: 'none' });
      });
  },

  onSizeChange(e) {
    this.setData({
      sizeIndex: parseInt(e.detail.value)
    });
  },

  onLengthChange(e) {
    this.setData({
      lengthIndex: parseInt(e.detail.value)
    });
  },

  saveMainLine() {
    const { editId, sizeIndex, lengthIndex, sizes, lengths } = this.data;

    if (sizeIndex < 0) {
      wx.showToast({ title: '请选择主线线号', icon: 'none' });
      return;
    }

    if (lengthIndex < 0) {
      wx.showToast({ title: '请选择长度/米数', icon: 'none' });
      return;
    }

    const payload = {
      size: sizes[sizeIndex],
      length: lengths[lengthIndex]
    };

    wx.showLoading({ title: '保存中...' });
    const requestPromise = editId
      ? api.updateUserMainLine(editId, payload)
      : api.addUserMainLine(payload);

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
        console.error('[AddMainLine] 保存主线失败:', err);
        wx.showToast({ title: '网络错误，保存失败', icon: 'none' });
      });
  }
});