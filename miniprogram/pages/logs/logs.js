/**
 * 作钓日志页面
 * 展示钓鱼会话摘要列表（一次出钓 = 一条日志卡片）
 */
const api = require('../../utils/api');

Page({
  data: {
    sessions: [],
    loading: true,
  },

  onLoad() {
    this.fetchSessions();
  },

  onPullDownRefresh() {
    this.fetchSessions().then(() => {
      wx.stopPullDownRefresh();
    });
  },

  onShow() {
    // 每次展示页面时静默刷新
    this.fetchSessions();
  },

  fetchSessions() {
    this.setData({ loading: true });
    return api.getSessionList(20)
      .then((res) => {
        if (res.status === 'ok' && res.data) {
          const formatted = res.data.map(s => this._formatSession(s));
          this.setData({ sessions: formatted, loading: false });
        } else {
          this.setData({ loading: false });
        }
      })
      .catch((err) => {
        console.error('[Logs] 获取日志失败:', err);
        wx.showToast({ title: '获取日志失败', icon: 'none' });
        this.setData({ loading: false });
      });
  },

  /**
   * 格式化会话数据用于显示
   */
  _formatSession(s) {
    // 日期
    const startDate = new Date(s.start_time * 1000);
    const endDate = new Date(s.end_time * 1000);
    const dateStr = `${startDate.getFullYear()}年${startDate.getMonth() + 1}月${startDate.getDate()}日`;
    const startTimeStr = `${this._pad(startDate.getHours())}:${this._pad(startDate.getMinutes())}`;
    const endTimeStr = `${this._pad(endDate.getHours())}:${this._pad(endDate.getMinutes())}`;

    // 时长
    const hours = Math.floor(s.duration_min / 60);
    const mins = s.duration_min % 60;
    const durationStr = hours > 0 ? `${hours}小时${mins}分钟` : `${mins}分钟`;

    // 水温变化
    let waterChange = null;
    if (s.t_water_start != null && s.t_water_end != null) {
      const diff = (s.t_water_end - s.t_water_start).toFixed(1);
      const arrow = diff > 0 ? '↑' : diff < 0 ? '↓' : '→';
      waterChange = {
        start: s.t_water_start.toFixed(1),
        end: s.t_water_end.toFixed(1),
        diff: Math.abs(diff).toFixed(1),
        arrow,
        color: diff > 0 ? '#e53935' : diff < 0 ? '#1565c0' : '#757575',
      };
    }

    // 气温变化
    let airChange = null;
    if (s.t_air_start != null && s.t_air_end != null) {
      const diff = (s.t_air_end - s.t_air_start).toFixed(1);
      const arrow = diff > 0 ? '↑' : diff < 0 ? '↓' : '→';
      airChange = {
        start: s.t_air_start.toFixed(1),
        end: s.t_air_end.toFixed(1),
        diff: Math.abs(diff).toFixed(1),
        arrow,
        color: diff > 0 ? '#e53935' : diff < 0 ? '#1565c0' : '#757575',
      };
    }

    // 气压变化
    let pressChange = null;
    if (s.p_start != null && s.p_end != null) {
      const diff = (s.p_end - s.p_start).toFixed(1);
      const arrow = diff > 0 ? '↑' : diff < 0 ? '↓' : '→';
      pressChange = {
        start: s.p_start.toFixed(1),
        end: s.p_end.toFixed(1),
        diff: Math.abs(diff).toFixed(1),
        arrow,
        trend: s.p_trend || '',
        color: diff > 0 ? '#2e7d32' : diff < 0 ? '#e53935' : '#757575',
      };
    }

    // 开口指数评级
    let biteLevel = 'low';
    if (s.bite_index_max >= 80) biteLevel = 'high';
    else if (s.bite_index_max >= 60) biteLevel = 'mid';

    return {
      id: s.id,
      dateStr,
      timeRange: `${startTimeStr} ~ ${endTimeStr}`,
      durationStr,
      dataPoints: s.data_points,
      locationName: s.location_name || '未知钓点',
      waterChange,
      airChange,
      pressChange,
      weatherText: s.weather_text || '--',
      windDesc: s.wind_desc || '',
      biteIndexMax: s.bite_index_max != null ? s.bite_index_max : '--',
      biteIndexAvg: s.bite_index_avg != null ? s.bite_index_avg : '--',
      biteLevel,
      recommendedFish: s.recommended_fish || '--',
    };
  },

  _pad(n) {
    return n < 10 ? '0' + n : '' + n;
  },
});
