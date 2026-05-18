/**
 * BLE 通信协议编解码模块
 * 与 ESP32 esp32/ble/protocol.py 完全对齐
 *
 * 所有数值使用小端序（Little-Endian）
 *
 * 硬件版本: v2（水温 + 气温 + 气压，共 3 值）
 */

// ── 指令码（与 ESP32 config.py 一致）──
const CMD = {
  TIME_SYNC: 0x01,      // 对表指令    (小程序 -> ESP32)
  REALTIME_DATA: 0x02,  // 实时数据帧  (ESP32 -> 小程序)
  HISTORY_DATA: 0x03,   // 历史数据帧  (ESP32 -> 小程序)
  SYNC_ACK: 0x04,       // 同步确认    (小程序 -> ESP32)
  STATUS_QUERY: 0x05,   // 状态查询    (小程序 -> ESP32)
  STATUS_REPLY: 0x06,   // 状态回复    (ESP32 -> 小程序)
  PULL_HISTORY: 0x07,   // 手动拉取一批历史 (小程序 -> ESP32，无载荷)
  BULK_DUMP: 0x08,      // 全量快闪拉取 (小程序 -> ESP32)
  DUMP_COMPLETE: 0x09,  // 全量快闪结束标记 (ESP32 -> 小程序)
  ENTER_REALTIME: 0x0A, // 切换实时 Notify 模式 (小程序 -> ESP32)
};

// ── None 值占位符（与 ESP32 protocol.py 一致）──
const TEMP_NONE = -999.0;
const PRESS_NONE = 0.0;

/**
 * 将占位符还原为 null
 */
function toNullable(value, placeholder) {
  return Math.abs(value - placeholder) < 0.01 ? null : value;
}

/**
 * 格式化温度值（保留2位小数）
 */
function fmtTemp(value) {
  return value !== null ? parseFloat(value.toFixed(2)) : null;
}

// ============================================
//  编码（小程序 -> ESP32）
// ============================================

/**
 * 编码对表指令
 * 帧结构: CMD(1) + unix_timestamp(4)
 * @param {number} unixTimestamp - Unix 时间戳（秒）
 * @returns {ArrayBuffer}
 */
function encodeTimeSync(unixTimestamp) {
  const buffer = new ArrayBuffer(5);
  const view = new DataView(buffer);
  view.setUint8(0, CMD.TIME_SYNC);
  view.setUint32(1, unixTimestamp, true); // little-endian
  return buffer;
}

/**
 * 编码同步确认
 * 帧结构: CMD(1) + confirmed_count(2)
 * @param {number} count - 已确认条数
 * @returns {ArrayBuffer}
 */
function encodeSyncAck(count) {
  const buffer = new ArrayBuffer(3);
  const view = new DataView(buffer);
  view.setUint8(0, CMD.SYNC_ACK);
  view.setUint16(1, count, true);
  return buffer;
}

/**
 * 编码状态查询
 * 帧结构: CMD(1)
 * @returns {ArrayBuffer}
 */
function encodeStatusQuery() {
  const buffer = new ArrayBuffer(1);
  const view = new DataView(buffer);
  view.setUint8(0, CMD.STATUS_QUERY);
  return buffer;
}

/**
 * 编码手动拉取历史指令
 * 帧结构: CMD(1)
 * @returns {ArrayBuffer}
 */
function encodePullHistory() {
  const buffer = new ArrayBuffer(1);
  const view = new DataView(buffer);
  view.setUint8(0, CMD.PULL_HISTORY);
  return buffer;
}

/**
 * 编码全量快闪拉取指令
 * 帧结构: CMD(1)
 * @returns {ArrayBuffer}
 */
function encodeBulkDump() {
  const buffer = new ArrayBuffer(1);
  const view = new DataView(buffer);
  view.setUint8(0, CMD.BULK_DUMP);
  return buffer;
}

/**
 * 编码切换实时模式指令
 * 帧结构: CMD(1)
 * @returns {ArrayBuffer}
 */
function encodeEnterRealtime() {
  const buffer = new ArrayBuffer(1);
  const view = new DataView(buffer);
  view.setUint8(0, CMD.ENTER_REALTIME);
  return buffer;
}

// ============================================
//  解码（ESP32 -> 小程序）
// ============================================

/**
 * 解码从 ESP32 收到的数据帧
 * @param {ArrayBuffer} buffer - 原始字节数据
 * @returns {object} 解码后的数据对象
 */
function decodeIncoming(buffer) {
  if (!buffer || buffer.byteLength < 1) {
    return { cmd: null, error: '空数据' };
  }

  const view = new DataView(buffer);
  const cmd = view.getUint8(0);

  try {
    switch (cmd) {
      case CMD.REALTIME_DATA:
        return decodeRealtimeData(view);

      case CMD.HISTORY_DATA:
        return decodeHistoryBatch(view);

      case CMD.STATUS_REPLY:
        return decodeStatusReply(view);
        
      case CMD.DUMP_COMPLETE:
        return { cmd: CMD.DUMP_COMPLETE };

      default:
        return { cmd, error: `未知指令码: 0x${cmd.toString(16)}` };
    }
  } catch (e) {
    return { cmd, error: `解码异常: ${e.message}` };
  }
}

/**
 * 解码实时数据帧 (v2)
 * 帧结构: CMD(1) + timestamp(4) + t_water(4) + t_air(4) + p_local(4) = 17字节
 */
function decodeRealtimeData(view) {
  if (view.byteLength < 17) {
    return { cmd: CMD.REALTIME_DATA, error: '实时数据帧长度不足' };
  }

  const timestamp = view.getUint32(1, true);
  const tWater = view.getFloat32(5, true);
  const tAir = view.getFloat32(9, true);
  const pLocal = view.getFloat32(13, true);

  const tw = fmtTemp(toNullable(tWater, TEMP_NONE));
  const ta = fmtTemp(toNullable(tAir, TEMP_NONE));
  const pl = toNullable(pLocal, PRESS_NONE);

  return {
    cmd: CMD.REALTIME_DATA,
    timestamp,
    tWater: tw,
    tAir: ta,
    pLocal: pl !== null ? parseFloat(pl.toFixed(2)) : null,
  };
}

/**
 * 解码历史数据批量帧 (v2)
 * 帧结构: CMD(1) + count(2) + N * [timestamp(4) + t_water(4) + t_air(4) + p_local(4)]
 * 每条记录 16 字节
 */
function decodeHistoryBatch(view) {
  if (view.byteLength < 3) {
    return { cmd: CMD.HISTORY_DATA, error: '历史数据帧头长度不足' };
  }

  const count = view.getUint16(1, true);
  const recordSize = 16; // 4+4+4+4
  const expectedLen = 3 + count * recordSize;

  if (view.byteLength < expectedLen) {
    return {
      cmd: CMD.HISTORY_DATA,
      error: `历史数据帧长度不足: 需要${expectedLen}, 实际${view.byteLength}`,
    };
  }

  const records = [];
  for (let i = 0; i < count; i++) {
    const offset = 3 + i * recordSize;
    const timestamp = view.getUint32(offset, true);
    const tWater = view.getFloat32(offset + 4, true);
    const tAir = view.getFloat32(offset + 8, true);
    const pLocal = view.getFloat32(offset + 12, true);

    const tw = fmtTemp(toNullable(tWater, TEMP_NONE));
    const ta = fmtTemp(toNullable(tAir, TEMP_NONE));
    const pl = toNullable(pLocal, PRESS_NONE);

    records.push({
      timestamp,
      tWater: tw,
      tAir: ta,
      pLocal: pl !== null ? parseFloat(pl.toFixed(2)) : null,
    });
  }

  return {
    cmd: CMD.HISTORY_DATA,
    count,
    records,
  };
}

/**
 * 解码状态回复帧
 * 帧结构: CMD(1) + capacity(2) + count(2) + unsent(2) + total_written(4) = 11字节
 */
function decodeStatusReply(view) {
  if (view.byteLength < 11) {
    return { cmd: CMD.STATUS_REPLY, error: '状态回复帧长度不足' };
  }

  return {
    cmd: CMD.STATUS_REPLY,
    capacity: view.getUint16(1, true),
    count: view.getUint16(3, true),
    unsent: view.getUint16(5, true),
    totalWritten: view.getUint32(7, true),
  };
}

module.exports = {
  CMD,
  encodeTimeSync,
  encodeSyncAck,
  encodeStatusQuery,
  encodePullHistory,
  encodeBulkDump,
  encodeEnterRealtime,
  decodeIncoming,
};
