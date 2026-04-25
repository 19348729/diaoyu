import argparse
import sys
import time

# 强制切换标准输出为 utf-8，防止 Windows 终端 Emoji 乱码
sys.stdout.reconfigure(encoding='utf-8')

from domain.value_objects import (
    HardwareData, ApiData, SensorReading, SensorTimeSeries, SessionContext,
)
from domain.services import FishingPredictionService
from domain.constants import FISH_PROFILES
from domain.time_utils import build_session_context


def _build_mock_series(base_ts: int, duration_minutes: int = 30) -> SensorTimeSeries:
    """构造模拟时序数据（模拟 ESP32 持续采集）。
    
    模拟场景：水温缓慢上升，气压稳步回升，表底温差约2℃。
    """
    readings = []
    interval = 5  # 每5秒一条
    num_points = (duration_minutes * 60) // interval

    for i in range(num_points):
        ts = base_ts + i * interval
        progress = i / max(num_points - 1, 1)  # 0.0 ~ 1.0

        # 水底温度：18.0 -> 19.5（缓慢上升）
        t_bottom = 18.0 + progress * 1.5
        # 水下1米：比底层高0.5~1.0度
        t_mid = t_bottom + 0.5 + progress * 0.5
        # 水面：比底层高1.5~2.5度
        t_surface = t_bottom + 1.5 + progress * 1.0
        # 气压：1008.0 -> 1009.5（稳步回升）
        p_local = 1008.0 + progress * 1.5

        readings.append(SensorReading(
            timestamp=ts,
            t_bottom=round(t_bottom, 2),
            t_mid=round(t_mid, 2),
            t_surface=round(t_surface, 2),
            p_local=round(p_local, 2),
        ))

    return SensorTimeSeries(readings=tuple(readings))


def main():
    parser = argparse.ArgumentParser(description="AI 钓鱼预测核心算法演示")
    parser.add_argument(
        "--fish", 
        type=str, 
        default="鲫鱼", 
        choices=list(FISH_PROFILES.keys()),
        help=f"目标鱼种，可选值: {', '.join(FISH_PROFILES.keys())}"
    )
    parser.add_argument(
        "--mode",
        type=str,
        default="series",
        choices=["legacy", "series"],
        help="预测模式: legacy=单帧快照, series=时序数据"
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=30,
        help="模拟采集时长（分钟），仅 series 模式有效"
    )
    args = parser.parse_args()
    
    target_fish_name = args.fish
    fish_profile = FISH_PROFILES[target_fish_name]

    print("=" * 60)
    print(f"  AI 钓鱼预测核心算法 - 运行演示 [目标鱼种: {target_fish_name}]")
    print("=" * 60)

    # 初始化核心业务服务实例
    prediction_service = FishingPredictionService(fish_profile=fish_profile)

    # 模拟云端气象数据
    api_data = ApiData(
        wind_speed=2.5,
        altitude=150.0,
        weather_trend="sunny"
    )

    if args.mode == "legacy":
        _run_legacy_mode(prediction_service, api_data)
    else:
        _run_series_mode(prediction_service, api_data, args.duration)


def _run_legacy_mode(service: FishingPredictionService, api: ApiData):
    """向后兼容的单帧快照模式。"""
    print("\n[模式] 单帧快照预测 (Legacy)")
    print("-" * 40)

    hardware_data = HardwareData(
        t_water=22.5,
        p_local=1008.5,
        delta_p=1.2
    )

    print(f"  水温: {hardware_data.t_water}℃ | 气压: {hardware_data.p_local}hPa | 气压变化: +{hardware_data.delta_p}hPa/2h")
    print(f"  风速: {api.wind_speed}m/s | 天气: {api.weather_trend}")

    result = service.predict(hardware=hardware_data, api=api)
    _print_result(result)


def _run_series_mode(service: FishingPredictionService, api: ApiData, duration_min: int):
    """新版时序数据预测模式。"""
    print(f"\n[模式] 时序数据预测 (Series) - 模拟采集 {duration_min} 分钟")
    print("-" * 40)

    base_ts = int(time.time()) - duration_min * 60
    series = _build_mock_series(base_ts, duration_min)

    print(f"  数据点数: {series.count} 条")
    print(f"  时间跨度: {series.duration_seconds} 秒 ({series.duration_seconds // 60} 分钟)")

    latest = series.latest
    if latest:
        print(f"  最新水底温度: {latest.t_bottom}℃")
        print(f"  最新水下1米: {latest.t_mid}℃")
        print(f"  最新水面温度: {latest.t_surface}℃")
        print(f"  最新气压:     {latest.p_local}hPa")

    print(f"  风速: {api.wind_speed}m/s | 天气: {api.weather_trend}")

    # 全量数据预测（full 阶段）
    result_full = service.predict_from_series(series=series, api=api)
    print(f"\n--- 完整报告 ({duration_min}分钟数据) ---")
    _print_result(result_full)

    # 演示渐进式报告：截取不同时长的数据
    stages_demo = [
        ("instant (刚连接)", 0),
        ("brief (5分钟)", 300),
        ("standard (10分钟)", 600),
    ]

    for stage_name, min_seconds in stages_demo:
        # 截取对应时长的数据
        if min_seconds == 0:
            sub_readings = (series.readings[-1],) if series.readings else ()
        else:
            cutoff_ts = series.latest.timestamp - min_seconds
            sub_readings = tuple(r for r in series.readings if r.timestamp >= cutoff_ts)

        sub_series = SensorTimeSeries(readings=sub_readings)
        result = service.predict_from_series(series=sub_series, api=api)

        print(f"\n--- {stage_name} ---")
        print(f"  报告阶段: {result.report_stage} | 置信度: {result.confidence}%")
        print(f"  开口分数: {result.bite_index}/100")
        print(f"  标签数: {len(result.tactical_tags)} 个")


def _print_result(result):
    """格式化输出预测结果。"""
    print(f"\n  虚拟溶解氧指标  : {result.do_trend} mg/L")
    print(f"  最终综合开口分数: {result.bite_index} / 100")
    print(f"  报告阶段        : {result.report_stage}")
    print(f"  置信度          : {result.confidence}%")

    if result.time_period_advice:
        print(f"  时段建议: {result.time_period_advice}")
    if result.season_note:
        print(f"  季节备注: {result.season_note}")

    print("  触发的战术标签:")
    for tag in result.tactical_tags:
        print(f"    - {tag}")


if __name__ == "__main__":
    main()
