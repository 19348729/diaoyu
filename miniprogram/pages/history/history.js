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
      tWaterMin: '--',
      tWaterMax: '--',
      tAirMin: '--',
      tAirMax: '--',
      pLocalMin: '--',
      pLocalMax: '--',
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
    const totalCount = history.length;

    // 按当前 timeRange 过滤，使“数据概览”与图表保持一致
    const filtered = this._filterByTimeRange(history);
    const count = filtered.length;

    this.setData({ recordCount: count });

    if (count > 0) {
      const summary = this._calcSummary(filtered);
      this.setData({ summary });
    } else {
      this.setData({
        summary: {
          tWaterMin: '--', tWaterMax: '--',
          tAirMin: '--', tAirMax: '--',
          pLocalMin: '--', pLocalMax: '--',
          duration: '--',
        }
      });
    }

    if (this.tempChart && this.pressChart) {
      this._updateChart();
    }
  },

  /**
   * 按当前 timeRange 过滤记录。
   * timeRange == 0 表示“全部”，不过滤。
   * 以最新一条记录的时间为参考（设备可能离线，不能用当前系统时间）。
   */
  _filterByTimeRange(records) {
    if (!records || records.length === 0) return [];
    if (this.data.timeRange <= 0) return records;
    const latestTs = records[records.length - 1].timestamp;
    const cutoff = latestTs - this.data.timeRange * 60;
    return records.filter(r => r.timestamp >= cutoff);
  },

  _updateChart() {
    if (!this.tempChart || !this.pressChart) return;
    const history = app.globalData.historyData || [];
    
    if (history.length === 0) {
      this.tempChart.clear();
      this.pressChart.clear();
      return;
    }

    // 根据 timeRange 过滤数据（与概览复用同一过滤函数）
    const displayRecords = this._filterByTimeRange(history);
    
    const times = [];
    const tWaters = [];
    const tAirs = [];
    const pLocals = [];

    displayRecords.forEach(r => {
      times.push(this._formatTime(r.timestamp));
      tWaters.push(r.tWater !== null && r.tWater !== undefined ? parseFloat(r.tWater.toFixed(1)) : null);
      tAirs.push(r.tAir !== null && r.tAir !== undefined ? parseFloat(r.tAir.toFixed(1)) : null);
      pLocals.push(r.pLocal !== null && r.pLocal !== undefined ? parseFloat(r.pLocal.toFixed(1)) : null);
    });

    const optionTemp = {
      color: ['#1890FF', '#2FC25B'],
      legend: {
        data: ['水温', '气温'],
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
        { name: '水温', type: 'line', smooth: true, sampling: 'lttb', data: tWaters, symbol: 'none' },
        { name: '气温', type: 'line', smooth: true, sampling: 'lttb', data: tAirs, symbol: 'none' }
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
    const validWater = records.filter((r) => r.tWater !== null && r.tWater !== undefined).map((r) => r.tWater);
    const validAir = records.filter((r) => r.tAir !== null && r.tAir !== undefined).map((r) => r.tAir);
    const validPress = records.filter((r) => r.pLocal !== null && r.pLocal !== undefined).map((r) => r.pLocal);

    const minMax = (arr) => {
      if (arr.length === 0) return { min: '--', max: '--' };
      return {
        min: Math.min(...arr).toFixed(1),
        max: Math.max(...arr).toFixed(1),
      };
    };

    const waterMM = minMax(validWater);
    const airMM = minMax(validAir);
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
      tWaterMin: waterMM.min,
      tWaterMax: waterMM.max,
      tAirMin: airMM.min,
      tAirMax: airMM.max,
      pLocalMin: pressMM.min,
      pLocalMax: pressMM.max,
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
