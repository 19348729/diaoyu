const api = require('../../utils/api');
const { translateTags } = require('../../utils/tagMap');

Page({
  data: {
    logs: [],
    loading: true,
  },

  onLoad() {
    this.fetchLogs();
  },

  onPullDownRefresh() {
    this.fetchLogs().then(() => {
      wx.stopPullDownRefresh();
    });
  },

  onShow() {
    // 每次展示页面时静默刷新一下
    this.fetchLogs();
  },

  fetchLogs() {
    this.setData({ loading: true });
    return api.getPredictionLogs(20)
      .then((res) => {
        if (res.status === 'ok' && res.data) {
          // 处理数据，翻译 tag 等
          const formattedLogs = res.data.map(log => {
            return {
              ...log,
              tags: translateTags(log.tags || [])
            };
          });
          this.setData({
            logs: formattedLogs,
            loading: false
          });
        } else {
          this.setData({ loading: false });
        }
      })
      .catch((err) => {
        console.error('获取日志失败', err);
        wx.showToast({
          title: '获取历史失败',
          icon: 'none'
        });
        this.setData({ loading: false });
      });
  }
});
