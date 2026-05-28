"""
和风天气服务模块 (QWeather Service)
==================================
对接和风天气 API，提供实时天气、逐小时预报和 3 天逐日预报。

内部实现内存缓存（5~60 分钟 TTL），减少重复调用；
将和风天气原始数据映射为系统内部的标准 ApiData 值对象，
供开口指数计算和鱼情预报服务消费。
"""

import time
import httpx
import logging
import os
from typing import Optional
from domain.value_objects import ApiData

logger = logging.getLogger(__name__)

# 全局内存缓存
# 结构: { "lon,lat": {"data": ApiData, "expire_at": int} }
_WEATHER_CACHE = {}
CACHE_TTL_SECONDS = 300  # 5 分钟缓存

class QWeatherService:
    """和风天气服务（实时天气 + 逐小时预报）"""
    
    BASE_DOMAIN = "https://kx4jac59km.re.qweatherapi.com"
    NOW_URL = f"{BASE_DOMAIN}/v7/weather/now"
    HOURLY_URL = f"{BASE_DOMAIN}/v7/weather/24h"
    DAILY_URL = f"{BASE_DOMAIN}/v7/weather/3d"
    
    def __init__(self, api_key: Optional[str] = None):
        # 优先从传入参数获取，其次从环境变量 QWEATHER_API_KEY 获取
        self.api_key = api_key or os.getenv("QWEATHER_API_KEY")
        
    def _get_cache_key(self, lat: float, lng: float) -> str:
        # 对经纬度保留2位小数作为缓存 key（约1公里精度，足以用于天气缓存）
        return f"{round(lng, 2)},{round(lat, 2)}"
        
    def _map_weather_text_to_trend(self, text: str) -> str:
        """将和风天气的天气描述映射为系统可识别的 weather_trend"""
        text = text.lower()
        if "晴" in text:
            return "sunny"
        elif "多云" in text or "阴" in text:
            if "多云" in text:
                return "cloudy"
            return "overcast"
        elif "暴雨" in text or "雷" in text or "大风" in text or "冰雹" in text:
            return "stormy"
        elif "雨" in text or "雪" in text:
            return "rainy"
        return "sunny"  # 默认兜底
        
    def _map_wind_dir_to_enum(self, wind_dir: str, wind_360: str = "") -> str:
        """映射风向到 N/NE/E/SE/S/SW/W/NW"""
        if "北" in wind_dir and "东" in wind_dir: return "NE"
        if "北" in wind_dir and "西" in wind_dir: return "NW"
        if "南" in wind_dir and "东" in wind_dir: return "SE"
        if "南" in wind_dir and "西" in wind_dir: return "SW"
        if "北" in wind_dir: return "N"
        if "南" in wind_dir: return "S"
        if "东" in wind_dir: return "E"
        if "西" in wind_dir: return "W"
        return ""

    async def get_realtime_weather(self, lat: float, lng: float, altitude: float = 0.0) -> ApiData:
        """获取实时天气，支持缓存"""
        if not self.api_key:
            logger.warning("未配置 QWEATHER_API_KEY，返回默认天气数据")
            return ApiData(
                wind_speed=0.0,
                altitude=altitude,
                weather_trend="sunny",
                wind_direction="",
                humidity=50.0,
                original_text="无",
                original_wind_dir="无"
            )

        cache_key = self._get_cache_key(lat, lng)
        now = int(time.time())
        
        import dataclasses
        # 1. 查缓存
        if cache_key in _WEATHER_CACHE:
            cached_item = _WEATHER_CACHE[cache_key]
            if now < cached_item["expire_at"]:
                logger.debug(f"命中天气缓存: {cache_key}")
                # 海拔可能会变，返回更新了海拔的新对象
                data = cached_item["data"]
                return dataclasses.replace(data, altitude=altitude)
                
        # 2. 调用 API
        location_str = f"{round(lng, 3)},{round(lat, 3)}" # 和风要求 lon,lat
        
        # 直接拼接 URL，防止 httpx 默认将逗号编码为 %2C 导致某些服务商 403
        url = f"{self.NOW_URL}?location={location_str}&key={self.api_key}"
        
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                res_data = response.json()
                
                if res_data.get("code") == "200":
                    now_data = res_data.get("now", {})
                    
                    wind_speed = float(now_data.get("windSpeed", 0)) * 1000 / 3600  # km/h 转 m/s
                    humidity = float(now_data.get("humidity", 0))
                    text = now_data.get("text", "晴")
                    wind_dir = now_data.get("windDir", "")
                    
                    weather_trend = self._map_weather_text_to_trend(text)
                    mapped_wind_dir = self._map_wind_dir_to_enum(wind_dir)
                    
                    api_data = ApiData(
                        wind_speed=round(wind_speed, 1),
                        altitude=altitude,
                        weather_trend=weather_trend,
                        wind_direction=mapped_wind_dir,
                        humidity=humidity,
                        original_text=text,
                        original_wind_dir=wind_dir
                    )
                    
                    # 写入缓存
                    _WEATHER_CACHE[cache_key] = {
                        "data": api_data,
                        "expire_at": now + CACHE_TTL_SECONDS
                    }
                    
                    logger.info(f"成功获取和风天气: {location_str} -> {text}, 风速: {wind_speed:.1f}m/s")
                    return api_data
                else:
                    logger.error(f"和风天气API返回错误码: {res_data.get('code')}")
        except Exception as e:
            logger.error(f"请求和风天气异常: {e}")
            
        # 兜底返回
        return ApiData(
            wind_speed=0.0,
            altitude=altitude,
            weather_trend="sunny",
            wind_direction="",
            humidity=50.0,
            original_text="晴(兜底)",
            original_wind_dir="无持续风向"
        )

    async def get_hourly_forecast(self, lat: float, lng: float) -> list:
        """获取未来 24 小时逐小时天气预报。

        Returns:
            [
                {
                    "fxTime": "2026-05-05T10:00+08:00",
                    "hour": 10,
                    "temp": 28.0,          # 气温 ℃
                    "humidity": 75.0,       # 湿度 %
                    "wind_speed": 2.5,      # 风速 m/s
                    "wind_direction": "SW", # 风向
                    "weather_trend": "sunny",
                    "weather_text": "晴",
                    "pressure": 1012.0,     # 气压 hPa
                },
                ...
            ]
        """
        if not self.api_key:
            logger.warning("未配置 API Key，返回空预报")
            return []

        cache_key = self._get_cache_key(lat, lng) + ":forecast"
        now = int(time.time())

        # 查缓存（预报数据缓存 30 分钟）
        if cache_key in _WEATHER_CACHE:
            cached = _WEATHER_CACHE[cache_key]
            if now < cached["expire_at"]:
                logger.debug(f"命中预报缓存: {cache_key}")
                return cached["data"]

        location_str = f"{round(lng, 3)},{round(lat, 3)}"
        url = f"{self.HOURLY_URL}?location={location_str}&key={self.api_key}"

        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                res_data = response.json()

                if res_data.get("code") == "200":
                    hourly_raw = res_data.get("hourly", [])
                    result = []
                    for h in hourly_raw:
                        fx_time = h.get("fxTime", "")
                        # 提取小时数
                        hour = 0
                        if "T" in fx_time:
                            try:
                                hour = int(fx_time.split("T")[1][:2])
                            except (ValueError, IndexError):
                                pass

                        ws_kmh = float(h.get("windSpeed", 0))
                        wind_dir_text = h.get("windDir", "")

                        result.append({
                            "fxTime": fx_time,
                            "hour": hour,
                            "temp": float(h.get("temp", 20)),
                            "humidity": float(h.get("humidity", 50)),
                            "wind_speed": round(ws_kmh * 1000 / 3600, 1),
                            "wind_direction": self._map_wind_dir_to_enum(wind_dir_text),
                            "weather_trend": self._map_weather_text_to_trend(
                                h.get("text", "晴")
                            ),
                            "weather_text": h.get("text", "晴"),
                            "pressure": float(h.get("pressure", 1013)),
                        })

                    # 写入缓存（30 分钟）
                    _WEATHER_CACHE[cache_key] = {
                        "data": result,
                        "expire_at": now + 1800,
                    }
                    logger.info(f"成功获取24h预报: {location_str}, {len(result)} 条")
                    return result
                else:
                    logger.error(f"预报API错误码: {res_data.get('code')}")
        except Exception as e:
            logger.error(f"请求逐小时预报异常: {e}")

        return []

    async def get_3day_forecast(self, lat: float, lng: float) -> list:
        """获取未来 3 天逐日天气预报。

        Returns:
            [
                {
                    "date": "2026-05-06",
                    "temp_max": 32.0,
                    "temp_min": 23.0,
                    "text_day": "晴",
                    "text_night": "多云",
                    "weather_trend": "sunny",
                    "humidity": 70.0,
                    "pressure": 1010.0,
                    "wind_speed": 2.5,
                    "wind_direction": "SW",
                },
                ...
            ]
        """
        if not self.api_key:
            logger.warning("未配置 API Key，返回空3天预报")
            return []

        cache_key = self._get_cache_key(lat, lng) + ":3day"
        now = int(time.time())

        # 查缓存（3天预报缓存 1 小时）
        if cache_key in _WEATHER_CACHE:
            cached = _WEATHER_CACHE[cache_key]
            if now < cached["expire_at"]:
                logger.debug(f"命中3天预报缓存: {cache_key}")
                return cached["data"]

        location_str = f"{round(lng, 3)},{round(lat, 3)}"
        url = f"{self.DAILY_URL}?location={location_str}&key={self.api_key}"

        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                res_data = response.json()

                if res_data.get("code") == "200":
                    daily_raw = res_data.get("daily", [])
                    result = []
                    for d in daily_raw:
                        ws_kmh = float(d.get("windSpeedDay", 0))
                        wind_dir_text = d.get("windDirDay", "")

                        result.append({
                            "date": d.get("fxDate", ""),
                            "temp_max": float(d.get("tempMax", 30)),
                            "temp_min": float(d.get("tempMin", 20)),
                            "text_day": d.get("textDay", "晴"),
                            "text_night": d.get("textNight", "晴"),
                            "weather_trend": self._map_weather_text_to_trend(
                                d.get("textDay", "晴")
                            ),
                            "humidity": float(d.get("humidity", 50)),
                            "pressure": float(d.get("pressure", 1013)),
                            "wind_speed": round(ws_kmh * 1000 / 3600, 1),
                            "wind_direction": self._map_wind_dir_to_enum(wind_dir_text),
                        })

                    # 写入缓存（1 小时）
                    _WEATHER_CACHE[cache_key] = {
                        "data": result,
                        "expire_at": now + 3600,
                    }
                    logger.info(f"成功获取3天预报: {location_str}, {len(result)} 天")
                    return result
                else:
                    logger.error(f"3天预报API错误码: {res_data.get('code')}")
        except Exception as e:
            logger.error(f"请求3天预报异常: {e}")

        return []
