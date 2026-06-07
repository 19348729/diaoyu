const api = require('../../utils/api')
const app = getApp()

Page({
  data: {
    fishOptions: ['鲫鱼', '鲤鱼', '罗非鱼', '鲢鳙', '草鱼', '翘嘴', '青鱼', '其他'],
    fishSpecies: '',
    catchCount: 0,
    totalWeight: '',
    note: '',
    submitting: false,

    logs: [],
    loading: true,
  },

  onShow() {
    this._fetchLogs()
  },

  onPullDownRefresh() {
    this._fetchLogs().then(() => wx.stopPullDownRefresh())
  },

  selectFish(e) { this.setData({ fishSpecies: e.currentTarget.dataset.val }) },
  onCountInput(e) {
    let v = parseInt(e.detail.value, 10)
    if (isNaN(v) || v < 0) v = 0
    this.setData({ catchCount: v })
  },
  countMinus() { this.setData({ catchCount: Math.max(0, this.data.catchCount - 1) }) },
  countPlus() { this.setData({ catchCount: this.data.catchCount + 1 }) },
  onWeightInput(e) { this.setData({ totalWeight: e.detail.value }) },
  onNoteInput(e) { this.setData({ note: e.detail.value }) },

  async submit() {
    if (this.data.submitting) return
    this.setData({ submitting: true })
    try {
      const g = app.globalData || {}
      const lastPred = g.lastPrediction || {}
      const latest = g.latestData || {}
      const spot = g.spotContext || {}
      const fc = g.fishContext || {}

      let loc = { lat: null, lng: null }
      try { loc = await app.getLocationWithCache() } catch (e) {}

      const weight = parseFloat(this.data.totalWeight)
      const payload = {
        fish_species: this.data.fishSpecies || (this.data.catchCount > 0 ? '其他' : '空军'),
        catch_count: this.data.catchCount,
        total_weight: isNaN(weight) ? null : weight,
        note: this.data.note || null,
        spot_type: spot.type || null,
        spot_density: spot.density || null,
        water_clarity: spot.clarity || null,
        lat: loc.lat, lng: loc.lng,
        target_fish: (fc.target && fc.target !== 'auto') ? fc.target : (lastPred.recommended_fish || null),
        bite_index: (lastPred.bite_index !== undefined && lastPred.bite_index !== null) ? lastPred.bite_index : null,
        // 当时环境快照（气压/天气/温度/风），回看渔获时可对照
        t_water: (latest.tWater !== undefined && latest.tWater !== null) ? latest.tWater : null,
        t_air: (latest.tAir !== undefined && latest.tAir !== null) ? latest.tAir : (lastPred.air_temp != null ? lastPred.air_temp : null),
        p_local: (latest.pLocal !== undefined && latest.pLocal !== null) ? latest.pLocal : null,
        humidity: (lastPred.humidity != null) ? lastPred.humidity : null,
        weather_text: lastPred.weather_text || null,
        wind_desc: lastPred.wind_desc || null,
      }

      const res = await api.saveCatchLog(payload)
      if (res.status === 'ok') {
        wx.showToast({ title: '已记录', icon: 'success' })
        this.setData({ fishSpecies: '', catchCount: 0, totalWeight: '', note: '' })
        this._fetchLogs()
      } else {
        wx.showToast({ title: res.message || '记录失败', icon: 'none' })
      }
    } catch (e) {
      wx.showToast({ title: e.message || '网络错误', icon: 'none' })
    } finally {
      this.setData({ submitting: false })
    }
  },

  _fetchLogs() {
    this.setData({ loading: true })
    return api.getCatchLogs(30).then(res => {
      if (res.status === 'ok' && res.data) {
        const logs = res.data.map(r => this._format(r))
        this.setData({ logs, loading: false })
      } else {
        this.setData({ loading: false })
      }
    }).catch(err => {
      console.error('[CatchLog] 获取列表失败:', err)
      this.setData({ loading: false })
    })
  },

  _format(r) {
    let dateStr = '--'
    if (r.created_at) {
      const d = new Date(r.created_at)
      const p = n => (n < 10 ? '0' + n : '' + n)
      dateStr = `${d.getMonth() + 1}月${d.getDate()}日 ${p(d.getHours())}:${p(d.getMinutes())}`
    }
    const skunked = !r.catch_count
    // 当时环境：天气 / 气温 / 水温 / 气压 / 风
    const env = []
    if (r.weather_text) env.push(r.weather_text)
    if (r.t_air !== null && r.t_air !== undefined) env.push(`气温${r.t_air}℃`)
    if (r.t_water !== null && r.t_water !== undefined) env.push(`水温${r.t_water}℃`)
    if (r.p_local !== null && r.p_local !== undefined) env.push(`气压${r.p_local}hPa`)
    if (r.wind_desc) env.push(r.wind_desc)
    return {
      id: r.id,
      dateStr,
      skunked,
      title: skunked ? '🛩️ 空军' : `🎣 ${r.fish_species || '渔获'} × ${r.catch_count}`,
      weight: r.total_weight ? `约 ${r.total_weight} 斤` : '',
      spot: [r.spot_type, r.spot_density, r.water_clarity].filter(Boolean).join(' · '),
      location: r.location_name || '',
      biteIndex: (r.bite_index !== null && r.bite_index !== undefined) ? r.bite_index : null,
      env: env.join(' · '),
      note: r.note || '',
    }
  },
})
