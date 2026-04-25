"""
BMP280 气压传感器采集模块 (Pressure Sensor)
=============================================
通过 I2C 软总线读取 BMP280 的气压和环境温度数据。
实现寄存器级驱动，不依赖第三方库。

参考数据手册: Bosch BMP280 (BST-BMP280-DS001)
"""

import time
from machine import Pin, SoftI2C
import struct

from config import PIN_I2C_SDA, PIN_I2C_SCL, BMP280_I2C_ADDR


# ── BMP280 寄存器地址 ──
_REG_ID = 0xD0
_REG_RESET = 0xE0
_REG_STATUS = 0xF3
_REG_CTRL_MEAS = 0xF4
_REG_CONFIG = 0xF5
_REG_PRESS_MSB = 0xF7
_REG_CALIB_START = 0x88   # 补偿参数起始地址（26 字节）

# 芯片 ID
_BMP280_CHIP_ID = 0x58

# 过采样配置
_OSRS_T_X16 = 0b101       # 温度 16x 过采样
_OSRS_P_X16 = 0b101       # 气压 16x 过采样
_MODE_FORCED = 0b01        # 强制测量模式（单次测量后自动休眠）


class PressureSensor:
    """BMP280 气压传感器驱动。

    使用强制测量模式（Forced Mode），每次调用 read() 时触发一次测量，
    读取完成后芯片自动进入休眠，功耗极低。
    """

    def __init__(self):
        self._i2c = None
        self._addr = BMP280_I2C_ADDR
        self._initialized = False
        # 补偿参数（从芯片 NVM 读取）
        self._dig_T1 = 0
        self._dig_T2 = 0
        self._dig_T3 = 0
        self._dig_P1 = 0
        self._dig_P2 = 0
        self._dig_P3 = 0
        self._dig_P4 = 0
        self._dig_P5 = 0
        self._dig_P6 = 0
        self._dig_P7 = 0
        self._dig_P8 = 0
        self._dig_P9 = 0

    def init(self) -> bool:
        """初始化 I2C 总线并验证 BMP280 芯片。

        Returns:
            True 表示初始化成功
        """
        try:
            self._i2c = SoftI2C(
                scl=Pin(PIN_I2C_SCL),
                sda=Pin(PIN_I2C_SDA),
                freq=100000,
            )

            # 验证芯片 ID
            chip_id = self._read_reg(_REG_ID, 1)[0]
            if chip_id != _BMP280_CHIP_ID:
                # BME280 的 ID 是 0x60，也兼容
                if chip_id == 0x60:
                    print("[气压] 检测到 BME280 (兼容 BMP280)")
                else:
                    print("[气压] 芯片 ID 不匹配: 0x{:02X} (预期 0x{:02X})".format(
                        chip_id, _BMP280_CHIP_ID))
                    return False

            # 软复位
            self._write_reg(_REG_RESET, 0xB6)
            time.sleep_ms(10)

            # 读取补偿参数
            self._read_calibration()

            # 配置: IIR 滤波系数=4, 待机时间=0.5ms
            self._write_reg(_REG_CONFIG, (0b010 << 5) | (0b00 << 2))

            self._initialized = True
            print("[气压] BMP280 初始化成功 (I2C 地址: 0x{:02X})".format(self._addr))
            return True

        except Exception as e:
            print("[气压] 初始化失败: {}".format(e))
            return False

    def read(self) -> dict:
        """触发一次测量并读取气压和温度。

        Returns:
            {
                "p_local": float,   # 本地气压 (hPa)
                "t_env":   float,   # 环境温度 (℃) —— BMP280 自带的温度，非水温
            }
            读取失败时值为 None
        """
        if not self._initialized:
            return {"p_local": None, "t_env": None}

        try:
            # 设置强制测量模式: 温度16x + 气压16x + forced mode
            ctrl = (_OSRS_T_X16 << 5) | (_OSRS_P_X16 << 2) | _MODE_FORCED
            self._write_reg(_REG_CTRL_MEAS, ctrl)

            # 等待测量完成（16x 过采样约需 ~44ms）
            time.sleep_ms(50)

            # 等待 status 寄存器的 measuring 位清零
            for _ in range(10):
                status = self._read_reg(_REG_STATUS, 1)[0]
                if (status & 0x08) == 0:
                    break
                time.sleep_ms(5)

            # 读取原始数据（6字节: press_msb, press_lsb, press_xlsb, temp_msb, temp_lsb, temp_xlsb）
            raw = self._read_reg(_REG_PRESS_MSB, 6)

            raw_press = (raw[0] << 12) | (raw[1] << 4) | (raw[2] >> 4)
            raw_temp = (raw[3] << 12) | (raw[4] << 4) | (raw[5] >> 4)

            # 补偿计算
            temperature, t_fine = self._compensate_temperature(raw_temp)
            pressure = self._compensate_pressure(raw_press, t_fine)

            return {
                "p_local": round(pressure, 2),
                "t_env": round(temperature, 2),
            }

        except Exception as e:
            print("[气压] 读取失败: {}".format(e))
            return {"p_local": None, "t_env": None}

    def _read_calibration(self):
        """读取 BMP280 NVM 中的补偿参数（出厂校准值）。"""
        calib = self._read_reg(_REG_CALIB_START, 26)

        # 使用 struct 解包：小端序
        # 温度补偿参数
        self._dig_T1 = struct.unpack_from("<H", calib, 0)[0]   # unsigned short
        self._dig_T2 = struct.unpack_from("<h", calib, 2)[0]   # signed short
        self._dig_T3 = struct.unpack_from("<h", calib, 4)[0]

        # 气压补偿参数
        self._dig_P1 = struct.unpack_from("<H", calib, 6)[0]
        self._dig_P2 = struct.unpack_from("<h", calib, 8)[0]
        self._dig_P3 = struct.unpack_from("<h", calib, 10)[0]
        self._dig_P4 = struct.unpack_from("<h", calib, 12)[0]
        self._dig_P5 = struct.unpack_from("<h", calib, 14)[0]
        self._dig_P6 = struct.unpack_from("<h", calib, 16)[0]
        self._dig_P7 = struct.unpack_from("<h", calib, 18)[0]
        self._dig_P8 = struct.unpack_from("<h", calib, 20)[0]
        self._dig_P9 = struct.unpack_from("<h", calib, 22)[0]

    def _compensate_temperature(self, raw_temp: int):
        """温度补偿计算（数据手册公式）。

        Returns:
            (temperature_celsius, t_fine)
        """
        var1 = (raw_temp / 16384.0 - self._dig_T1 / 1024.0) * self._dig_T2
        var2 = ((raw_temp / 131072.0 - self._dig_T1 / 8192.0) ** 2) * self._dig_T3
        t_fine = var1 + var2
        temperature = t_fine / 5120.0
        return temperature, t_fine

    def _compensate_pressure(self, raw_press: int, t_fine: float) -> float:
        """气压补偿计算（数据手册公式）。

        Returns:
            压力值 (hPa)
        """
        var1 = t_fine / 2.0 - 64000.0
        var2 = var1 * var1 * self._dig_P6 / 32768.0
        var2 = var2 + var1 * self._dig_P5 * 2.0
        var2 = var2 / 4.0 + self._dig_P4 * 65536.0
        var1 = (self._dig_P3 * var1 * var1 / 524288.0 + self._dig_P2 * var1) / 524288.0
        var1 = (1.0 + var1 / 32768.0) * self._dig_P1

        if var1 == 0:
            return 0.0

        pressure = 1048576.0 - raw_press
        pressure = ((pressure - var2 / 4096.0) * 6250.0) / var1
        var1 = self._dig_P9 * pressure * pressure / 2147483648.0
        var2 = pressure * self._dig_P8 / 32768.0
        pressure = pressure + (var1 + var2 + self._dig_P7) / 16.0

        # 转换 Pa -> hPa
        return pressure / 100.0

    def _read_reg(self, reg: int, length: int) -> bytes:
        """读取 I2C 寄存器。"""
        return self._i2c.readfrom_mem(self._addr, reg, length)

    def _write_reg(self, reg: int, value: int):
        """写入 I2C 寄存器。"""
        self._i2c.writeto_mem(self._addr, reg, bytes([value]))
