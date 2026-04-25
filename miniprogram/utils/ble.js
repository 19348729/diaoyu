/**
 * BLE 蓝牙连接管理模块
 * 负责扫描、连接 FishProbe 设备、对表、数据收发、断连重连
 */

const protocol = require('./protocol');

// ── 与 ESP32 config.py 保持一致的 BLE 参数 ──
const BLE_DEVICE_NAME = 'FishProbe';
const BLE_SERVICE_UUID = '12345678-1234-5678-1234-56789ABCDEF0';
const BLE_TX_CHAR_UUID = '12345678-1234-5678-1234-56789ABCDEF1'; // ESP32 -> 小程序 (Notify)
const BLE_RX_CHAR_UUID = '12345678-1234-5678-1234-56789ABCDEF2'; // 小程序 -> ESP32 (Write)

// 扫描超时（毫秒）
const SCAN_TIMEOUT = 15000;

class BLEManager {
  constructor() {
    this._deviceId = null;
    this._serviceId = null;
    this._txCharId = null;  // 通知特征（ESP32 -> 小程序）
    this._rxCharId = null;  // 写入特征（小程序 -> ESP32）
    this._connected = false;
    this._timeSynced = false;
    this._scanning = false;

    // 回调函数
    this._onDataCallback = null;       // 收到数据回调
    this._onConnectCallback = null;    // 连接状态变化回调
    this._onTimeSyncCallback = null;   // 对表完成回调

    // 监听蓝牙断开事件
    wx.onBLEConnectionStateChange((res) => {
      if (!res.connected) {
        console.log('[BLE] 连接已断开:', res.deviceId);
        this._connected = false;
        this._timeSynced = false;
        if (this._onConnectCallback) {
          this._onConnectCallback(false);
        }
      }
    });

    // 监听特征值变化（接收 ESP32 数据）
    wx.onBLECharacteristicValueChange((res) => {
      this._handleNotification(res.value);
    });
  }

  /** 是否已连接 */
  get isConnected() { return this._connected; }

  /** 是否已对表 */
  get isTimeSynced() { return this._timeSynced; }

  /** 当前设备 ID */
  get deviceId() { return this._deviceId; }

  /**
   * 注册回调
   */
  onData(callback) { this._onDataCallback = callback; }
  onConnect(callback) { this._onConnectCallback = callback; }
  onTimeSync(callback) { this._onTimeSyncCallback = callback; }

  /**
   * 扫描并连接 FishProbe 设备
   * 完整流程：扫描 -> 连接 -> 获取服务 -> 获取特征 -> 订阅通知 -> 对表
   * @returns {Promise<boolean>}
   */
  async connectDevice() {
    try {
      // 1. 初始化蓝牙适配器
      await this._openAdapter();
      console.log('[BLE] 蓝牙适配器已打开');

      // 2. 扫描设备
      wx.showLoading({ title: '搜索设备中...' });
      const device = await this._scanForDevice();
      if (!device) {
        wx.hideLoading();
        wx.showToast({ title: '未找到 FishProbe 设备', icon: 'none' });
        return false;
      }
      this._deviceId = device.deviceId;
      console.log('[BLE] 找到设备:', device.name, device.deviceId);

      // 3. 建立连接
      wx.showLoading({ title: '连接中...' });
      await this._createConnection(this._deviceId);
      this._connected = true;
      console.log('[BLE] 连接成功');

      // 4. 获取服务和特征
      await this._discoverServices();
      console.log('[BLE] 服务发现完成');

      // 5. 订阅 TX 特征通知
      await this._enableNotify();
      console.log('[BLE] 通知订阅成功');

      // 6. 发送对表指令
      await this._sendTimeSync();
      this._timeSynced = true;
      console.log('[BLE] 对表完成');

      wx.hideLoading();
      wx.showToast({ title: '连接成功', icon: 'success' });

      if (this._onConnectCallback) {
        this._onConnectCallback(true);
      }
      if (this._onTimeSyncCallback) {
        this._onTimeSyncCallback();
      }

      return true;
    } catch (err) {
      wx.hideLoading();
      console.error('[BLE] 连接流程失败:', err);
      wx.showToast({
        title: err.message || '连接失败',
        icon: 'none',
        duration: 3000,
      });
      return false;
    }
  }

  /**
   * 断开连接
   */
  async disconnect() {
    if (this._deviceId) {
      try {
        await wx.closeBLEConnection({ deviceId: this._deviceId });
      } catch (e) {
        // 忽略断开错误
      }
    }
    this._connected = false;
    this._timeSynced = false;
    this._deviceId = null;
    console.log('[BLE] 已主动断开');
    if (this._onConnectCallback) {
      this._onConnectCallback(false);
    }
  }

  /**
   * 发送同步确认（收到历史数据后调用）
   * @param {number} count - 确认条数
   */
  async sendSyncAck(count) {
    const buffer = protocol.encodeSyncAck(count);
    await this._writeToDevice(buffer);
    console.log('[BLE] 发送同步确认:', count, '条');
  }

  /**
   * 发送状态查询
   */
  async sendStatusQuery() {
    const buffer = protocol.encodeStatusQuery();
    await this._writeToDevice(buffer);
    console.log('[BLE] 发送状态查询');
  }

  // ============================================
  //  内部方法
  // ============================================

  _openAdapter() {
    return new Promise((resolve, reject) => {
      wx.openBluetoothAdapter({
        mode: 'central',
        success: resolve,
        fail: (err) => reject(new Error(`蓝牙未开启: ${err.errMsg}`)),
      });
    });
  }

  /**
   * 扫描 FishProbe 设备
   * @returns {Promise<object|null>}
   */
  _scanForDevice() {
    return new Promise((resolve, reject) => {
      let found = null;
      this._scanning = true;

      const timer = setTimeout(() => {
        if (this._scanning) {
          wx.stopBluetoothDevicesDiscovery();
          this._scanning = false;
          resolve(found);
        }
      }, SCAN_TIMEOUT);

      wx.onBluetoothDeviceFound((res) => {
        for (const device of res.devices) {
          if (device.localName === BLE_DEVICE_NAME || device.name === BLE_DEVICE_NAME) {
            found = device;
            clearTimeout(timer);
            wx.stopBluetoothDevicesDiscovery();
            this._scanning = false;
            resolve(found);
            return;
          }
        }
      });

      wx.startBluetoothDevicesDiscovery({
        allowDuplicatesKey: false,
        powerLevel: 'high',
        fail: (err) => {
          clearTimeout(timer);
          this._scanning = false;
          reject(new Error(`扫描失败: ${err.errMsg}`));
        },
      });
    });
  }

  _createConnection(deviceId) {
    return new Promise((resolve, reject) => {
      wx.createBLEConnection({
        deviceId,
        timeout: 10000,
        success: resolve,
        fail: (err) => reject(new Error(`连接失败: ${err.errMsg}`)),
      });
    });
  }

  /**
   * 发现服务和特征
   */
  async _discoverServices() {
    // 等待稳定（部分安卓机型需要）
    await this._delay(500);

    // 获取服务列表
    const servicesRes = await new Promise((resolve, reject) => {
      wx.getBLEDeviceServices({
        deviceId: this._deviceId,
        success: resolve,
        fail: (err) => reject(new Error(`获取服务失败: ${err.errMsg}`)),
      });
    });

    // 查找目标服务
    const targetService = servicesRes.services.find(
      (s) => s.uuid.toUpperCase() === BLE_SERVICE_UUID.toUpperCase()
    );
    if (!targetService) {
      throw new Error('未找到 FishProbe 服务');
    }
    this._serviceId = targetService.uuid;

    // 获取特征列表
    const charsRes = await new Promise((resolve, reject) => {
      wx.getBLEDeviceCharacteristics({
        deviceId: this._deviceId,
        serviceId: this._serviceId,
        success: resolve,
        fail: (err) => reject(new Error(`获取特征失败: ${err.errMsg}`)),
      });
    });

    // 匹配 TX 和 RX 特征
    for (const char of charsRes.characteristics) {
      const uuid = char.uuid.toUpperCase();
      if (uuid === BLE_TX_CHAR_UUID.toUpperCase()) {
        this._txCharId = char.uuid;
      } else if (uuid === BLE_RX_CHAR_UUID.toUpperCase()) {
        this._rxCharId = char.uuid;
      }
    }

    if (!this._txCharId || !this._rxCharId) {
      throw new Error('未找到 TX/RX 特征');
    }
  }

  /**
   * 订阅 TX 特征的通知
   */
  _enableNotify() {
    return new Promise((resolve, reject) => {
      wx.notifyBLECharacteristicValueChange({
        deviceId: this._deviceId,
        serviceId: this._serviceId,
        characteristicId: this._txCharId,
        state: true,
        success: resolve,
        fail: (err) => reject(new Error(`订阅通知失败: ${err.errMsg}`)),
      });
    });
  }

  /**
   * 发送对表指令
   */
  async _sendTimeSync() {
    const now = Math.floor(Date.now() / 1000); // 当前 Unix 时间戳（秒）
    const buffer = protocol.encodeTimeSync(now);
    await this._writeToDevice(buffer);
    console.log('[BLE] 对表指令已发送, timestamp:', now);
  }

  /**
   * 写入数据到 RX 特征
   * @param {ArrayBuffer} buffer
   */
  _writeToDevice(buffer) {
    return new Promise((resolve, reject) => {
      wx.writeBLECharacteristicValue({
        deviceId: this._deviceId,
        serviceId: this._serviceId,
        characteristicId: this._rxCharId,
        value: buffer,
        success: resolve,
        fail: (err) => reject(new Error(`写入失败: ${err.errMsg}`)),
      });
    });
  }

  /**
   * 处理 ESP32 通过 Notify 推送的数据
   * @param {ArrayBuffer} buffer
   */
  _handleNotification(buffer) {
    const data = protocol.decodeIncoming(buffer);

    if (data.error) {
      console.warn('[BLE] 数据解码错误:', data.error);
      return;
    }

    switch (data.cmd) {
      case protocol.CMD.REALTIME_DATA:
        console.log('[BLE] 实时数据:', data);
        // 更新全局数据
        const app = getApp();
        app.globalData.latestData = {
          timestamp: data.timestamp,
          tBottom: data.tBottom,
          tMid: data.tMid,
          tSurface: data.tSurface,
          tDiff: data.tDiff,
          pLocal: data.pLocal,
        };
        app.addHistoryRecord(data);
        break;

      case protocol.CMD.HISTORY_DATA:
        console.log('[BLE] 历史数据:', data.count, '条');
        // 存储历史数据
        const app2 = getApp();
        app2.addHistoryBatch(data.records);
        // 自动发送同步确认
        this.sendSyncAck(data.count).catch((e) => {
          console.error('[BLE] 同步确认发送失败:', e);
        });
        break;

      case protocol.CMD.STATUS_REPLY:
        console.log('[BLE] 设备状态:', data);
        break;
    }

    // 触发数据回调
    if (this._onDataCallback) {
      this._onDataCallback(data);
    }
  }

  _delay(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }
}

// 单例模式
let _instance = null;

function getBLEManager() {
  if (!_instance) {
    _instance = new BLEManager();
  }
  return _instance;
}

module.exports = {
  getBLEManager,
};
