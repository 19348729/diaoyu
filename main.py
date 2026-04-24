import argparse
import sys

# 强制切换标准输出为 utf-8，防止 Windows 终端 Emoji 乱码
sys.stdout.reconfigure(encoding='utf-8')

from domain.value_objects import HardwareData, ApiData
from domain.services import FishingPredictionService
from domain.constants import FISH_PROFILES

def main():
    parser = argparse.ArgumentParser(description="AI 钓鱼预测核心算法演示")
    parser.add_argument(
        "--fish", 
        type=str, 
        default="鲫鱼", 
        choices=list(FISH_PROFILES.keys()),
        help=f"目标鱼种，可选值: {', '.join(FISH_PROFILES.keys())}"
    )
    args = parser.parse_args()
    
    target_fish_name = args.fish
    fish_profile = FISH_PROFILES[target_fish_name]

    print("=" * 40)
    print(f"🎣 AI 钓鱼预测核心算法 - 运行演示 [目标鱼种: {target_fish_name}]")
    print("=" * 40)

    # 1. 初始化核心业务服务实例（动态注入用户选择的鱼种配置）
    prediction_service = FishingPredictionService(fish_profile=fish_profile)

    print("\n[ 系统 ] 正在从边缘传感设备及云端气象API获取数据...")
    
    # 2. 模拟准备边缘硬件采集的数据 (比如温度、气压)
    hardware_data = HardwareData(
        t_water=42.5,     # 测试水温 32.5℃ (对鲫鱼/草鱼是极端高温停口，但对罗非/鲢鳙则是黄金温度)
        p_local=1008.5,   # 本地绝对气压：1008.5 hPa
        delta_p=1.2       # 气压趋势：过去2小时气压处于稳步回升状态 (+1.2 hPa)
    )

    # 3. 模拟准备云端请求的气象辅助数据
    api_data = ApiData(
        wind_speed=2.5,         # 风速 2.5 m/s （微风有助于水面起波浪增氧）
        altitude=150.0,         # 钓点海拔 150m
        weather_trend="sunny"   # 短临天气趋势为晴朗
    )

    print(f"  -> 水温: {hardware_data.t_water}℃ | 气压: {hardware_data.p_local}hPa | 气压变化: +{hardware_data.delta_p}hPa/2h")
    print(f"  -> 风速: {api_data.wind_speed}m/s | 天气: {api_data.weather_trend}")

    print("\n[ 系统 ] 开始多因子数据融合计算与推演...")
    
    # 4. 传入核心领域引擎执行预测
    result = prediction_service.predict(hardware=hardware_data, api=api_data)

    # 5. 可视化输出分析结果
    print("\n" + "=" * 40)
    print("🎯 最终预测结果")
    print("=" * 40)
    print(f"💧 虚拟溶解氧指标  : {result.do_trend} mg/L")
    print(f"⭐ 最终综合开口分数: {result.bite_index} / 100")
    print("🏷️  触发的战术标签集合:")
    
    for tag in result.tactical_tags:
        print(f"    ✅ {tag}")
        
    print("\n(开发提示：您可以将上述标签通过系统拼接后，发送给 LLM 生成如：「当前天气晴朗且气压回升，鲫鱼摄食欲望极其强烈...」 的人类播报语音)")

if __name__ == "__main__":
    main()
