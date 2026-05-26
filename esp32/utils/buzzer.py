"""
ESP32-B 终端蜂鸣器声音报警模块 (Buzzer Alarm Driver)
===================================================
- 采用完全非阻塞 (Non-blocking) 的时间差状态机设计，绝不影响主循环通信。
- 采用 MicroPython PWM 调节频率，完美呈现不同等级的鱼讯听觉效果。
- 鸣叫结束自动 deinit() 释放 PWM，并将 GPIO 强行拉低，实现零功耗待机、防止漏电发热。
- 内置 3.5 秒冷却去抖保护，防范连续高频重复触发。
"""

import time
import machine
from machine import Pin, PWM
from config import PIN_BUZZER

# 告警级别常量
ALARM_NONE = 0
ALARM_BOTTOM_FISH = 1
ALARM_MID_FISH = 2

class BuzzerManager:
    """非阻塞蜂鸣器声学状态机管理器"""
    
    def __init__(self, pin_num=PIN_BUZZER):
        self.pin_num = pin_num
        self.pwm = None
        self._seq = []              # 当前播放的音符序列：[(freq, duration_ms), ...]
        self._seq_idx = -1          # 当前正在播放的音符索引，-1 表示空闲
        self._next_change_ms = 0    # 下一次状态改变的 tick_ms
        self._last_trigger_time = 0 # 上一次成功鸣叫的时间戳 (tick_ms)
        self._last_alarm = ALARM_NONE
        
    def init(self):
        """初始化蜂鸣器引脚为输出低电平（暂不开启 PWM，防上电杂音和漏电）"""
        try:
            p = Pin(self.pin_num, Pin.OUT)
            p.value(0)
            print("[Buzzer] 蜂鸣器引脚 GPIO{} 初始化成功".format(self.pin_num))
        except Exception as e:
            print("[Buzzer] 引脚 GPIO{} 初始化失败: {}".format(self.pin_num, e))

    def trigger(self, alarm_level):
        """触发与鱼讯等级对应的特征声音。
        
        策略:
          - 级别 0: 无鱼，静音。
          - 级别 1 (底层拱窝): 低音 di-di 双击。800Hz, 短促清脆。
          - 级别 2 (中层截杀): 高音 DIIII~ 长鸣。2500Hz, 响亮急促。
        
        去抖与冷却保护:
          - 相同级别的鱼讯触发有 3.5 秒 (3500ms) 的冷却保护，防止高频冗余鸣叫。
          - 高级别警报 (中层截杀) 可以随时打断并覆盖低级别警报 (底层拱窝)。
        """
        if alarm_level == ALARM_NONE:
            self._last_alarm = ALARM_NONE
            return

        now = time.ticks_ms()

        # 1. 冷却保护判断：如果鱼讯未发生级别提升，且在 3.5 秒冷却期内，则跳过触发
        if alarm_level <= self._last_alarm:
            if time.ticks_diff(now, self._last_trigger_time) < 3500:
                return

        self._last_alarm = alarm_level
        self._last_trigger_time = now

        # 2. 装载对应等级的音调脉冲序列 [(频率, 持续时间ms), ...]
        # 频率=0 表示静音停顿
        if alarm_level == ALARM_BOTTOM_FISH:
            # 底层拱窝: 800Hz 低音 di-di 双击 (di: 60ms -> pause: 60ms -> di: 60ms)
            self._seq = [
                (800, 60),
                (0, 60),
                (800, 60)
            ]
            print("[Buzzer] 触发【底层拱窝】声效: di-di")
        elif alarm_level == ALARM_MID_FISH:
            # 中层截杀: 2500Hz 强力高音长鸣 (DIIII~: 350ms)
            self._seq = [
                (2500, 350)
            ]
            print("[Buzzer] 触发【中层截杀】声效: DIIII~~")

        # 3. 开启序列播放，非阻塞启动状态机
        self._seq_idx = 0
        self._next_change_ms = now

    def tick(self):
        """状态机时钟轮询。必须由主程序在 tick_callback() 中定期调用（节拍 50ms）"""
        if self._seq_idx < 0:
            return

        now = time.ticks_ms()
        # 判断当前音符是否播放时间已满
        if time.ticks_diff(now, self._next_change_ms) >= 0:
            if self._seq_idx < len(self._seq):
                # 播放当前音符
                freq, duration = self._seq[self._seq_idx]
                self._play(freq)
                
                # 计算下一个切换的时间点
                self._next_change_ms = time.ticks_add(now, duration)
                self._seq_idx += 1
            else:
                # 序列全部播放完毕，彻底关闭声音，恢复空闲状态
                self._play(0)
                self._seq_idx = -1

    def _play(self, freq):
        """控制底层 PWM 频率。freq = 0 表示完全静音并释放硬件。"""
        try:
            if freq > 0:
                # 开启 PWM，占空比 50% (512/1024) 保证方波发声清脆
                if self.pwm is None:
                    self.pwm = PWM(Pin(self.pin_num), freq=freq, duty=512)
                else:
                    self.pwm.freq(freq)
                    self.pwm.duty(512)
            else:
                # 静音关载：彻底销毁 PWM，强制拉低物理引脚，防持续直通功耗与漏电
                if self.pwm is not None:
                    try:
                        self.pwm.deinit()
                    except Exception:
                        pass
                    self.pwm = None
                
                # 强行将引脚切换为通用输出引脚并置为 0 (拉低)
                p = Pin(self.pin_num, Pin.OUT)
                p.value(0)
        except Exception as e:
            print("[Buzzer] 底层发声异常 (GPIO{}): {}".format(self.pin_num, e))
            # 异常应急处理：清除 PWM
            self.pwm = None
