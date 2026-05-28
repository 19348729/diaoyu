"""
钓鱼预报服务 (Fishing Forecast Service)
==========================================
基于逐小时天气预报数据，预测今日各时段鱼情，
找出最佳出钓时间窗口。

供 `/api/forecast/today` 接口调用。
"""
from __future__ import annotations

from typing import Dict, List, Optional

from .constants import FishSpeciesProfile
from .services import FishingPredictionService
from .value_objects import ApiData
from .solunar import calc_solunar_rating

import time as _time


class FishingForecastService:
    """基于天气预报的鱼情预测服务。

    消费 QWeatherService.get_hourly_forecast() 返回的逐小时数据，
    对每个小时跑一次 predict_weather_only 简化评分，
    汇总出今日最佳出钓窗口和整体鱼情评级。
    """

    def __init__(self, fish_profile: FishSpeciesProfile = None):
        self.fish_profile = fish_profile or FishSpeciesProfile()

    def calc_hourly_scores(
        self, hourly_data: List[dict], fish_profile: FishSpeciesProfile = None,
    ) -> List[dict]:
        """对逐小时天气数据逐条评分。

        Args:
            hourly_data: QWeatherService.get_hourly_forecast() 的返回值
            fish_profile: 目标鱼种配置（可覆盖实例默认值）

        Returns:
            [
                {
                    "fxTime": "2026-05-05T10:00+08:00",
                    "hour": 10,
                    "temp": 28.0,
                    "weather_text": "晴",
                    "wind_speed": 2.5,
                    "bite_index": 72,
                    "rating": "good",
                },
                ...
            ]
        """
        profile = fish_profile or self.fish_profile
        service = FishingPredictionService(fish_profile=profile)

        results = []
        for h in hourly_data:
            # 构建 ApiData
            api = ApiData(
                wind_speed=h.get("wind_speed", 0.0),
                altitude=0.0,
                weather_trend=h.get("weather_trend", "sunny"),
                wind_direction=h.get("wind_direction", ""),
                humidity=h.get("humidity", 50.0),
                original_text=h.get("weather_text", "晴"),
                original_wind_dir="",
            )

            air_temp = h.get("temp", 20.0)
            pred = service.predict_weather_only(api=api, air_temp=air_temp)

            # 评级文字
            score = pred.bite_index
            if score >= 80:
                rating = "excellent"
            elif score >= 60:
                rating = "good"
            elif score >= 40:
                rating = "fair"
            else:
                rating = "poor"

            results.append({
                "fxTime": h.get("fxTime", ""),
                "hour": h.get("hour", 0),
                "temp": air_temp,
                "weather_text": h.get("weather_text", "晴"),
                "wind_speed": h.get("wind_speed", 0.0),
                "pressure": h.get("pressure", 1013.0),
                "bite_index": score,
                "rating": rating,
            })

        return results

    def calc_best_windows(
        self, hourly_data: List[dict], fish_profile: FishSpeciesProfile = None,
        top_n: int = 3,
    ) -> List[dict]:
        """找出今日最佳出钓时段（top N 个连续高分窗口）。

        算法：对逐小时评分做滑动窗口（2小时），取均分最高的 top_n 个窗口。

        Returns:
            [
                {
                    "start_hour": 6,
                    "end_hour": 8,
                    "avg_score": 76,
                    "label": "06:00-08:00 — 早口黄金期",
                },
                ...
            ]
        """
        scored = self.calc_hourly_scores(hourly_data, fish_profile)
        if len(scored) < 2:
            return []

        # 滑动窗口（2小时）
        windows = []
        window_size = 2
        for i in range(len(scored) - window_size + 1):
            chunk = scored[i:i + window_size]
            avg = sum(c["bite_index"] for c in chunk) / window_size
            start_h = chunk[0]["hour"]
            end_h = chunk[-1]["hour"] + 1  # 结束小时（不含）

            # 时段标签
            if 5 <= start_h < 10:
                label_suffix = "早口黄金期"
            elif 10 <= start_h < 14:
                label_suffix = "午休期"
            elif 14 <= start_h < 18:
                label_suffix = "午后开口期"
            else:
                label_suffix = "傍晚/夜钓期"

            windows.append({
                "start_hour": start_h,
                "end_hour": end_h,
                "avg_score": round(avg),
                "label": f"{start_h:02d}:00-{end_h:02d}:00 — {label_suffix}",
            })

        # 按均分降序，去重（避免重叠窗口）
        windows.sort(key=lambda x: x["avg_score"], reverse=True)

        # 简单去重：已选窗口的 start_hour 不能与之前选中的重叠
        selected = []
        used_hours = set()
        for w in windows:
            overlap = any(
                h in used_hours
                for h in range(w["start_hour"], w["end_hour"])
            )
            if not overlap:
                selected.append(w)
                for h in range(w["start_hour"], w["end_hour"]):
                    used_hours.add(h)
            if len(selected) >= top_n:
                break

        return selected

    def calc_daily_summary(
        self, hourly_data: List[dict], fish_profile: FishSpeciesProfile = None,
    ) -> dict:
        """今日整体鱼情汇总。

        Returns:
            {
                "overall_score": 65,
                "overall_rating": "good",          # excellent/good/fair/poor
                "rating_cn": "良好",
                "peak_hour": 7,                    # 最高分时段
                "peak_score": 82,
                "solunar_info": {...},
            }
        """
        scored = self.calc_hourly_scores(hourly_data, fish_profile)
        if not scored:
            return {
                "overall_score": 0,
                "overall_rating": "poor",
                "rating_cn": "无数据",
                "peak_hour": 0,
                "peak_score": 0,
                "solunar_info": {},
            }

        # 整体均分
        avg_score = sum(s["bite_index"] for s in scored) / len(scored)
        peak = max(scored, key=lambda x: x["bite_index"])

        # 评级
        if avg_score >= 75:
            rating, cn = "excellent", "极佳"
        elif avg_score >= 55:
            rating, cn = "good", "良好"
        elif avg_score >= 35:
            rating, cn = "fair", "一般"
        else:
            rating, cn = "poor", "较差"

        now_ts = int(_time.time())
        solunar = calc_solunar_rating(now_ts)

        return {
            "overall_score": round(avg_score),
            "overall_rating": rating,
            "rating_cn": cn,
            "peak_hour": peak["hour"],
            "peak_score": peak["bite_index"],
            "solunar_info": solunar,
        }

    def calc_daily_score_from_weather(
        self, day_data: dict, fish_profile: FishSpeciesProfile = None,
    ) -> dict:
        """对单日天气数据评分（用于 3 天日历）。

        使用白天均温 = (tempMax + tempMin) / 2 作为代表温度。

        Args:
            day_data: get_3day_forecast() 中的单日数据

        Returns:
            {"date": "...", "score": 72, "rating": "good", "rating_cn": "良好", ...}
        """
        profile = fish_profile or self.fish_profile
        service = FishingPredictionService(fish_profile=profile)

        avg_temp = (day_data.get("temp_max", 25) + day_data.get("temp_min", 15)) / 2

        api = ApiData(
            wind_speed=day_data.get("wind_speed", 0.0),
            altitude=0.0,
            weather_trend=day_data.get("weather_trend", "sunny"),
            wind_direction=day_data.get("wind_direction", ""),
            humidity=day_data.get("humidity", 50.0),
            original_text=day_data.get("text_day", "晴"),
            original_wind_dir="",
        )

        pred = service.predict_weather_only(api=api, air_temp=avg_temp)

        score = pred.bite_index
        if score >= 75:
            rating, cn = "excellent", "极佳"
        elif score >= 55:
            rating, cn = "good", "良好"
        elif score >= 35:
            rating, cn = "fair", "一般"
        else:
            rating, cn = "poor", "较差"

        return {
            "date": day_data.get("date", ""),
            "temp_max": day_data.get("temp_max"),
            "temp_min": day_data.get("temp_min"),
            "text_day": day_data.get("text_day", ""),
            "text_night": day_data.get("text_night", ""),
            "pressure": day_data.get("pressure", 1013),
            "humidity": day_data.get("humidity", 50),
            "wind_speed": day_data.get("wind_speed", 0),
            "score": score,
            "rating": rating,
            "rating_cn": cn,
            "tactical_advice": pred.tactical_advice,
        }

    def calc_3day_calendar(
        self, daily_data: List[dict], fish_profile: FishSpeciesProfile = None,
    ) -> dict:
        """生成未来 3 天鱼情日历。

        Args:
            daily_data: QWeatherService.get_3day_forecast() 返回值

        Returns:
            {
                "best_day": "2026-05-06",
                "best_day_score": 78,
                "days": [
                    {"date": "2026-05-05", "score": 65, "rating_cn": "良好", ...},
                    {"date": "2026-05-06", "score": 78, "rating_cn": "极佳", ...},
                    {"date": "2026-05-07", "score": 52, "rating_cn": "一般", ...},
                ],
                "comparison": "5月6日（周二）鱼情最佳，建议优先选择"
            }
        """
        profile = fish_profile or self.fish_profile

        if not daily_data:
            return {
                "best_day": "",
                "best_day_score": 0,
                "days": [],
                "comparison": "无天气预报数据",
            }

        days = []
        for d in daily_data:
            day_score = self.calc_daily_score_from_weather(d, profile)
            days.append(day_score)

        best = max(days, key=lambda x: x["score"])

        # 构建对比说明
        if len(days) >= 2:
            sorted_days = sorted(days, key=lambda x: x["score"], reverse=True)
            best_date = sorted_days[0]["date"]
            comparison = f"{best_date} 鱼情最佳（{sorted_days[0]['score']}分），建议优先选择"
            if len(sorted_days) >= 2 and sorted_days[1]["score"] >= 55:
                comparison += f"；{sorted_days[1]['date']} 也不错（{sorted_days[1]['score']}分）"
        else:
            comparison = ""

        return {
            "best_day": best["date"],
            "best_day_score": best["score"],
            "days": days,
            "comparison": comparison,
        }

