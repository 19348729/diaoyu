# 蓝牙历史数据「手动拉取」补丁说明

> 适用场景：在另一台已拉取最新仓库代码的电脑上，手工重现本次改动。
> 本次改动仅涉及 **ESP32 固件** 与 **微信小程序前端**，**不涉及服务器后端**。

---

## 一、问题背景

- ESP32 侧：BLE 未连接时数据持续写入 `RingBuffer`。以往小程序连接并对表后，主循环会**自动补传历史数据**：每 5 秒（`SAMPLE_INTERVAL_SEC`）一轮，每轮仅发 1 批（`BLE_BATCH_SIZE = 10` 条）。
- 现场现象：堆积一小时 = 720 条，净补传速率 ≈ 1.8 条/秒，要 ~7 分钟才能追完；补传中间一旦再次断开就永远追不上，而且用户无感知。

## 二、修复方案（手动拉取模式）

- 主循环改为**只发实时数据**，不再自动补传。
- 新增指令 `CMD_PULL_HISTORY = 0x07`（小程序 → ESP32，无载荷）：小程序每点一次"拉取一批"，ESP32 回发一批历史（最多 `BLE_BATCH_SIZE = 10` 条），小程序收到后自动回 `CMD_SYNC_ACK` 并自动查询 `CMD_STATUS_QUERY` 刷新 unsent 显示。
- `BLE_BATCH_SIZE` 不变，传输大小不变。
- 小程序 `实时监测` 页「设备缓存」这一行改为两个独立链接：**刷新 | 拉取一批**。

## 三、协议变更汇总

| 指令 | 方向 | 载荷 | 说明 |
|------|------|------|------|
| `CMD_PULL_HISTORY = 0x07` | 小程序 → ESP32 | 无 | 请求 ESP32 回发一批历史；ESP32 校验"已对表 + 有待补"后调用 `send_history_batch()` |

其余指令（0x01~0x06）保持不变。

---

## 四、ESP32 侧改动

### 4.1 `esp32/config.py`

在 `CMD_STATUS_REPLY = 0x06` 行之后新增一行：

```python
CMD_STATUS_QUERY = 0x05     # 状态查询（小程序 -> ESP32）
CMD_STATUS_REPLY = 0x06     # 状态回复（ESP32 -> 小程序）
CMD_PULL_HISTORY = 0x07     # 手动拉取一批历史（小程序 -> ESP32，无载荷）
```

### 4.2 `esp32/ble/protocol.py`

**① 顶部 import 追加 `CMD_PULL_HISTORY`：**

```python
from config import (
    CMD_TIME_SYNC, CMD_REALTIME_DATA, CMD_HISTORY_DATA,
    CMD_SYNC_ACK, CMD_STATUS_QUERY, CMD_STATUS_REPLY, CMD_PULL_HISTORY,
)
```

**② `decode_incoming` 在 `CMD_STATUS_QUERY` 分支之后、`else` 分支之前插入：**

```python
        elif cmd == CMD_STATUS_QUERY:
            # 状态查询: 仅 CMD(1)，无载荷
            return {"cmd": cmd}

        elif cmd == CMD_PULL_HISTORY:
            # 手动拉取一批历史: 仅 CMD(1)，无载荷
            return {"cmd": cmd}

        else:
            return {"cmd": cmd, "error": "未知指令码: 0x{:02X}".format(cmd)}
```

### 4.3 `esp32/ble/service.py`

**① 顶部 import 追加 `CMD_PULL_HISTORY`：**

```python
from config import (
    BLE_DEVICE_NAME, BLE_SERVICE_UUID, BLE_TX_CHAR_UUID, BLE_RX_CHAR_UUID,
    BLE_BATCH_SIZE, CMD_TIME_SYNC, CMD_SYNC_ACK, CMD_STATUS_QUERY,
    CMD_PULL_HISTORY,
)
```

**② `_handle_rx_data` 方法在处理 `CMD_STATUS_QUERY` 分支之后追加：**

```python
        elif cmd == CMD_STATUS_QUERY:
            # 状态查询 -> 回复缓冲区状态
            status = self._ring_buffer.get_status()
            reply = encode_status_reply(
                status["capacity"], status["count"],
                status["unsent"], status["total_written"],
            )
            self._send(reply)

        elif cmd == CMD_PULL_HISTORY:
            # 手动拉取一批历史数据
            if not self._time_synced:
                print("[BLE] 收到拉取指令但未对表，忽略")
                return
            if self._ring_buffer.unsent_count == 0:
                print("[BLE] 收到拉取指令但无待补数据")
                return
            sent = self.send_history_batch()
            if sent:
                print("[BLE] 手动拉取：已发送一批历史数据")
```

### 4.4 `esp32/main.py`

**① 文件顶部注释更新（可选）：**

```python
"""
ESP32 钓鱼传感器主程序 (Main Entry)
=====================================
初始化所有模块，运行主采集-通信循环。

主循环逻辑（每 5 秒一轮）：
  1. 读取三层水温
  2. 读取气压
  3. 生成时间戳
  4. 写入环形缓冲区
  5. 根据 BLE 连接状态决定发送策略：
     - 已连接且已对表 → 发送实时数据
     - 已连接但未对表 → 等待对表指令
     - 未连接 → 数据留在缓冲区
  6. 历史数据采用手动拉取模式：由小程序下发 CMD_PULL_HISTORY
     主动拉取，每次回发一批（最多 BLE_BATCH_SIZE 条）。
"""
```

**② 主循环中「2.5 BLE 数据发送策略」整段替换为：**

```python
        # ── 2.5 BLE 数据发送策略 ──
        # 注意：历史数据补传改为"手动拉取模式"，由小程序主动下发
        # CMD_PULL_HISTORY 指令触发，主循环只负责发送实时数据。
        if ble_service.is_connected and ble_service.is_time_synced:
            # 清除重连标志（不再自动补传，仅保留状态）
            if ble_service.just_reconnected:
                unsent = ring_buffer.unsent_count
                if unsent > 0:
                    print("[系统] 重连后待补 {} 条，等待小程序手动拉取".format(unsent))
                ble_service.clear_reconnect_flag()

            # 仅发送实时数据
            ble_service.send_realtime(
                timestamp,
                temps["t_bottom"],
                temps["t_mid"],
                temps["t_surface"],
                press["p_local"],
            )
```

即**删除原有的** `if ble_service.has_pending_history(): ble_service.send_history_batch() else: ...` 分支，改为**始终只发送实时数据**。

---

## 五、小程序侧改动

### 5.1 `miniprogram/utils/protocol.js`

**① `CMD` 常量对象新增一项：**

```js
const CMD = {
  TIME_SYNC: 0x01,
  REALTIME_DATA: 0x02,
  HISTORY_DATA: 0x03,
  SYNC_ACK: 0x04,
  STATUS_QUERY: 0x05,
  STATUS_REPLY: 0x06,
  PULL_HISTORY: 0x07,   // 手动拉取一批历史 (小程序 -> ESP32，无载荷)
};
```

**② 在 `encodeStatusQuery` 函数之后新增 `encodePullHistory`：**

```js
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
```

**③ `module.exports` 追加导出：**

```js
module.exports = {
  CMD,
  encodeTimeSync,
  encodeSyncAck,
  encodeStatusQuery,
  encodePullHistory,
  decodeIncoming,
};
```

### 5.2 `miniprogram/utils/ble.js`

**① 在 `sendStatusQuery` 方法之后新增 `sendPullHistory`：**

```js
  /**
   * 发送手动拉取历史指令（每次回发一批）
   */
  async sendPullHistory() {
    const buffer = protocol.encodePullHistory();
    await this._writeToDevice(buffer);
    console.log('[BLE] 发送手动拉取历史指令');
  }
```

**② `_handleNotification` 中 `HISTORY_DATA` 分支调整：收到历史后 ACK 成功再自动发一次状态查询，刷新 unsent：**

```js
      case protocol.CMD.HISTORY_DATA:
        console.log('[BLE] 历史数据:', data.count, '条');
        // 存储历史数据
        const app2 = getApp();
        app2.addHistoryBatch(data.records);
        // 自动发送同步确认，随后刷新一次设备状态
        this.sendSyncAck(data.count)
          .then(() => this.sendStatusQuery())
          .catch((e) => {
            console.error('[BLE] 同步确认/状态刷新失败:', e);
          });
        break;
```

### 5.3 `miniprogram/pages/index/index.wxml`

**将「设备缓存」信息行** 替换为两个独立链接：

原来：

```xml
      <view class="info-row" bindtap="onTapQueryStatus">
        <text class="info-label">设备缓存</text>
        <text class="info-value link">{{bufferUnsent}}/{{bufferCount}} 条待同步 (点击刷新)</text>
      </view>
```

改为：

```xml
      <view class="info-row">
        <text class="info-label">设备缓存</text>
        <view class="info-value">
          <text>{{bufferUnsent}}/{{bufferCount}} 条待同步 </text>
          <text class="link" catchtap="onTapQueryStatus">刷新</text>
          <text> | </text>
          <text class="link {{bufferUnsent > 0 ? '' : 'link-disabled'}}" catchtap="onTapPullHistory">拉取一批</text>
        </view>
      </view>
```

### 5.4 `miniprogram/pages/index/index.wxss`

在 `.info-value.link { ... }` 规则之后追加两条样式（行内链接需要独立的 `.link` 类，以及"无待补"时的灰色禁用态）：

```css
.info-value.link {
  color: #1a73e8;
}

.info-value .link {
  color: #1a73e8;
  padding: 0 4rpx;
}

.info-value .link-disabled {
  color: #bbbbbb;
}
```

### 5.5 `miniprogram/pages/index/index.js`

**在 `onTapQueryStatus` 方法之后新增 `onTapPullHistory`：**

```js
  /**
   * 点击手动拉取一批历史数据
   * 每点一次发一批（最多 BLE_BATCH_SIZE 条），收到后会自动 ACK 并刷新状态
   */
  async onTapPullHistory() {
    if (!this._ble.isConnected) {
      wx.showToast({ title: '未连接设备', icon: 'none' });
      return;
    }
    if (!this._ble.isTimeSynced) {
      wx.showToast({ title: '等待对表完成', icon: 'none' });
      return;
    }
    if (this.data.bufferUnsent <= 0) {
      wx.showToast({ title: '当前无待补数据', icon: 'none' });
      return;
    }
    try {
      await this._ble.sendPullHistory();
      wx.showToast({ title: '已请求一批', icon: 'none' });
    } catch (e) {
      console.error('[Index] 手动拉取失败:', e);
      wx.showToast({ title: '拉取失败', icon: 'none' });
    }
  },
```

---

## 六、验证步骤

1. **编译/烧录 ESP32**：确保 `main.py`、`ble/service.py`、`ble/protocol.py`、`config.py` 已上传。
2. **重启 ESP32**，观察串口输出，不再出现「开始补传…」字样。
3. **小程序侧**：
   - 微信开发者工具中点"编译"，确保前端代码重新加载。
   - "实时监测"页「设备缓存」行应显示：`X/Y 条待同步  刷新 | 拉取一批`。
4. **冒烟测试**：
   - 断开小程序，等 1–2 分钟（累积 12–24 条）。
   - 重新连接 + 对表 → 观察实时数据正常流入，但历史数据保持在缓冲区。
   - 点「刷新」→ `X` 更新为实际待补条数。
   - 点「拉取一批」→ 一次收到一批（≤10 条）历史记录，页面 `historyCount` 增加，`X` 随即减小。
   - 反复点「拉取一批」直到 `X = 0`，进入灰色禁用态。
5. **边界情况**：
   - 未连接点按钮 → 提示「未连接设备」。
   - 未对表点按钮 → 提示「等待对表完成」。
   - `X=0` 点按钮 → 提示「当前无待补数据」。

---

## 七、注意事项

- 改动纯终端侧，无需动后端 `server.py` / `domain/` / `infrastructure/`。
- 环形缓冲区 `sync_cursor` 语义不变：断开重连期间不会丢失已同步进度，也不会重复发送已 ACK 数据。
- 若后续希望支持"一键全量补传"，可在小程序侧加轮询按钮（循环点 `sendPullHistory` 直到 `bufferUnsent === 0`），ESP32 侧无需再改。
