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

    # 本次出钓使用的装备快照 (V2 装备闭环)
    # 结构: {rods, mainLines, subLineHooks, floats, baits} - 与 user_inventory 一致
    equipment_used = Column(JSON, nullable=True, comment="本次出钓使用的装备快照")

    created_at = Column(DateTime(timezone=True), default=datetime.now, server_default=func.now())

class UserRod(Base):
    """
    用户保存在数字钓箱里的鱼竿
    """
    __tablename__ = "user_rods"

    id = Column(Integer, primary_key=True, index=True)
    openid = Column(String(64), index=True, nullable=False, comment="所属用户")
    
    brand = Column(String(32), nullable=False, comment="品牌，如 化氏")
    series = Column(String(64), nullable=False, comment="系列/型号，如 一味EX")
    length = Column(Float, nullable=False, comment="长度(米)")
    action = Column(String(32), nullable=True, comment="调性，如 28调")
    is_custom = Column(Integer, default=0, comment="是否是用户手填的")

    created_at = Column(DateTime(timezone=True), default=datetime.now, server_default=func.now())

class PublicRod(Base):
    """
    全球公共渔具品牌与型号库（支持大模型验证后自动收录，供所有人下拉选择）
    """
    __tablename__ = "public_rods"

    id = Column(Integer, primary_key=True, index=True)
    brand = Column(String(32), nullable=False, index=True, comment="品牌，如 化氏")
    series = Column(String(64), nullable=False, index=True, comment="系列/型号，如 一味EX")
    action = Column(String(32), nullable=True, comment="调性，如 28调")
    rod_type = Column(String(32), default="台钓竿", comment="鱼竿种类")
    length = Column(Float, nullable=False, comment="长度(米)")
    is_verified = Column(Integer, default=1, comment="是否审核通过可用 (1:已审核, 0:待审)")
    
    created_at = Column(DateTime(timezone=True), default=datetime.now, server_default=func.now())

class UserMainLine(Base):
    """
    用户保存在数字钓箱里的主线
    """
    __tablename__ = "user_mainlines"

    id = Column(Integer, primary_key=True, index=True)
    openid = Column(String(64), index=True, nullable=False, comment="所属用户")
    size = Column(Float, nullable=False, comment="线号 (如 2.0)")
    length = Column(Float, nullable=False, comment="长度/米数 (如 4.5)")

    created_at = Column(DateTime(timezone=True), default=datetime.now, server_default=func.now())

class UserSubLineHook(Base):
    """
    用户保存在数字钓箱里的子线双钩
    """
    __tablename__ = "user_subline_hooks"

    id = Column(Integer, primary_key=True, index=True)
    openid = Column(String(64), index=True, nullable=False, comment="所属用户")
    line_size = Column(Float, nullable=False, comment="子线线号 (如 0.8)")
    hook_type = Column(String(32), nullable=False, comment="钩型 (如 袖钩)")
    hook_size = Column(String(16), nullable=False, comment="钩号 (如 3号)")

    created_at = Column(DateTime(timezone=True), default=datetime.now, server_default=func.now())

class UserFloat(Base):
    """
    用户保存在数字钓箱里的浮漂
    """
    __tablename__ = "user_floats"

    id = Column(Integer, primary_key=True, index=True)
    openid = Column(String(64), index=True, nullable=False, comment="所属用户")
    
    lead = Column(Float, nullable=False, comment="吃铅量 (g)")
    material = Column(String(32), nullable=False, comment="材质 (如 芦苇)")
    shape = Column(String(32), nullable=False, comment="漂型 (如 枣核型)")
    tail_type = Column(String(32), nullable=False, comment="漂尾类型 (如 软尾)")
    name = Column(String(64), nullable=True, comment="自动生成的浮漂名称")

    created_at = Column(DateTime(timezone=True), default=datetime.now, server_default=func.now())

class UserBait(Base):
    """
    用户保存在数字钓箱里的饵料
    """
    __tablename__ = "user_baits"

    id = Column(Integer, primary_key=True, index=True)
    openid = Column(String(64), index=True, nullable=False, comment="所属用户")
    
    category = Column(String(32), nullable=False, comment="大类 (如 商品饵, 自然饵, 状态辅料, 小药)")
    brand = Column(String(32), nullable=False, comment="品牌 (如 老鬼, 龙王恨, 自定义)")
    name = Column(String(64), nullable=False, comment="名称 (如 野战蓝鲫, 蚯蚓)")
    flavor = Column(String(32), nullable=False, comment="味型 (如 腥香, 本味, 状态调整)")
    target_fish = Column(String(32), nullable=False, comment="目标鱼 (如 综合, 鲫鱼)")

    created_at = Column(DateTime(timezone=True), default=datetime.now, server_default=func.now())


class PublicBait(Base):
    """
    全球公共饵料品牌与型号库（供所有人下拉选择）
    """
    __tablename__ = "public_baits"

    id = Column(Integer, primary_key=True, index=True)
    category = Column(String(32), nullable=False, comment="大类 (如 商品饵, 自然饵, 状态辅料, 小药)")
    brand = Column(String(32), nullable=False, index=True, comment="品牌 (如 老鬼, 龙王恨)")
    name = Column(String(64), nullable=False, index=True, comment="名称 (如 野战蓝鲫, 蚯蚓)")
    flavor = Column(String(32), nullable=False, comment="味型 (如 腥香, 本味)")
    target_fish = Column(String(32), nullable=False, comment="目标鱼 (如 综合, 鲫鱼)")
    is_verified = Column(Integer, default=1, comment="是否审核通过 (1:已审核, 0:待审)")

    created_at = Column(DateTime(timezone=True), default=datetime.now, server_default=func.now())

