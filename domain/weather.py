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
    """和风天气服务（实时天气）"""
    
    BASE_URL = "https://devapi.qweather.com/v7/weather/now"
    
    def __init__(self, api_key: Optional[str] = None):
        # 优先从传入参数获取，或者环境变量获取，最后直接使用您写入的 Key
        self.api_key = api_key or os.getenv("QWEATHER_API_KEY") or "50483fd7702045e3bd6557285c66c502"
        
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
                humidity=50.0
            )

        cache_key = self._get_cache_key(lat, lng)
        now = int(time.time())
        
        # 1. 查缓存
        if cache_key in _WEATHER_CACHE:
            cached_item = _WEATHER_CACHE[cache_key]
            if now < cached_item["expire_at"]:
                logger.debug(f"命中天气缓存: {cache_key}")
                # 海拔可能会变，更新缓存数据的海拔
                data = cached_item["data"]
                data.altitude = altitude
                return data
                
        # 2. 调用 API
        location_str = f"{round(lng, 3)},{round(lat, 3)}" # 和风要求 lon,lat
        params = {
            "location": location_str,
            "key": self.api_key
        }
        
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(self.BASE_URL, params=params)
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
                        humidity=humidity
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
            humidity=50.0
        )
