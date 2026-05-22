"""
DS18B20 双探头测试脚本
========================
测试目标：GPIO15 单总线连接两个 DS18B20 温度探头
功能：扫描 ROM 地址，循环读取并打印两个探头的温度值

硬件接线：
  - GPIO15 接两个 DS18B20 的 DATA 引脚（并联）
  - 两个 DS18B20 的 VCC 接 3.3V
  - 两个 DS18B20 的 GND 接 GND
  - GPIO15 需要通过 4.7kΩ 上拉电阻连接到 3.3V
"""

import time
from machine import Pin
import onewire
import ds18x20

# GPIO15 引脚定义
PIN_TEMP = 15

def format_rom(rom):
    """将 ROM 地址格式化为十六进制字符串"""
    return "".join("{:02X}".format(b) for b in rom)

def main():
    """主测试函数"""
    print("=" * 50)
    print("DS18B20 双探头测试 - GPIO15")
    print("=" * 50)
    
    # 初始化单总线
    try:
        pin = Pin(PIN_TEMP, Pin.IN, Pin.PULL_UP)
        ow = onewire.OneWire(pin)
        ds = ds18x20.DS18X20(ow)
        print("[成功] 单总线初始化完成 (GPIO{})".format(PIN_TEMP))
    except Exception as e:
        print("[错误] 单总线初始化失败: {}".format(e))
        return
    
    # 扫描连接的 DS18B20 探头
    print("\n正在扫描 DS18B20 探头...")
    roms = ds.scan()
    
    if not roms:
        print("[错误] 未检测到任何 DS18B20 探头!")
        print("请检查:")
        print("  1. 探头是否正确连接到 GPIO{}".format(PIN_TEMP))
        print("  2. 是否连接了 4.7kΩ 上拉电阻")
        print("  3. VCC 和 GND 是否正确连接")
        return
    
    print("[成功] 检测到 {} 个 DS18B20 探头".format(len(roms)))
    for i, rom in enumerate(roms):
        print("  探头 {}: {}".format(i + 1, format_rom(rom)))
    
    if len(roms) < 2:
        print("\n[警告] 预期检测到 2 个探头，但只检测到 {} 个".format(len(roms)))
        print("如果只连接了一个探头，这是正常的")
    
    print("\n开始读取温度数据 (按 Ctrl+C 停止)...")
    print("-" * 50)
    
    # 循环读取温度
    try:
        while True:
            # 启动温度转换
            ds.convert_temp()
            
            # 等待转换完成（12位精度需要约750ms）
            time.sleep_ms(750)
            
            # 读取并打印每个探头的温度
            print("\n[{}] 温度读取结果:".format(
                time.strftime("%Y-%m-%d %H:%M:%S")))
            
            for i, rom in enumerate(roms):
                try:
                    temp = ds.read_temp(rom)
                    
                    # 检查异常值
                    if temp == 85.0:
                        print("  探头 {}: {}°C (上电默认值，可能需要等待)".format(
                            i + 1, temp))
                    elif temp == -127.0:
                        print("  探头 {}: {}°C (通信失败)".format(
                            i + 1, temp))
                    else:
                        print("  探头 {}: {:.2f}°C [ROM: {}]".format(
                            i + 1, temp, format_rom(rom)))
                except Exception as e:
                    print("  探头 {}: 读取失败 - {}".format(i + 1, e))
            
            # 等待下一次读取
            time.sleep(2)
            
    except KeyboardInterrupt:
        print("\n\n测试已手动停止")
    except Exception as e:
        print("\n[错误] 测试过程中出现异常: {}".format(e))

if __name__ == "__main__":
    main()
