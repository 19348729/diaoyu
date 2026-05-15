from sqlalchemy import Column, Integer, String, Float, DateTime, Text, JSON
from sqlalchemy.sql import func
from datetime import datetime
from .database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    openid = Column(String(64), unique=True, index=True, nullable=False, comment="微信OpenID")
    created_at = Column(DateTime(timezone=True), default=datetime.now, server_default=func.now(), comment="注册时间")
    last_login = Column(DateTime(timezone=True), default=datetime.now, onupdate=datetime.now, server_default=func.now(), comment="最后活跃时间")


class SensorRecord(Base):
    """
    用户上传的传感器历史数据
    """
    __tablename__ = "sensor_records"

    id = Column(Integer, primary_key=True, index=True)
    openid = Column(String(64), index=True, nullable=False, comment="所属用户")
    
    timestamp = Column(Integer, nullable=False, comment="Unix时间戳(秒)")
    t_water = Column(Float, nullable=True, comment="水温（DS18B20）")
    t_air = Column(Float, nullable=True, comment="气温（BMP280）")
    t_bottom = Column(Float, nullable=True, comment="[兼容] 水底温度")
    t_mid = Column(Float, nullable=True, comment="[兼容] 中层温度")
    t_surface = Column(Float, nullable=True, comment="[兼容] 水面温度")
    p_local = Column(Float, nullable=True, comment="本地气压 hPa")
    
    # 冗余的经纬度，便于后续做区域性热力图
    lat = Column(Float, nullable=True, comment="纬度")
    lng = Column(Float, nullable=True, comment="经度")
    location_name = Column(String(128), nullable=True, comment="解析后的钓点名称")

    created_at = Column(DateTime(timezone=True), default=datetime.now, server_default=func.now())


class PredictionHistory(Base):
    """
    预测历史日志
    记录每一次发起的预测，方便用户查阅“智能钓鱼日志”
    """
    __tablename__ = "prediction_history"

    id = Column(Integer, primary_key=True, index=True)
    openid = Column(String(64), index=True, nullable=False, comment="所属用户")
    
    lat = Column(Float, nullable=True, comment="请求发生纬度")
    lng = Column(Float, nullable=True, comment="请求发生经度")
    location_name = Column(String(128), nullable=True, comment="解析后的钓点名称")
    
    recommended_fish = Column(String(32), nullable=True, comment="最高推荐鱼种")
    bite_index = Column(Integer, nullable=True, comment="开口指数得分")
    
    # 存储当时的复杂状态，使用 JSON 格式
    weather_snapshot = Column(JSON, nullable=True, comment="当时的天气快照")
    tactical_advice = Column(JSON, nullable=True, comment="战术建议快照")
    tags = Column(JSON, nullable=True, comment="触发的标签快照")
    solunar_info = Column(JSON, nullable=True, comment="月相快照")

    created_at = Column(DateTime(timezone=True), default=datetime.now, server_default=func.now())


class FishingSession(Base):
    """
    钓鱼会话摘要（一次出钓 = 一条记录）
    由用户断开 ESP32 时确认保存，聚合整次作钓的传感器趋势和预测结果。
    """
    __tablename__ = "fishing_sessions"

    id = Column(Integer, primary_key=True, index=True)
    openid = Column(String(64), index=True, nullable=False, comment="所属用户")

    # 时间
    start_time = Column(Integer, nullable=False, comment="会话开始 Unix 时间戳")
    end_time = Column(Integer, nullable=False, comment="会话结束 Unix 时间戳")
    duration_min = Column(Integer, nullable=False, comment="作钓时长（分钟）")
    data_points = Column(Integer, default=0, comment="传感器数据点数量")

    # 位置
    lat = Column(Float, nullable=True, comment="钓点纬度")
    lng = Column(Float, nullable=True, comment="钓点经度")
    location_name = Column(String(128), nullable=True, comment="钓点名称")

    # 水温统计
    t_water_start = Column(Float, nullable=True, comment="水温起始值")
    t_water_end = Column(Float, nullable=True, comment="水温结束值")
    t_water_min = Column(Float, nullable=True, comment="水温最低值")
    t_water_max = Column(Float, nullable=True, comment="水温最高值")

    # 气温统计
    t_air_start = Column(Float, nullable=True, comment="气温起始值")
    t_air_end = Column(Float, nullable=True, comment="气温结束值")

    # 气压统计
    p_start = Column(Float, nullable=True, comment="气压起始值")
    p_end = Column(Float, nullable=True, comment="气压结束值")
    p_trend = Column(String(32), nullable=True, comment="气压趋势：持续上升/持续下降/先升后降/平稳")

    # 天气快照
    weather_text = Column(String(32), nullable=True, comment="天气描述（如：多云）")
    wind_desc = Column(String(64), nullable=True, comment="风况描述")

    # 预测汇总
    bite_index_max = Column(Integer, nullable=True, comment="开口指数最高值")
    bite_index_avg = Column(Integer, nullable=True, comment="开口指数平均值")
    recommended_fish = Column(String(32), nullable=True, comment="推荐鱼种（出现频率最高的）")

    created_at = Column(DateTime(timezone=True), default=datetime.now, server_default=func.now())
