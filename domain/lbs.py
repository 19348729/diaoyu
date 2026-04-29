import httpx
import logging

logger = logging.getLogger(__name__)

class TencentLBSService:
    """
    腾讯位置服务 (Tencent Location Based Services) API
    文档: https://lbs.qq.com/service/webService/webServiceGuide/webServiceGcoder
    """
    
    # 替换为您申请的真实 Key
    API_KEY = "72BBZ-NXCC7-IJ6XC-HSQ27-6ASH2-SGB7T"
    BASE_URL = "https://apis.map.qq.com/ws/geocoder/v1/"
    
    @classmethod
    async def reverse_geocode(cls, lat: float, lng: float) -> str:
        """
        逆地址解析：经纬度 -> 结构化地名
        优先返回著名的地标、水库、村镇或街道名称。
        """
        if lat == 0.0 and lng == 0.0:
            return "未知位置"
            
        params = {
            "location": f"{lat},{lng}",
            "key": cls.API_KEY,
            "get_poi": 1,  # 是否返回周边POI
        }
        
        headers = {
            "Referer": "https://ks.gzbaoge.com/"
        }
        
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(cls.BASE_URL, params=params, headers=headers, timeout=5.0)
                
            if resp.status_code != 200:
                logger.error(f"[LBS] HTTP {resp.status_code}")
                return "未知位置"
                
            data = resp.json()
            if data.get("status") != 0:
                logger.error(f"[LBS] API Error: {data.get('message')}")
                return "未知位置"
                
            result = data.get("result", {})
            address_component = result.get("address_component", {})
            formatted_addresses = result.get("formatted_addresses", {})
            
            # 优先使用推荐的简短地标地址（如“白云湖公园”）
            if "recommend" in formatted_addresses:
                return formatted_addresses["recommend"]
                
            # 退化使用基础地址
            address = result.get("address", "未知位置")
            return address
            
        except Exception as e:
            logger.error(f"[LBS] 逆地址解析异常: {e}")
            return "未知位置"
