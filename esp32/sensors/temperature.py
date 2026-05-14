"""
水温采集模块 (Temperature Sensor)
====================================
基于 DS18B20 单总线协议，单探头读取水温。

硬件版本: v2（单探头 GPIO13）
"""

import time
from machine import Pin, disable_irq, enable_irq
import onewire
import ds18x20

from config import (
    PIN_DS18B20,
    DS18B20_CONVERSION_MS, DS18B20_MAX_RETRIES,
)


class TemperatureSensor:
    """单探头水温传感器管理器。

    管理一条 OneWire 总线上的单个 DS18B20 探头，
    提供统一的读取接口。
    """

    def __init__(self):
        self._ds = None             # ds18x20 实例
        self._rom = None            # 探头 ROM 地址
        self._initialized = False

    def init(self) -> bool:
        """初始化 OneWire 总线并扫描 DS18B20 探头。

        Returns:
            True 表示检测到探头，False 表示失败
        """
        try:
            pin = Pin(PIN_DS18B20, Pin.IN, Pin.PULL_UP)
            ow = onewire.OneWire(pin)
            self._ds = ds18x20.DS18X20(ow)
            roms = self._ds.scan()

            if roms:
                self._rom = bytes(roms[0])
                self._initialized = True
                print("[温度] GPIO{} 水温探头: {}".format(
                    PIN_DS18B20,
                    self._format_rom(self._rom),
                ))
                if len(roms) > 1:
                    print("[温度] 警告: 检测到 {} 个探头，仅使用第一个".format(len(roms)))
                return True
            else:
                print("[温度] 错误: GPIO{} 未检测到探头!".format(PIN_DS18B20))
                return False
        except Exception as e:
            print("[温度] GPIO{} 初始化失败: {}".format(PIN_DS18B20, e))
            return False

    def read(self) -> dict:
        """读取水温数据。

        Returns:
            {
                "t_water": float or None,  # 水温 (℃)
            }
        """
        if not self._initialized or not self._ds or not self._rom:
            return {"t_water": None}

        for attempt in range(DS18B20_MAX_RETRIES):
            try:
                # 暂停系统中断，防止 BLE 射频高频打断 OneWire 微秒级通讯
                irq_state = disable_irq()
                try:
                    self._ds.convert_temp()
                finally:
                    enable_irq(irq_state)

                time.sleep_ms(DS18B20_CONVERSION_MS)

                # 读取数据同样需要中断保护
                irq_state = disable_irq()
                try:
                    temp = self._ds.read_temp(self._rom)
                finally:
                    enable_irq(irq_state)

                # 过滤异常值（85.0 = 上电默认值，-127.0 = 通信失败）
                if temp == 85.0 or temp == -127.0:
                    raise ValueError("异常温度值: {:.1f}".format(temp))

                return {"t_water": round(temp, 2)}

            except Exception as e:
                if attempt < DS18B20_MAX_RETRIES - 1:
                    print("[温度] 读取重试({}/{}): {}".format(
                        attempt + 1, DS18B20_MAX_RETRIES, e))
                    time.sleep_ms(200)
                else:
                    print("[温度] 读取失败(已重试{}次): {}".format(DS18B20_MAX_RETRIES, e))

        return {"t_water": None}

    @staticmethod
    def _format_rom(rom) -> str:
        """将 ROM 地址格式化为十六进制字符串，便于调试输出。"""
        return "".join("{:02X}".format(b) for b in rom)
