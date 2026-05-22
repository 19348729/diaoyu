"""
水温 + 气压 + 气温 三参数读取程序 - MicroPython (ESP32)
========================================================
硬件接线（依据本次硬件改动）：
  - DS18B20 水温探头:
        DATA -> GPIO13   （需 4.7kΩ 上拉电阻到 3.3V）
        VCC  -> 3.3V
        GND  -> GND
  - BMP280 气压/气温模块:
        SCL  -> GPIO15
        SDA  -> GPIO2
        VCC  -> 3.3V
        GND  -> GND
        SDO  -> GND  (I2C 地址 0x76)

输出：每 5 秒打印一次  水温 / 气温 / 气压
本文件为独立测试脚本，不依赖 config.py，可直接运行调试。
"""

import time
import struct
from machine import Pin, I2C
import onewire
import ds18x20


# ──────────────────────────────────────────────
#  引脚配置
# ──────────────────────────────────────────────
PIN_DS18B20 = 13          # 水温探头 DATA 引脚
PIN_I2C_SCL = 15          # BMP280 SCL
PIN_I2C_SDA = 2           # BMP280 SDA
BMP280_ADDR = 0x76        # SDO 接 GND -> 0x76；接 VCC -> 0x77

READ_INTERVAL_SEC = 5     # 主循环采样间隔


# ──────────────────────────────────────────────
#  DS18B20 水温
# ──────────────────────────────────────────────
class WaterTempSensor:
    def __init__(self, pin_num):
        self._pin_num = pin_num
        self._ds = None
        self._rom = None

    def init(self):
        try:
            pin = Pin(self._pin_num, Pin.IN, Pin.PULL_UP)
            ow = onewire.OneWire(pin)
            self._ds = ds18x20.DS18X20(ow)
            roms = self._ds.scan()
            if not roms:
                print("[水温] GPIO{} 未检测到 DS18B20，请检查接线和上拉电阻".format(self._pin_num))
                return False
            # 单探头：取第一个 ROM
            self._rom = roms[0]
            addr_str = "".join("{:02X}".format(b) for b in self._rom)
            print("[水温] DS18B20 初始化成功 (GPIO{}, ROM={})".format(self._pin_num, addr_str))
            return True
        except Exception as e:
            print("[水温] 初始化失败: {}".format(e))
            return False

    def read(self, max_retries=3):
        if self._ds is None or self._rom is None:
            return None
        for attempt in range(max_retries):
            try:
                self._ds.convert_temp()
                time.sleep_ms(750)        # 12-bit 转换约 750ms
                temp = self._ds.read_temp(self._rom)
                # 过滤 DS18B20 常见的异常值
                if temp is None or temp == 85.0 or temp == -127.0:
                    raise ValueError("异常读数 {}".format(temp))
                return round(temp, 2)
            except Exception as e:
                if attempt < max_retries - 1:
                    print("[水温] 读取重试 {}/{}: {}".format(attempt + 1, max_retries, e))
                    time.sleep_ms(200)
                else:
                    print("[水温] 读取失败: {}".format(e))
        return None


# ──────────────────────────────────────────────
#  BMP280 气压 + 气温
# ──────────────────────────────────────────────
_REG_ID = 0xD0
_REG_RESET = 0xE0
_REG_STATUS = 0xF3
_REG_CTRL_MEAS = 0xF4
_REG_CONFIG = 0xF5
_REG_PRESS_MSB = 0xF7
_REG_CALIB_START = 0x88
_BMP280_CHIP_ID = 0x58
_OSRS_T_X16 = 0b101
_OSRS_P_X16 = 0b101
_MODE_FORCED = 0b01


class AirSensor:
    """BMP280 驱动：返回气压 (hPa) 与气温 (℃)。"""

    def __init__(self, scl_pin, sda_pin, addr=0x76):
        self._scl = scl_pin
        self._sda = sda_pin
        self._addr = addr
        self._i2c = None
        self._initialized = False
        # 校准参数
        self._dig_T1 = self._dig_T2 = self._dig_T3 = 0
        self._dig_P1 = self._dig_P2 = self._dig_P3 = 0
        self._dig_P4 = self._dig_P5 = self._dig_P6 = 0
        self._dig_P7 = self._dig_P8 = self._dig_P9 = 0

    def init(self):
        try:
            self._i2c = I2C(scl=Pin(self._scl), sda=Pin(self._sda), freq=100000)
            devs = self._i2c.scan()
            print("[气压] I2C 总线扫描到设备: {}".format(["0x{:02X}".format(d) for d in devs]))
            if self._addr not in devs:
                print("[气压] 在 0x{:02X} 未找到 BMP280，请检查接线 (SCL=GPIO{}, SDA=GPIO{})".format(
                    self._addr, self._scl, self._sda))
                return False

            chip_id = self._read_reg(_REG_ID, 1)[0]
            if chip_id == _BMP280_CHIP_ID:
                pass
            elif chip_id == 0x60:
                print("[气压] 检测到 BME280 (兼容 BMP280)")
            else:
                print("[气压] 芯片 ID 不匹配: 0x{:02X}".format(chip_id))
                return False

            # 软复位
            self._write_reg(_REG_RESET, 0xB6)
            time.sleep_ms(10)

            self._read_calibration()
            # IIR 滤波系数 = 4
            self._write_reg(_REG_CONFIG, (0b010 << 5) | (0b00 << 2))

            self._initialized = True
            print("[气压] BMP280 初始化成功 (I2C 0x{:02X})".format(self._addr))
            return True
        except Exception as e:
            print("[气压] 初始化失败: {}".format(e))
            return False

    def read(self):
        """返回 (pressure_hPa, temperature_C)；失败时返回 (None, None)。"""
        if not self._initialized:
            return (None, None)
        try:
            ctrl = (_OSRS_T_X16 << 5) | (_OSRS_P_X16 << 2) | _MODE_FORCED
            self._write_reg(_REG_CTRL_MEAS, ctrl)
            time.sleep_ms(50)
            for _ in range(10):
                if (self._read_reg(_REG_STATUS, 1)[0] & 0x08) == 0:
                    break
                time.sleep_ms(5)

            raw = self._read_reg(_REG_PRESS_MSB, 6)
            raw_p = (raw[0] << 12) | (raw[1] << 4) | (raw[2] >> 4)
            raw_t = (raw[3] << 12) | (raw[4] << 4) | (raw[5] >> 4)

            t, t_fine = self._compensate_T(raw_t)
            p = self._compensate_P(raw_p, t_fine)
            return (round(p, 2), round(t, 2))
        except Exception as e:
            print("[气压] 读取失败: {}".format(e))
            return (None, None)

    # ── 内部辅助 ──
    def _read_reg(self, reg, length):
        return self._i2c.readfrom_mem(self._addr, reg, length)

    def _write_reg(self, reg, value):
        self._i2c.writeto_mem(self._addr, reg, bytes([value]))

    def _read_calibration(self):
        c = self._read_reg(_REG_CALIB_START, 26)
        self._dig_T1 = struct.unpack_from("<H", c, 0)[0]
        self._dig_T2 = struct.unpack_from("<h", c, 2)[0]
        self._dig_T3 = struct.unpack_from("<h", c, 4)[0]
        self._dig_P1 = struct.unpack_from("<H", c, 6)[0]
        self._dig_P2 = struct.unpack_from("<h", c, 8)[0]
        self._dig_P3 = struct.unpack_from("<h", c, 10)[0]
        self._dig_P4 = struct.unpack_from("<h", c, 12)[0]
        self._dig_P5 = struct.unpack_from("<h", c, 14)[0]
        self._dig_P6 = struct.unpack_from("<h", c, 16)[0]
        self._dig_P7 = struct.unpack_from("<h", c, 18)[0]
        self._dig_P8 = struct.unpack_from("<h", c, 20)[0]
        self._dig_P9 = struct.unpack_from("<h", c, 22)[0]

    def _compensate_T(self, raw_t):
        v1 = (raw_t / 16384.0 - self._dig_T1 / 1024.0) * self._dig_T2
        v2 = ((raw_t / 131072.0 - self._dig_T1 / 8192.0) ** 2) * self._dig_T3
        t_fine = v1 + v2
        return t_fine / 5120.0, t_fine

    def _compensate_P(self, raw_p, t_fine):
        v1 = t_fine / 2.0 - 64000.0
        v2 = v1 * v1 * self._dig_P6 / 32768.0
        v2 = v2 + v1 * self._dig_P5 * 2.0
        v2 = v2 / 4.0 + self._dig_P4 * 65536.0
        v1 = (self._dig_P3 * v1 * v1 / 524288.0 + self._dig_P2 * v1) / 524288.0
        v1 = (1.0 + v1 / 32768.0) * self._dig_P1
        if v1 == 0:
            return 0.0
        p = 1048576.0 - raw_p
        p = ((p - v2 / 4096.0) * 6250.0) / v1
        v1 = self._dig_P9 * p * p / 2147483648.0
        v2 = p * self._dig_P8 / 32768.0
        p = p + (v1 + v2 + self._dig_P7) / 16.0
        return p / 100.0   # Pa -> hPa


# ──────────────────────────────────────────────
#  主程序
# ──────────────────────────────────────────────
def main():
    print("=" * 48)
    print("ESP32 水温 + 气压 + 气温 读取程序")
    print("  水温 (DS18B20) -> GPIO{}".format(PIN_DS18B20))
    print("  气压/气温 (BMP280) -> SCL=GPIO{}, SDA=GPIO{}".format(PIN_I2C_SCL, PIN_I2C_SDA))
    print("  采样间隔: {} 秒".format(READ_INTERVAL_SEC))
    print("=" * 48)

    water = WaterTempSensor(PIN_DS18B20)
    air = AirSensor(PIN_I2C_SCL, PIN_I2C_SDA, BMP280_ADDR)

    water_ok = water.init()
    air_ok = air.init()

    if not water_ok and not air_ok:
        print("[主程序] 所有传感器均未就绪，请检查硬件后重启。")
        return

    print("\n开始循环采样...\n")

    while True:
        ts = time.localtime()
        t_str = "{:02d}:{:02d}:{:02d}".format(ts[3], ts[4], ts[5])

        t_water = water.read() if water_ok else None
        p_air, t_air = air.read() if air_ok else (None, None)

        def fmt(v, unit):
            return "{:.2f}{}".format(v, unit) if v is not None else "--"

        print("[{}] 水温: {} | 气温: {} | 气压: {}".format(
            t_str,
            fmt(t_water, "°C"),
            fmt(t_air, "°C"),
            fmt(p_air, "hPa"),
        ))

        time.sleep(READ_INTERVAL_SEC)


if __name__ == "__main__":
    main()
