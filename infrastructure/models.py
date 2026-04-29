from sqlalchemy import Column, Integer, String, Float, DateTime, Text, JSON
from sqlalchemy.sql import func
from .database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    openid = Column(String(64), unique=True, index=True, nullable=False, comment="微信OpenID")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="注册时间")
    last_login = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="最后活跃时间")


class SensorRecord(Base):
    """
    用户上传的传感器历史数据
    """
    __tablename__ = "sensor_records"

    id = Column(Integer, primary_key=True, index=True)
    openid = Column(String(64), index=True, nullable=False, comment="所属用户")
    
    timestamp = Column(Integer, nullable=False, comment="Unix时间戳(秒)")
    t_bottom = Column(Float, nullable=True, comment="水底温度")
    t_mid = Column(Float, nullable=True, comment="中层温度")
    t_surface = Column(Float, nullable=True, comment="水面温度")
    p_local = Column(Float, nullable=True, comment="气压")
    
    # 冗余的经纬度，便于后续做区域性热力图
    lat = Column(Float, nullable=True, comment="纬度")
    lng = Column(Float, nullable=True, comment="经度")

    created_at = Column(DateTime(timezone=True), server_default=func.now())


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
    
    recommended_fish = Column(String(32), nullable=True, comment="最高推荐鱼种")
    bite_index = Column(Integer, nullable=True, comment="开口指数得分")
    
    # 存储当时的复杂状态，使用 JSON 格式
    weather_snapshot = Column(JSON, nullable=True, comment="当时的天气快照")
    tactical_advice = Column(JSON, nullable=True, comment="战术建议快照")
    tags = Column(JSON, nullable=True, comment="触发的标签快照")
    solunar_info = Column(JSON, nullable=True, comment="月相快照")

    created_at = Column(DateTime(timezone=True), server_default=func.now())
