"""
三层水温采集模块 (Temperature Sensors)
========================================
基于 DS18B20 单总线协议，支持双总线布局：
  - GPIO15: 水底温度 + 水下1米温度（两个探头共用单总线，ROM 地址区分）
  - GPIO2:  水面温度（独立总线）

保留 CRC 重试机制确保数据可靠性。
"""

import time
from machine import Pin
import onewire
import ds18x20

from config import (
    PIN_TEMP_DEEP, PIN_TEMP_SURFACE,
    ROM_ADDR_BOTTOM, ROM_ADDR_MID,
    DS18B20_CONVERSION_MS, DS18B20_MAX_RETRIES,
)


class TemperatureSensor:
    """三层水温传感器管理器。

    管理两条 OneWire 总线上的三个 DS18B20 探头，
    提供统一的读取接口。
    """

    def __init__(self):
        self._ds_deep = None        # GPIO15 总线上的 ds18x20 实例
        self._ds_surface = None     # GPIO2 总线上的 ds18x20 实例
        self._rom_bottom = None     # 水底探头 ROM 地址
        self._rom_mid = None        # 水下1米探头 ROM 地址
        self._rom_surface = None    # 水面探头 ROM 地址
        self._initialized = False

    def init(self) -> bool:
        """初始化双总线并扫描所有 DS18B20 探头。

        Returns:
            True 表示至少检测到一个探头，False 表示完全失败
        """
        success = True

        # ── 总线1: GPIO15（水底 + 水下1米）──
        try:
            pin_deep = Pin(PIN_TEMP_DEEP, Pin.IN, Pin.PULL_UP)
            ow_deep = onewire.OneWire(pin_deep)
            self._ds_deep = ds18x20.DS18X20(ow_deep)
            roms_deep = self._ds_deep.scan()

            if len(roms_deep) >= 2:
                # 如果配置了固定 ROM 地址，按配置匹配
                if ROM_ADDR_BOTTOM and ROM_ADDR_MID:
                    self._rom_bottom = ROM_ADDR_BOTTOM
                    self._rom_mid = ROM_ADDR_MID
                    print("[温度] GPIO{} 使用预配置 ROM 地址".format(PIN_TEMP_DEEP))
                else:
                    # 按扫描顺序分配（第一个=水底，第二个=水下1米）
                    self._rom_bottom = roms_deep[0]
                    self._rom_mid = roms_deep[1]
                    print("[温度] GPIO{} 自动分配: 水底={}, 水下1米={}".format(
                        PIN_TEMP_DEEP,
                        self._format_rom(roms_deep[0]),
                        self._format_rom(roms_deep[1]),
                    ))
            elif len(roms_deep) == 1:
                self._rom_bottom = roms_deep[0]
                print("[温度] 警告: GPIO{} 仅检测到1个探头（预期2个）".format(PIN_TEMP_DEEP))
            else:
                print("[温度] 错误: GPIO{} 未检测到探头!".format(PIN_TEMP_DEEP))
                success = False
        except Exception as e:
            print("[温度] GPIO{} 初始化失败: {}".format(PIN_TEMP_DEEP, e))
            success = False

        # ── 总线2: GPIO2（水面）──
        try:
            pin_surface = Pin(PIN_TEMP_SURFACE, Pin.IN, Pin.PULL_UP)
            ow_surface = onewire.OneWire(pin_surface)
            self._ds_surface = ds18x20.DS18X20(ow_surface)
            roms_surface = self._ds_surface.scan()

            if roms_surface:
                self._rom_surface = roms_surface[0]
                print("[温度] GPIO{} 水面探头: {}".format(
                    PIN_TEMP_SURFACE,
                    self._format_rom(roms_surface[0]),
                ))
            else:
                print("[温度] 错误: GPIO{} 未检测到水面探头!".format(PIN_TEMP_SURFACE))
                success = False
        except Exception as e:
            print("[温度] GPIO{} 初始化失败: {}".format(PIN_TEMP_SURFACE, e))
            success = False

        self._initialized = success or (self._rom_bottom is not None) or (self._rom_surface is not None)
        return self._initialized

    def read_all(self) -> dict:
        """读取三层水温数据。

        Returns:
            {
                "t_bottom":  float or None,  # 水底温度 (℃)
                "t_mid":     float or None,  # 水下1米温度 (℃)
                "t_surface": float or None,  # 水面温度 (℃)
                "t_diff":    float or None,  # 温差 = 水面 - 水底 (℃)
            }
        """
        result = {
            "t_bottom": None,
            "t_mid": None,
            "t_surface": None,
            "t_diff": None,
        }

        # 读取 GPIO15 总线（水底 + 水下1米）
        if self._ds_deep and (self._rom_bottom or self._rom_mid):
            temps = self._read_bus(
                self._ds_deep,
                [r for r in [self._rom_bottom, self._rom_mid] if r is not None],
            )
            if self._rom_bottom and self._rom_bottom in temps:
                result["t_bottom"] = temps[self._rom_bottom]
            if self._rom_mid and self._rom_mid in temps:
                result["t_mid"] = temps[self._rom_mid]

        # 读取 GPIO2 总线（水面）
        if self._ds_surface and self._rom_surface:
            temps = self._read_bus(self._ds_surface, [self._rom_surface])
            if self._rom_surface in temps:
                result["t_surface"] = temps[self._rom_surface]

        # 计算温差
        if result["t_surface"] is not None and result["t_bottom"] is not None:
            result["t_diff"] = round(result["t_surface"] - result["t_bottom"], 2)

        return result

    def _read_bus(self, ds, roms, max_retries=None) -> dict:
        """读取指定总线上的温度值，带重试机制。

        Args:
            ds: ds18x20.DS18X20 实例
            roms: 要读取的 ROM 地址列表
            max_retries: 最大重试次数

        Returns:
            {rom_bytes: temperature_float} 字典
        """
        if max_retries is None:
            max_retries = DS18B20_MAX_RETRIES

        for attempt in range(max_retries):
            try:
                ds.convert_temp()
                time.sleep_ms(DS18B20_CONVERSION_MS)

                temps = {}
                for rom in roms:
                    temp = ds.read_temp(rom)
                    # 过滤异常值（85.0 = 上电默认值，-127.0 = 通信失败）
                    if temp == 85.0 or temp == -127.0:
                        raise ValueError("异常温度值: {:.1f}".format(temp))
                    temps[rom] = round(temp, 2)

                return temps

            except Exception as e:
                if attempt < max_retries - 1:
                    print("[温度] 读取重试({}/{}): {}".format(
                        attempt + 1, max_retries, e))
                    time.sleep_ms(200)
                else:
                    print("[温度] 读取失败(已重试{}次): {}".format(max_retries, e))

        return {}

    @staticmethod
    def _format_rom(rom) -> str:
        """将 ROM 地址格式化为十六进制字符串，便于调试输出。"""
        return "".join("{:02X}".format(b) for b in rom)
