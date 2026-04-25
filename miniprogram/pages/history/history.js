/**
 * 趋势分析页面
 * 展示传感器历史数据的变化趋势（列表形式，适配小程序原生能力）
 */
const app = getApp();

Page({
  data: {
    // 数据列表（倒序，最新在前）
    records: [],
    recordCount: 0,

    // 统计摘要
    summary: {
      tBottomMin: '--',
      tBottomMax: '--',
      tSurfaceMin: '--',
      tSurfaceMax: '--',
      pLocalMin: '--',
      pLocalMax: '--',
      tDiffMax: '--',
      duration: '--',
    },

    // 筛选
    filterType: 'all', // all | temp | pressure
  },

  onShow() {
    this._refreshData();
  },

  /**
   * 下拉刷新
   */
  onPullDownRefresh() {
    this._refreshData();
    wx.stopPullDownRefresh();
  },

  /**
   * 切换筛选类型
   */
  onFilterChange(e) {
    this.setData({ filterType: e.currentTarget.dataset.type });
  },

  /**
   * 刷新数据
   */
  _refreshData() {
    const history = app.globalData.historyData || [];
    const count = history.length;

    if (count === 0) {
      this.setData({ records: [], recordCount: 0 });
      return;
    }

    // 倒序（最新在前），最多显示 200 条
    const displayRecords = history
      .slice(-200)
      .reverse()
      .map((r) => ({
        ...r,
        timeStr: this._formatTime(r.timestamp),
        tBottomStr: r.tBottom !== null ? r.tBottom.toFixed(1) : '--',
        tMidStr: r.tMid !== null ? r.tMid.toFixed(1) : '--',
        tSurfaceStr: r.tSurface !== null ? r.tSurface.toFixed(1) : '--',
        tDiffStr: r.tDiff !== null ? r.tDiff.toFixed(1) : '--',
        pLocalStr: r.pLocal !== null ? r.pLocal.toFixed(1) : '--',
        tDiffWarn: r.tDiff !== null && r.tDiff > 5,
      }));

    // 计算统计摘要
    const summary = this._calcSummary(history);

    this.setData({
      records: displayRecords,
      recordCount: count,
      summary,
    });
  },

  /**
   * 计算统计摘要
   */
  _calcSummary(records) {
    const validBottom = records.filter((r) => r.tBottom !== null).map((r) => r.tBottom);
    const validSurface = records.filter((r) => r.tSurface !== null).map((r) => r.tSurface);
    const validPress = records.filter((r) => r.pLocal !== null).map((r) => r.pLocal);
    const validDiff = records.filter((r) => r.tDiff !== null).map((r) => Math.abs(r.tDiff));

    const minMax = (arr) => {
      if (arr.length === 0) return { min: '--', max: '--' };
      return {
        min: Math.min(...arr).toFixed(1),
        max: Math.max(...arr).toFixed(1),
      };
    };

    const bottomMM = minMax(validBottom);
    const surfaceMM = minMax(validSurface);
    const pressMM = minMax(validPress);

    // 计算持续时间
    let duration = '--';
    if (records.length >= 2) {
      const firstTs = records[0].timestamp;
      const lastTs = records[records.length - 1].timestamp;
      const diffMin = Math.round((lastTs - firstTs) / 60);
      if (diffMin >= 60) {
        duration = `${Math.floor(diffMin / 60)}小时${diffMin % 60}分钟`;
      } else {
        duration = `${diffMin}分钟`;
      }
    }

    return {
      tBottomMin: bottomMM.min,
      tBottomMax: bottomMM.max,
      tSurfaceMin: surfaceMM.min,
      tSurfaceMax: surfaceMM.max,
      pLocalMin: pressMM.min,
      pLocalMax: pressMM.max,
      tDiffMax: validDiff.length > 0 ? Math.max(...validDiff).toFixed(1) : '--',
      duration,
    };
  },

  _formatTime(timestamp) {
    if (!timestamp) return '--';
    const d = new Date(timestamp * 1000);
    const pad = (n) => (n < 10 ? '0' + n : '' + n);
    return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  },
});
