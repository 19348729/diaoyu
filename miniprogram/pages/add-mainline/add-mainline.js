const api = require('../../utils/api');

Page({
  data: {
    editId: '',
    size: '',
    length: ''
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
          this.setData({
            size: line.size.toString(),
            length: line.length.toString()
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

  onSizeInput(e) {
    this.setData({ size: e.detail.value });
  },

  onLengthInput(e) {
    this.setData({ length: e.detail.value });
  },

  saveMainLine() {
    const { editId, size, length } = this.data;

    if (!size.trim() || !length.trim()) {
      wx.showToast({ title: '线号和米数均不能为空', icon: 'none' });
      return;
    }

    const parsedSize = parseFloat(size.trim());
    const parsedLength = parseFloat(length.trim());

    if (isNaN(parsedSize) || parsedSize <= 0) {
      wx.showToast({ title: '请输入合法的线号数值', icon: 'none' });
      return;
    }

    if (isNaN(parsedLength) || parsedLength <= 0) {
      wx.showToast({ title: '请输入合法的长度数值', icon: 'none' });
      return;
    }

    const payload = {
      size: parsedSize,
      length: parsedLength
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