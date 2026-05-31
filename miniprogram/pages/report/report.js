const api = require('../../utils/api')
const ble = require('../../utils/ble')
const app = getApp()

Page({
  data: {
    catchLevel: '稳赚',
    isGenerating: false,
    posterData: null,
    equipmentUsed: null   // 本次使用装备快照（取自钓箱全量）
  },

  selectLevel(e) {
    this.setData({ catchLevel: e.currentTarget.dataset.val })
  },

  async finishSession() {
    this.setData({ isGenerating: true })
    try {
      // 1. 获取基础位置数据
      const loc = await app.getLocationWithCache()
      
      // 2. 拉取装备库快照（钓友习惯：库里的装备出钓都会带上）
      let equipmentUsed = null
      try {
        equipmentUsed = await api.getUserInventoryAll()
      } catch (invErr) {
        console.warn('[Report] 拉取装备快照失败，跳过装备记录:', invErr)
      }
      
      // 3. 从本次会话真实采集的传感器数据聚合会话摘要
      const sessionData = this._buildSessionSummary()
      sessionData.lat = loc.lat
      sessionData.lng = loc.lng
      sessionData.equipment_used = equipmentUsed

      if (sessionData.data_points < 2) {
        wx.showToast({ title: '本次未采集到足够数据', icon: 'none', duration: 2000 })
      }

      const saveRes = await api.saveSession(sessionData)
      
      // 4. 断开蓝牙连接
      const bleManager = ble.getBLEManager()
      if (bleManager.isConnected) {
        bleManager.disconnect()
        wx.showToast({ title: '设备已休眠', icon: 'none' })
      }
      
      // 5. 获取海报数据
      if (saveRes.status === 'ok') {
        const posterRes = await api.getPoster(saveRes.session_id)
        if (posterRes.status === 'ok') {
          this.setData({ 
            posterData: posterRes.poster,
            equipmentUsed: equipmentUsed
          })
        }
      }
    } catch (e) {
      wx.showToast({ title: e.message || '生成失败', icon: 'none' })
    } finally {
      this.setData({ isGenerating: false })
    }
  },
  
  getBiteIndex(level) {
    if (level === '爆护') return 90;
    if (level === '稳赚') return 70;
    if (level === '惨淡') return 50;
    return 30; // 空军
  },

  /**
   * 从本次会话真实采集的传感器数据聚合摘要
   * 数据来源：app.globalData.historyData（BLE 快闪 Dump + 实时帧累积）
   * 用 globalData.sessionStartTs（对表时记录）界定本次出钓的数据范围
   * @returns {object} 后端 /api/session/save 所需的会话摘要
   */
  _buildSessionSummary() {
    const app = getApp()
    const all = (app.globalData && app.globalData.historyData) || []
    const startTs = (app.globalData && app.globalData.sessionStartTs) || 0
    const history = startTs ? all.filter(r => r && r.timestamp >= startTs) : all.slice()

    const nowSec = Math.floor(Date.now() / 1000)
    const summary = {
      start_time: startTs || nowSec,
      end_time: nowSec,
      duration_min: 0,
      data_points: history.length,
      // 渔获等级由用户自评（爆护/稳赚/惨淡/空军），用于海报展示
      bite_index_avg: this.getBiteIndex(this.data.catchLevel),
    }

    // 目标鱼种（出钓开局所选）
    const target = app.globalData && app.globalData.fishContext && app.globalData.fishContext.target
    if (target && target !== 'auto') summary.recommended_fish = target

    if (history.length >= 2) {
      const first = history[0]
      const last = history[history.length - 1]
      summary.start_time = first.timestamp
      summary.end_time = last.timestamp
      summary.duration_min = Math.max(0, Math.round((last.timestamp - first.timestamp) / 60))

      const waters = history.filter(r => r.tWater != null).map(r => r.tWater)
      const airs = history.filter(r => r.tAir != null).map(r => r.tAir)
      const pressures = history.filter(r => r.pLocal != null).map(r => r.pLocal)

      if (waters.length > 0) {
        summary.t_water_start = waters[0]
        summary.t_water_end = waters[waters.length - 1]
        summary.t_water_min = Math.min.apply(null, waters)
        summary.t_water_max = Math.max.apply(null, waters)
      }
      if (airs.length > 0) {
        summary.t_air_start = airs[0]
        summary.t_air_end = airs[airs.length - 1]
      }
      if (pressures.length > 0) {
        summary.p_start = pressures[0]
        summary.p_end = pressures[pressures.length - 1]
        summary.p_trend = this._calcPressureTrend(pressures)
      }
    }

    return summary
  },

  /**
   * 计算气压趋势描述（与首页算法一致）
   * @param {number[]} pressures - 气压序列
   * @returns {string}
   */
  _calcPressureTrend(pressures) {
    if (pressures.length < 2) return '数据不足'
    const diff = pressures[pressures.length - 1] - pressures[0]
    const threshold = 0.5 // hPa
    if (pressures.length >= 4) {
      const midIdx = Math.floor(pressures.length / 2)
      const firstHalf = pressures[midIdx] - pressures[0]
      const secondHalf = pressures[pressures.length - 1] - pressures[midIdx]
      if (firstHalf > threshold && secondHalf < -threshold) return '先升后降'
      if (firstHalf < -threshold && secondHalf > threshold) return '先降后升'
    }
    if (diff > threshold) return '持续上升'
    if (diff < -threshold) return '持续下降'
    return '基本平稳'
  },

  sharePoster() {
    wx.showToast({ title: '已保存到相册，快去分享吧', icon: 'none' })
  }
})
