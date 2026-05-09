import * as echarts from '../../components/ec-canvas/echarts';

const app = getApp();

Page({
  data: {
    ec: {
      lazyLoad: true
    },
    recordCount: 0,
    timeRange: 60, // 默认近1小时（60分钟）
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
    }
  },

  onReady() {
    this.ecComponentTemp = this.selectComponent('#temp-chart-dom');
    this.ecComponentPress = this.selectComponent('#press-chart-dom');
    this.initChart();
  },

  onTimeRangeChange(e) {
    const range = parseInt(e.currentTarget.dataset.range);
    this.setData({ timeRange: range });
    this._refreshData();
  },

  onShow() {
    this._refreshData();
  },

  onPullDownRefresh() {
    this._refreshData();
    wx.stopPullDownRefresh();
  },

  initChart() {
    if (this.ecComponentTemp) {
      this.ecComponentTemp.init((canvas, width, height, dpr) => {
        const chart = echarts.init(canvas, null, { width, height, devicePixelRatio: dpr });
        canvas.setChart(chart);
        this.tempChart = chart;
        this._updateChart();
        return chart;
      });
    }
    if (this.ecComponentPress) {
      this.ecComponentPress.init((canvas, width, height, dpr) => {
        const chart = echarts.init(canvas, null, { width, height, devicePixelRatio: dpr });
        canvas.setChart(chart);
        this.pressChart = chart;
        this._updateChart();
        return chart;
      });
    }
  },

  _refreshData() {
    const history = app.globalData.historyData || [];
    const count = history.length;
    
    this.setData({ recordCount: count });

    if (count > 0) {
      const summary = this._calcSummary(history);
      this.setData({ summary });
    } else {
      this.setData({
        summary: {
          tBottomMin: '--', tBottomMax: '--',
          tSurfaceMin: '--', tSurfaceMax: '--',
          pLocalMin: '--', pLocalMax: '--',
          tDiffMax: '--', duration: '--',
        }
      });
    }

    if (this.tempChart && this.pressChart) {
      this._updateChart();
    }
  },

  _updateChart() {
    if (!this.tempChart || !this.pressChart) return;
    const history = app.globalData.historyData || [];
    
    if (history.length === 0) {
      this.tempChart.clear();
      this.pressChart.clear();
      return;
    }

    // 根据 timeRange 过滤数据
    let displayRecords = history;
    if (this.data.timeRange > 0) {
      // 找到最后一条数据的时间作为当前参考时间，因为设备可能离线，以最新数据时间往前推更合理
      const latestTs = history[history.length - 1].timestamp;
      const cutoff = latestTs - this.data.timeRange * 60;
      displayRecords = history.filter(r => r.timestamp >= cutoff);
    }
    
    const times = [];
    const tBottoms = [];
    const tMids = [];
    const tSurfaces = [];
    const pLocals = [];

    displayRecords.forEach(r => {
      times.push(this._formatTime(r.timestamp));
      tBottoms.push(r.tBottom !== null ? parseFloat(r.tBottom.toFixed(1)) : null);
      tMids.push(r.tMid !== null ? parseFloat(r.tMid.toFixed(1)) : null);
      tSurfaces.push(r.tSurface !== null ? parseFloat(r.tSurface.toFixed(1)) : null);
      pLocals.push(r.pLocal !== null ? parseFloat(r.pLocal.toFixed(1)) : null);
    });

    const optionTemp = {
      color: ['#1890FF', '#2FC25B', '#FACC14'],
      legend: {
        data: ['水底', '1米', '水面'],
        top: 0,
        z: 100
      },
      grid: { left: 15, right: 15, bottom: 10, top: 30, containLabel: true },
      tooltip: { show: true, trigger: 'axis' },
      xAxis: { type: 'category', boundaryGap: false, data: times },
      yAxis: {
        type: 'value',
        name: '温度(℃)',
        position: 'left',
        scale: true,
        splitLine: { lineStyle: { type: 'dashed', color: '#eeeeee' } },
        axisLabel: { formatter: '{value}' }
      },
      series: [
        { name: '水底', type: 'line', smooth: true, sampling: 'lttb', data: tBottoms, symbol: 'none' },
        { name: '1米', type: 'line', smooth: true, sampling: 'lttb', data: tMids, symbol: 'none' },
        { name: '水面', type: 'line', smooth: true, sampling: 'lttb', data: tSurfaces, symbol: 'none' }
      ]
    };

    const optionPress = {
      color: ['#F04864'],
      legend: {
        data: ['气压'],
        top: 0,
        z: 100
      },
      grid: { left: 15, right: 15, bottom: 10, top: 30, containLabel: true },
      tooltip: { show: true, trigger: 'axis' },
      xAxis: { type: 'category', boundaryGap: false, data: times },
      yAxis: {
        type: 'value',
        name: '气压(hPa)',
        position: 'left',
        scale: true,
        splitLine: { lineStyle: { type: 'dashed', color: '#eeeeee' } },
        axisLabel: { formatter: '{value}' }
      },
      series: [
        { name: '气压', type: 'line', smooth: true, sampling: 'lttb', data: pLocals, symbol: 'none' }
      ]
    };

    this.tempChart.setOption(optionTemp);
    this.pressChart.setOption(optionPress);
  },

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

    let duration = '--';
    if (records.length >= 2) {
      const validRecords = records.filter(r => r.timestamp > 946656000);
      if (validRecords.length >= 2) {
        const firstTs = validRecords[0].timestamp;
        const lastTs = validRecords[validRecords.length - 1].timestamp;
        const diffMin = Math.round((lastTs - firstTs) / 60);
        if (diffMin >= 60) {
          duration = `${Math.floor(diffMin / 60)}小时${diffMin % 60}分钟`;
        } else {
          duration = `${diffMin}分钟`;
        }
      } else if (records.length > 0) {
        duration = `已采集${records.length}组数据`;
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
  }
});
