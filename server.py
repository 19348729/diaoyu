"""
FastAPI 应用入口 — AI 钓鱼预测 API 服务
======================================
启动方式:
  开发: python server.py
  生产: gunicorn server:app -c gunicorn.conf.py
"""
import os
import time
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException, Depends, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
import uuid

from domain.value_objects import (
    ApiData, SensorReading, SensorTimeSeries,
)
from domain.services import FishingPredictionService
from domain.constants import FISH_PROFILES
from domain.weather import QWeatherService
from domain.lbs import TencentLBSService
from domain.forecast import FishingForecastService
from domain.engine import FishingEngine
from domain.prescription import PrescriptionService
from domain.poster import PosterGenerator
from domain.master_kb import MasterKBRetriever
from domain.verification import RodVerificationService
from infrastructure.database import engine, Base, get_db
from infrastructure.models import User, SensorRecord, PredictionHistory, FishingSession, UserRod, PublicRod, UserMainLine, UserSubLineHook, UserFloat, UserBait, PublicBait, CatchLog

# 启动时自动建表（生产环境建议使用 Alembic 迁移工具）
Base.metadata.create_all(bind=engine)


# ── FastAPI 实例 ──────────────────────────────
app = FastAPI(
    title="AI 钓鱼预测 API",
    version="1.0.0",
    description="多因子融合钓鱼预测引擎 REST API  —  ks.gzbaoge.com",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS（允许小程序跨域） ───────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ══════════════════════════════════════════════
#  请求 / 响应模型 (Pydantic)
# ══════════════════════════════════════════════

class SensorDataIn(BaseModel):
    """单条传感器数据（来自小程序上报）"""
    timestamp: int = Field(..., description="Unix 时间戳（秒）")
    # v2 新字段
    t_water: Optional[float] = Field(None, description="水温 ℃")
    t_air: Optional[float] = Field(None, description="气温 ℃")
    p_local: Optional[float] = Field(None, description="本地气压 hPa")
    # v1 兼容字段（保留，旧版小程序仍可用）
    t_bottom: Optional[float] = Field(None, description="[兼容] 水底温度 ℃")
    t_mid: Optional[float] = Field(None, description="[兼容] 水下1米温度 ℃")
    t_surface: Optional[float] = Field(None, description="[兼容] 水面温度 ℃")


class PredictRequest(BaseModel):
    """预测请求"""
    fish_type: str = Field("auto", description="目标鱼种名称，传 'auto' 则全鱼种测算并推荐")
    sensors: List[SensorDataIn] = Field(..., description="传感器时序数据（按时间升序）", min_length=1)
    lat: float = Field(0.0, description="纬度")
    lng: float = Field(0.0, description="经度")
    altitude: float = Field(0.0, ge=0, description="海拔 米")
    user_inventory: Optional[Dict] = Field(None, description="用户装备库数据")
    spot_context: Optional[Dict] = Field(None, description="钓点情况 {type,density,clarity}（仅影响建议，不改开口指数）")


class PredictResponse(BaseModel):
    """预测响应"""
    recommended_fish: str = Field(..., description="系统推荐的最佳作钓鱼种")
    recommended_fishes: List[Dict] = Field(default_factory=list, description="全鱼种得分排行榜")
    bite_index: int = Field(..., description="开口评分 0-100")
    do_trend: float = Field(..., description="虚拟溶解氧 mg/L")
    report_stage: str = Field(..., description="报告阶段: instant/brief/standard/full")
    confidence: int = Field(..., description="置信度 0-100")
    tactical_tags: List[str] = Field(default_factory=list, description="战术标签列表")
    time_period_advice: Optional[str] = Field(None, description="时段建议")
    season_note: Optional[str] = Field(None, description="季节备注")
    weather_info: Optional[Dict] = Field(default=None, description="实时天气数据汇总")
    solunar_info: Dict = Field(default_factory=dict, description="月相信息")
    tactical_advice: Dict = Field(default_factory=dict, description="结构化战术建议")
    master_tips: List[Dict] = Field(default_factory=list, description="大师知识库匹配的 Top-K 战术秘籍")


class RealtimeSensorRequest(BaseModel):
    """实时数据上报（单条）"""
    sensor: SensorDataIn
    lat: float = 0.0
    lng: float = 0.0
    altitude: float = 0.0


class BatchSensorRequest(BaseModel):
    """批量历史数据上报"""
    records: List[SensorDataIn] = Field(..., min_length=1)
    lat: float = 0.0
    lng: float = 0.0


class RescueRequest(BaseModel):
    """V2 AI 鱼情救场请求"""
    sensors: List[SensorDataIn] = Field(..., description="传感器时序数据（按时间升序）")
    symptom_tags: List[str] = Field(default_factory=list, description="用户勾选的主观症状标签")
    fish_context: Dict = Field(default_factory=dict, description="目标鱼种、钓法、饵料等上下文")
    user_inventory: Optional[Dict] = Field(None, description="用户装备库数据")
    lat: float = 0.0
    lng: float = 0.0


class CatchLogRequest(BaseModel):
    """渔获记录请求（Phase 2 反馈闭环，仅记录、不参与预测）"""
    fish_species: Optional[str] = Field(None, description="主要鱼种")
    catch_count: int = Field(0, ge=0, description="渔获数量（0=空军）")
    total_weight: Optional[float] = Field(None, ge=0, description="大致总重（斤，选填）")
    note: Optional[str] = Field(None, description="备注")
    # 钓点情况（来自出钓上下文）
    spot_type: Optional[str] = None
    spot_density: Optional[str] = None
    water_clarity: Optional[str] = None
    # 位置
    lat: Optional[float] = None
    lng: Optional[float] = None
    # 校准锚点：记录时的预测/环境快照
    target_fish: Optional[str] = None
    bite_index: Optional[int] = None
    t_water: Optional[float] = None
    p_local: Optional[float] = None
    weather_text: Optional[str] = None

# ══════════════════════════════════════════════
#  API 路由
# ══════════════════════════════════════════════

@app.get("/health", tags=["系统"])
async def health_check():
    """健康检查接口（供 Nginx / 监控使用）"""
    return {
        "status": "ok",
        "timestamp": int(time.time()),
        "version": "1.0.0",
    }


@app.get("/api/fish-types", tags=["配置"])
async def list_fish_types():
    """获取支持的鱼种列表"""
    return {
        "fish_types": [
            {"name": name, "water_layer": profile.water_layer}
            for name, profile in FISH_PROFILES.items()
        ]
    }

@app.get("/api/inventory/rods", tags=["配置"])
async def list_rod_database(db: Session = Depends(get_db)):
    """获取官方与用户众包自动收录的鱼竿品牌与系列库"""
    db_rods = db.query(PublicRod).filter(PublicRod.is_verified == 1).all()

    # 聚合成前端多级级联结构
    brands_map = {}
    for rod in db_rods:
        if rod.brand not in brands_map:
            brands_map[rod.brand] = {}
            
        if rod.series not in brands_map[rod.brand]:
            brands_map[rod.brand][rod.series] = {
                "action": rod.action or "综合调",
                "lengths": set()
            }
        brands_map[rod.brand][rod.series]["lengths"].add(rod.length)
        
    # 组装最终 JSON 格式
    result = []
    for brand, series_map in brands_map.items():
        series_list = []
        for series_name, series_info in series_map.items():
            sorted_lengths = sorted(list(series_info["lengths"]))
            series_list.append({
                "series": series_name,
                "action": series_info["action"],
                "lengths": sorted_lengths
            })
        result.append({
            "brand": brand,
            "seriesList": series_list
        })
        
    return {"status": "ok", "data": result}


class AddRodRequest(BaseModel):
    brand: str
    series: str
    length: float
    action: Optional[str] = None
    is_custom: bool = False

@app.post("/api/inventory/rod", tags=["配置"])
async def add_user_rod(
    req: AddRodRequest,
    x_openid: Optional[str] = Header(None, alias="X-OpenID"),
    db: Session = Depends(get_db)
):
    """用户录入新的鱼竿到私有钓箱"""
    # For testing, we can use a mock openid if missing
    openid = _require_openid(x_openid)
    
    # UGC 自定义录入进行大模型验证
    if req.is_custom:
        verifier = RodVerificationService()
        check_res = verifier.verify_brand_and_series(req.brand, req.series)
        if not check_res.get("exists", True):
            return {
                "status": "error",
                "message": f"校验未通过：{check_res.get('reason')}"
            }
        
        # 验证成功后，自动同步收录到公共品牌库表(PublicRod)中，支持全球众包，供后续任何人下拉选择！
        existing = db.query(PublicRod).filter(
            PublicRod.brand == req.brand,
            PublicRod.series == req.series,
            PublicRod.length == req.length
        ).first()
        if not existing:
            new_public = PublicRod(
                brand=req.brand,
                series=req.series,
                action=req.action or "综合调",
                length=req.length,
                is_verified=1
            )
            db.add(new_public)
        
    user_rod = UserRod(
        openid=openid,
        brand=req.brand,
        series=req.series,
        length=req.length,
        action=req.action,
        is_custom=1 if req.is_custom else 0
    )
    db.add(user_rod)
    db.commit()
    return {"status": "ok", "message": "鱼竿录入成功", "id": user_rod.id}

@app.get("/api/inventory/rod/{rod_id}", tags=["配置"])
async def get_user_rod(
    rod_id: int,
    x_openid: Optional[str] = Header(None, alias="X-OpenID"),
    db: Session = Depends(get_db)
):
    """获取单根鱼竿详情"""
    openid = _require_openid(x_openid)
    
    user_rod = db.query(UserRod).filter(UserRod.id == rod_id, UserRod.openid == openid).first()
    if not user_rod:
        raise HTTPException(status_code=404, detail="未找到该鱼竿记录或无权访问")
        
    return {
        "status": "ok",
        "data": {
            "id": f"r{user_rod.id}",
            "brand": user_rod.brand,
            "series": user_rod.series,
            "length": user_rod.length,
            "action": user_rod.action or "未知",
            "is_custom": bool(user_rod.is_custom)
        }
    }

@app.put("/api/inventory/rod/{rod_id}", tags=["配置"])
async def update_user_rod(
    rod_id: int,
    req: AddRodRequest,
    x_openid: Optional[str] = Header(None, alias="X-OpenID"),
    db: Session = Depends(get_db)
):
    """修改用户私有钓箱中的鱼竿"""
    openid = _require_openid(x_openid)
    
    user_rod = db.query(UserRod).filter(UserRod.id == rod_id, UserRod.openid == openid).first()
    if not user_rod:
        raise HTTPException(status_code=404, detail="未找到该鱼竿记录或无权访问")
        
    # UGC 自定义录入进行大模型验证
    if req.is_custom:
        verifier = RodVerificationService()
        check_res = verifier.verify_brand_and_series(req.brand, req.series)
        if not check_res.get("exists", True):
            return {
                "status": "error",
                "message": f"校验未通过：{check_res.get('reason')}"
            }
            
        # 验证成功后，自动同步收录到公共品牌库表(PublicRod)中，支持全球众包，供后续任何人下拉选择！
        existing = db.query(PublicRod).filter(
            PublicRod.brand == req.brand,
            PublicRod.series == req.series,
            PublicRod.length == req.length
        ).first()
        if not existing:
            new_public = PublicRod(
                brand=req.brand,
                series=req.series,
                action=req.action or "综合调",
                length=req.length,
                is_verified=1
            )
            db.add(new_public)
            
    user_rod.brand = req.brand
    user_rod.series = req.series
    user_rod.length = req.length
    user_rod.action = req.action
    user_rod.is_custom = 1 if req.is_custom else 0
    
    db.commit()
    return {"status": "ok", "message": "鱼竿修改成功"}

@app.delete("/api/inventory/rod/{rod_id}", tags=["配置"])
async def delete_user_rod(
    rod_id: int,
    x_openid: Optional[str] = Header(None, alias="X-OpenID"),
    db: Session = Depends(get_db)
):
    """从用户私有钓箱中删除鱼竿"""
    openid = _require_openid(x_openid)
    
    user_rod = db.query(UserRod).filter(UserRod.id == rod_id, UserRod.openid == openid).first()
    if not user_rod:
        raise HTTPException(status_code=404, detail="未找到该鱼竿记录或无权访问")
        
    db.delete(user_rod)
    db.commit()
    return {"status": "ok", "message": "鱼竿删除成功"}

@app.get("/api/inventory/rods/user", tags=["配置"])
async def list_user_rods(
    x_openid: Optional[str] = Header(None, alias="X-OpenID"),
    db: Session = Depends(get_db)
):
    """获取用户钓箱里现有的所有鱼竿"""
    openid = _require_openid(x_openid)
        
    rods = db.query(UserRod).filter(UserRod.openid == openid).all()
    result = []
    for r in rods:
        result.append({
            "id": f"r{r.id}",
            "brand": r.brand,
            "name": r.series,
            "length": r.length,
            "action": r.action or "未知",
            "type": "台钓竿" # 默认均为台钓竿
        })
    return {"status": "ok", "data": result}


# ──────────────────────────────────────────────
#  主线 CRUD 接口列表
# ──────────────────────────────────────────────
class MainLineRequest(BaseModel):
    size: float
    length: float

@app.post("/api/inventory/mainline", tags=["主线"])
async def add_user_mainline(
    req: MainLineRequest,
    x_openid: Optional[str] = Header(None, alias="X-OpenID"),
    db: Session = Depends(get_db)
):
    """用户录入新的主线到私有钓箱"""
    openid = _require_openid(x_openid)
    
    user_line = UserMainLine(
        openid=openid,
        size=req.size,
        length=req.length
    )
    db.add(user_line)
    db.commit()
    return {"status": "ok", "message": "主线录入成功", "id": user_line.id}

@app.get("/api/inventory/mainline/{line_id}", tags=["主线"])
async def get_user_mainline(
    line_id: int,
    x_openid: Optional[str] = Header(None, alias="X-OpenID"),
    db: Session = Depends(get_db)
):
    """获取用户钓箱中单条主线的详情"""
    openid = _require_openid(x_openid)
    
    user_line = db.query(UserMainLine).filter(UserMainLine.id == line_id, UserMainLine.openid == openid).first()
    if not user_line:
        raise HTTPException(status_code=404, detail="未找到该主线记录")
        
    return {
        "status": "ok",
        "data": {
            "id": f"m{user_line.id}",
            "size": user_line.size,
            "length": user_line.length
        }
    }

@app.put("/api/inventory/mainline/{line_id}", tags=["主线"])
async def update_user_mainline(
    line_id: int,
    req: MainLineRequest,
    x_openid: Optional[str] = Header(None, alias="X-OpenID"),
    db: Session = Depends(get_db)
):
    """修改用户私有钓箱中的主线"""
    openid = _require_openid(x_openid)
    
    user_line = db.query(UserMainLine).filter(UserMainLine.id == line_id, UserMainLine.openid == openid).first()
    if not user_line:
        raise HTTPException(status_code=404, detail="未找到该主线记录")
        
    user_line.size = req.size
    user_line.length = req.length
    db.commit()
    return {"status": "ok", "message": "主线修改成功"}

@app.delete("/api/inventory/mainline/{line_id}", tags=["主线"])
async def delete_user_mainline(
    line_id: int,
    x_openid: Optional[str] = Header(None, alias="X-OpenID"),
    db: Session = Depends(get_db)
):
    """从用户私有钓箱中删除主线"""
    openid = _require_openid(x_openid)
    
    user_line = db.query(UserMainLine).filter(UserMainLine.id == line_id, UserMainLine.openid == openid).first()
    if not user_line:
        raise HTTPException(status_code=404, detail="未找到该主线记录")
        
    db.delete(user_line)
    db.commit()
    return {"status": "ok", "message": "主线删除成功"}

@app.get("/api/inventory/mainlines/user", tags=["主线"])
async def list_user_mainlines(
    x_openid: Optional[str] = Header(None, alias="X-OpenID"),
    db: Session = Depends(get_db)
):
    """获取用户钓箱里现有的所有主线"""
    openid = _require_openid(x_openid)
        
    mainlines = db.query(UserMainLine).filter(UserMainLine.openid == openid).all()
    result = []
    for m in mainlines:
        result.append({
            "id": f"m{m.id}",
            "size": m.size,
            "length": m.length
        })
    return {"status": "ok", "data": result}


# ──────────────────────────────────────────────
#  子线双钩 CRUD 接口列表
# ──────────────────────────────────────────────
class SubLineHookRequest(BaseModel):
    line_size: float
    hook_type: str
    hook_size: str

@app.post("/api/inventory/sublinehook", tags=["子线双钩"])
async def add_user_sublinehook(
    req: SubLineHookRequest,
    x_openid: Optional[str] = Header(None, alias="X-OpenID"),
    db: Session = Depends(get_db)
):
    """用户录入新的子线双钩到私有钓箱"""
    openid = _require_openid(x_openid)
    
    user_sub = UserSubLineHook(
        openid=openid,
        line_size=req.line_size,
        hook_type=req.hook_type,
        hook_size=req.hook_size
    )
    db.add(user_sub)
    db.commit()
    return {"status": "ok", "message": "子线双钩录入成功", "id": user_sub.id}

@app.get("/api/inventory/sublinehook/{subline_id}", tags=["子线双钩"])
async def get_user_sublinehook(
    subline_id: int,
    x_openid: Optional[str] = Header(None, alias="X-OpenID"),
    db: Session = Depends(get_db)
):
    """获取用户钓箱中单条子线双钩的详情"""
    openid = _require_openid(x_openid)
    
    user_sub = db.query(UserSubLineHook).filter(UserSubLineHook.id == subline_id, UserSubLineHook.openid == openid).first()
    if not user_sub:
        raise HTTPException(status_code=404, detail="未找到该子线双钩记录")
        
    return {
        "status": "ok",
        "data": {
            "id": f"s{user_sub.id}",
            "lineSize": user_sub.line_size,
            "hookType": user_sub.hook_type,
            "hookSize": user_sub.hook_size
        }
    }

@app.put("/api/inventory/sublinehook/{subline_id}", tags=["子线双钩"])
async def update_user_sublinehook(
    subline_id: int,
    req: SubLineHookRequest,
    x_openid: Optional[str] = Header(None, alias="X-OpenID"),
    db: Session = Depends(get_db)
):
    """修改用户私有钓箱中的子线双钩"""
    openid = _require_openid(x_openid)
    
    user_sub = db.query(UserSubLineHook).filter(UserSubLineHook.id == subline_id, UserSubLineHook.openid == openid).first()
    if not user_sub:
        raise HTTPException(status_code=404, detail="未找到该子线双钩记录")
        
    user_sub.line_size = req.line_size
    user_sub.hook_type = req.hook_type
    user_sub.hook_size = req.hook_size
    db.commit()
    return {"status": "ok", "message": "子线双钩修改成功"}

@app.delete("/api/inventory/sublinehook/{subline_id}", tags=["子线双钩"])
async def delete_user_sublinehook(
    subline_id: int,
    x_openid: Optional[str] = Header(None, alias="X-OpenID"),
    db: Session = Depends(get_db)
):
    """从用户私有钓箱中删除子线双钩"""
    openid = _require_openid(x_openid)
    
    user_sub = db.query(UserSubLineHook).filter(UserSubLineHook.id == subline_id, UserSubLineHook.openid == openid).first()
    if not user_sub:
        raise HTTPException(status_code=404, detail="未找到该子线双钩记录")
        
    db.delete(user_sub)
    db.commit()
    return {"status": "ok", "message": "子线双钩删除成功"}

@app.get("/api/inventory/sublinehooks/user", tags=["子线双钩"])
async def list_user_sublinehooks(
    x_openid: Optional[str] = Header(None, alias="X-OpenID"),
    db: Session = Depends(get_db)
):
    """获取用户钓箱里现有的所有子线双钩"""
    openid = _require_openid(x_openid)
        
    sublines = db.query(UserSubLineHook).filter(UserSubLineHook.openid == openid).all()
    result = []
    for s in sublines:
        result.append({
            "id": f"s{s.id}",
            "lineSize": s.line_size,
            "hookType": s.hook_type,
            "hookSize": s.hook_size
        })
    return {"status": "ok", "data": result}


# ──────────────────────────────────────────────
#  浮漂 CRUD 接口列表
# ──────────────────────────────────────────────
class FloatRequest(BaseModel):
    lead: float
    material: str
    shape: str
    tail_type: str

@app.post("/api/inventory/float", tags=["浮漂"])
async def add_user_float(
    req: FloatRequest,
    x_openid: Optional[str] = Header(None, alias="X-OpenID"),
    db: Session = Depends(get_db)
):
    """用户录入新的浮漂到私有钓箱"""
    openid = _require_openid(x_openid)
    
    generated_name = f"{req.material} {req.shape} {req.tail_type}漂"
    user_float = UserFloat(
        openid=openid,
        lead=req.lead,
        material=req.material,
        shape=req.shape,
        tail_type=req.tail_type,
        name=generated_name
    )
    db.add(user_float)
    db.commit()
    return {"status": "ok", "message": "浮漂录入成功", "id": user_float.id}

@app.get("/api/inventory/float/{float_id}", tags=["浮漂"])
async def get_user_float(
    float_id: int,
    x_openid: Optional[str] = Header(None, alias="X-OpenID"),
    db: Session = Depends(get_db)
):
    """获取用户钓箱中单条浮漂的详情"""
    openid = _require_openid(x_openid)
    
    user_float = db.query(UserFloat).filter(UserFloat.id == float_id, UserFloat.openid == openid).first()
    if not user_float:
        raise HTTPException(status_code=404, detail="未找到该浮漂记录")
        
    return {
        "status": "ok",
        "data": {
            "id": f"f{user_float.id}",
            "lead": user_float.lead,
            "material": user_float.material,
            "shape": user_float.shape,
            "tail_type": user_float.tail_type,
            "name": user_float.name
        }
    }

@app.put("/api/inventory/float/{float_id}", tags=["浮漂"])
async def update_user_float(
    float_id: int,
    req: FloatRequest,
    x_openid: Optional[str] = Header(None, alias="X-OpenID"),
    db: Session = Depends(get_db)
):
    """修改用户私有钓箱中的浮漂"""
    openid = _require_openid(x_openid)
    
    user_float = db.query(UserFloat).filter(UserFloat.id == float_id, UserFloat.openid == openid).first()
    if not user_float:
        raise HTTPException(status_code=404, detail="未找到该浮漂记录")
        
    generated_name = f"{req.material} {req.shape} {req.tail_type}漂"
    user_float.lead = req.lead
    user_float.material = req.material
    user_float.shape = req.shape
    user_float.tail_type = req.tail_type
    user_float.name = generated_name
    db.commit()
    return {"status": "ok", "message": "浮漂修改成功"}

@app.delete("/api/inventory/float/{float_id}", tags=["浮漂"])
async def delete_user_float(
    float_id: int,
    x_openid: Optional[str] = Header(None, alias="X-OpenID"),
    db: Session = Depends(get_db)
):
    """从用户私有钓箱中删除浮漂"""
    openid = _require_openid(x_openid)
    
    user_float = db.query(UserFloat).filter(UserFloat.id == float_id, UserFloat.openid == openid).first()
    if not user_float:
        raise HTTPException(status_code=404, detail="未找到该浮漂记录")
        
    db.delete(user_float)
    db.commit()
    return {"status": "ok", "message": "浮漂删除成功"}

@app.get("/api/inventory/floats/user", tags=["浮漂"])
async def list_user_floats(
    x_openid: Optional[str] = Header(None, alias="X-OpenID"),
    db: Session = Depends(get_db)
):
    """获取用户钓箱里现有的所有浮漂"""
    openid = _require_openid(x_openid)
        
    floats = db.query(UserFloat).filter(UserFloat.openid == openid).all()
    result = []
    for f in floats:
        result.append({
            "id": f"f{f.id}",
            "name": f.name or f"{f.material} {f.shape}漂",
            "material": f.material,
            "shape": f.shape,
            "lead": f.lead,
            "tail_type": f.tail_type
        })
    return {"status": "ok", "data": result}


# ──────────────────────────────────────────────
#  饵料 CRUD 接口列表
# ──────────────────────────────────────────────
class BaitRequest(BaseModel):
    category: str
    brand: str
    name: str
    flavor: str
    target_fish: str

@app.post("/api/inventory/bait", tags=["饵料"])
async def add_user_bait(
    req: BaitRequest,
    x_openid: Optional[str] = Header(None, alias="X-OpenID"),
    db: Session = Depends(get_db)
):
    """用户录入新的饵料到私有钓箱"""
    openid = _require_openid(x_openid)
    
    user_bait = UserBait(
        openid=openid,
        category=req.category,
        brand=req.brand,
        name=req.name,
        flavor=req.flavor,
        target_fish=req.target_fish
    )
    db.add(user_bait)
    db.commit()
    return {"status": "ok", "message": "饵料录入成功", "id": user_bait.id}

@app.post("/api/inventory/bait/old-three", tags=["饵料"])
async def add_old_three_bait(
    x_openid: Optional[str] = Header(None, alias="X-OpenID"),
    db: Session = Depends(get_db)
):
    """一键添加老三样 (野战蓝鲫 + 九一八 + 速攻)"""
    openid = _require_openid(x_openid)
    
    baits_to_add = [
        UserBait(openid=openid, category="商品饵", brand="龙王恨", name="野战蓝鲫", flavor="腥香", target_fish="综合"),
        UserBait(openid=openid, category="商品饵", brand="老鬼", name="九一八野战篇", flavor="麸香", target_fish="综合"),
        UserBait(openid=openid, category="状态辅料", brand="老鬼", name="速攻2号", flavor="状态", target_fish="综合")
    ]
    
    db.add_all(baits_to_add)
    db.commit()
    return {"status": "ok", "message": "老三样添加成功"}

@app.get("/api/inventory/bait/{bait_id}", tags=["饵料"])
async def get_user_bait(
    bait_id: int,
    x_openid: Optional[str] = Header(None, alias="X-OpenID"),
    db: Session = Depends(get_db)
):
    """获取用户钓箱中单款饵料的详情"""
    openid = _require_openid(x_openid)
    
    user_bait = db.query(UserBait).filter(UserBait.id == bait_id, UserBait.openid == openid).first()
    if not user_bait:
        raise HTTPException(status_code=404, detail="未找到该饵料记录")
        
    return {
        "status": "ok",
        "data": {
            "id": f"b{user_bait.id}",
            "category": user_bait.category,
            "brand": user_bait.brand,
            "name": user_bait.name,
            "flavor": user_bait.flavor,
            "targetFish": user_bait.target_fish
        }
    }

@app.put("/api/inventory/bait/{bait_id}", tags=["饵料"])
async def update_user_bait(
    bait_id: int,
    req: BaitRequest,
    x_openid: Optional[str] = Header(None, alias="X-OpenID"),
    db: Session = Depends(get_db)
):
    """修改用户私有钓箱中的饵料"""
    openid = _require_openid(x_openid)
    
    user_bait = db.query(UserBait).filter(UserBait.id == bait_id, UserBait.openid == openid).first()
    if not user_bait:
        raise HTTPException(status_code=404, detail="未找到该饵料记录")
        
    user_bait.category = req.category
    user_bait.brand = req.brand
    user_bait.name = req.name
    user_bait.flavor = req.flavor
    user_bait.target_fish = req.target_fish
    db.commit()
    return {"status": "ok", "message": "饵料修改成功"}

@app.delete("/api/inventory/bait/{bait_id}", tags=["饵料"])
async def delete_user_bait(
    bait_id: int,
    x_openid: Optional[str] = Header(None, alias="X-OpenID"),
    db: Session = Depends(get_db)
):
    """从用户私有钓箱中删除饵料"""
    openid = _require_openid(x_openid)
    
    user_bait = db.query(UserBait).filter(UserBait.id == bait_id, UserBait.openid == openid).first()
    if not user_bait:
        raise HTTPException(status_code=404, detail="未找到该饵料记录")
        
    db.delete(user_bait)
    db.commit()
    return {"status": "ok", "message": "饵料删除成功"}


@app.get("/api/inventory/baits/public", tags=["饵料"])
async def list_public_baits(db: Session = Depends(get_db)):
    """获取公共标准饵料库，供下拉级联选择"""
    baits = db.query(PublicBait).filter(PublicBait.is_verified == 1).all()
    
    # 按照 category -> brand -> name 进行聚合，方便前端读取
    category_map = {}
    for b in baits:
        cat = b.category
        brand = b.brand
        if cat not in category_map:
            category_map[cat] = {}
        if brand not in category_map[cat]:
            category_map[cat][brand] = []
            
        category_map[cat][brand].append({
            "name": b.name,
            "flavor": b.flavor,
            "targetFish": b.target_fish
        })
        
    return {"status": "ok", "data": category_map}


@app.get("/api/inventory/baits/user", tags=["饵料"])
async def list_user_baits(
    x_openid: Optional[str] = Header(None, alias="X-OpenID"),
    db: Session = Depends(get_db)
):
    """获取用户钓箱里现有的所有饵料"""
    openid = _require_openid(x_openid)
        
    baits = db.query(UserBait).filter(UserBait.openid == openid).all()
    result = []
    for b in baits:
        result.append({
            "id": f"b{b.id}",
            "category": b.category,
            "brand": b.brand,
            "name": b.name,
            "flavor": b.flavor,
            "targetFish": b.target_fish
        })
    return {"status": "ok", "data": result}


def _require_openid(x_openid: Optional[str]) -> str:
    """强制要求有效的用户标识，缺失时返回 401。

    用于装备库 / 会话日志等用户私有数据接口，避免匿名请求
    被静默兜底到共享的测试账号，造成数据串号与越权读写。
    """
    if not x_openid or not x_openid.strip():
        raise HTTPException(status_code=401, detail="未提供用户标识 (X-OpenID Header is empty)")
    return x_openid.strip()


def _optional_openid(x_openid: Optional[str]) -> Optional[str]:
    """返回规范化的 openid，缺失时返回 None（用于允许匿名访问的接口）。"""
    return x_openid.strip() if x_openid and x_openid.strip() else None


def _get_user_inventory(db: Session, openid: Optional[str]) -> dict:
    """Helper to query all digital tackle box items for a user and format them."""
    if not openid:
        return {"rods": [], "mainLines": [], "subLineHooks": [], "floats": [], "baits": []}
    rods = db.query(UserRod).filter(UserRod.openid == openid).all()
    mainlines = db.query(UserMainLine).filter(UserMainLine.openid == openid).all()
    sublines = db.query(UserSubLineHook).filter(UserSubLineHook.openid == openid).all()
    floats = db.query(UserFloat).filter(UserFloat.openid == openid).all()
    baits = db.query(UserBait).filter(UserBait.openid == openid).all()
    
    return {
        "rods": [{
            "id": f"r{r.id}",
            "brand": r.brand,
            "name": r.series,
            "length": r.length,
            "action": r.action or "未知",
            "type": "台钓竿"
        } for r in rods],
        "mainLines": [{
            "id": f"m{m.id}",
            "size": m.size,
            "length": m.length
        } for m in mainlines],
        "subLineHooks": [{
            "id": f"s{s.id}",
            "lineSize": s.line_size,
            "hookType": s.hook_type,
            "hookSize": s.hook_size
        } for s in sublines],
        "floats": [{
            "id": f"f{f.id}",
            "name": f.name or f"{f.material} {f.shape}漂",
            "material": f.material,
            "shape": f.shape,
            "lead": f.lead,
            "tail_type": f.tail_type
        } for f in floats],
        "baits": [{
            "id": f"b{b.id}",
            "category": b.category,
            "brand": b.brand,
            "name": b.name,
            "flavor": b.flavor,
            "targetFish": b.target_fish
        } for b in baits]
    }


def _resolve_inventory(req_inventory: Optional[Dict], db: Session, openid: Optional[str]) -> dict:
    """解析预测时使用的装备上下文。

    优先使用请求里携带的「本次出钓装备」（用户在小程序勾选的实际带出装备）；
    仅当请求未携带或勾选为空时，才回退到该用户钓箱的全量装备。
    这样主预测的装备建议只会在用户「本次带了的」范围内挑选，避免推荐没带的装备。
    """
    if req_inventory and any(
        req_inventory.get(k) for k in ("rods", "mainLines", "subLineHooks", "floats", "baits")
    ):
        return req_inventory
    return _get_user_inventory(db, openid)


@app.post("/api/predict", response_model=PredictResponse, tags=["预测"])
async def predict(
    req: PredictRequest,
    x_openid: Optional[str] = Header(None, alias="X-OpenID"),
    db: Session = Depends(get_db)
):
    """
    🎯 钓鱼预测主接口

    接收传感器时序数据 + 气象信息，返回多因子融合预测结果。
    传感器数据越多（时间跨度越长），预测置信度越高。

    **报告阶段**:
    - `instant` (刚连接): 基于最新单条数据，置信度 ~30%
    - `brief` (≥5分钟): 启用气压趋势 + 溶氧估算
    - `standard` (≥10分钟): 启用温度趋势 + 温跃层分析
    - `full` (≥30分钟): 全量深度分析
    """
    # 校验并决定要计算的鱼种列表
    # 为了保证排行榜完整性，无论是否指定鱼种，我们均计算所有支持的鱼种
    if req.fish_type != "auto" and req.fish_type not in FISH_PROFILES:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的鱼种: {req.fish_type}，可选: {', '.join(FISH_PROFILES.keys())}",
        )
    target_fishes = list(FISH_PROFILES.keys())

    # 获取实时天气数据与地名解析并列执行
    weather_service = QWeatherService()
    api_data = await weather_service.get_realtime_weather(req.lat, req.lng, req.altitude)
    location_name = await TencentLBSService.reverse_geocode(req.lat, req.lng)

    # 构建时序数据（包含 v2 降级映射）
    def _to_reading(s: SensorDataIn) -> SensorReading:
        if s.t_water is not None:
            # v2 设备：单水温传感器结合气温进行温跃层估算
            t_b = s.t_water
            if s.t_air is not None:
                # 物理模型：水面温度估算为底水温与实测气温的加权热力学响应值 (取因子 0.65)
                # t_surface = t_bottom + (t_air - t_bottom) * 0.65
                t_s = round(t_b + (s.t_air - t_b) * 0.65, 2)
                t_m = round((t_s + t_b) / 2, 2)
            else:
                t_m = t_s = s.t_water
        else:
            # v1 设备：保持原值
            t_b, t_m, t_s = s.t_bottom, s.t_mid, s.t_surface
        return SensorReading(
            timestamp=s.timestamp,
            t_bottom=t_b, t_mid=t_m, t_surface=t_s,
            p_local=s.p_local,
        )

    readings = tuple(_to_reading(s) for s in req.sensors)
    series = SensorTimeSeries(readings=readings)

    # 预测接口允许匿名访问：无登录态时不附带装备上下文，也不落库
    # 装备上下文：优先用本次出钓勾选（req.user_inventory），未携带时回退钓箱全量
    openid = _optional_openid(x_openid)
    user_inventory = _resolve_inventory(req.user_inventory, db, openid)

    # 对目标鱼种循环跑分
    fish_results = []
    for f_name in target_fishes:
        profile = FISH_PROFILES[f_name]
        service = FishingPredictionService(fish_profile=profile)
        res = service.predict_from_series(series=series, api=api_data, user_inventory=user_inventory, spot_context=req.spot_context)
        fish_results.append({
            "name": f_name,
            "result": res,
            "bite_index": res.bite_index
        })

    # 按照 bite_index 降序排列
    fish_results.sort(key=lambda x: x["bite_index"], reverse=True)
    
    # 如果指定了具体目标鱼种，主推荐优先选择用户指定的那个鱼种，否则默认推荐得分最高的一个
    if req.fish_type == "auto":
        best_match = fish_results[0]
    else:
        best_match = next((item for item in fish_results if item["name"] == req.fish_type), fish_results[0])
    best_result = best_match["result"]
    
    # 提取推荐榜单
    recommended_fishes = [{"name": item["name"], "score": item["bite_index"]} for item in fish_results]

    # 提取用于前端展示的天气数据
    weather_info = {
        "text": api_data.original_text,
        "wind_dir": api_data.original_wind_dir,
        "wind_speed": api_data.wind_speed,
        "humidity": api_data.humidity
    }

    # ── 大师知识库 RAG 检索（阶段三注入） ──
    # 从预测结果中提取查询维度，召回 Top-3 大师战术秘籍
    master_tips = []
    try:
        # 提取水温（取最新传感器读数的水底温度）
        rag_t_water = None
        if readings:
            latest_reading = readings[-1]
            rag_t_water = latest_reading.t_bottom

        # 提取气压状态（从战术标签推导）
        rag_pressure_state = None
        for tag in best_result.tactical_tags:
            if "PRESSURE_CRASH" in tag or "气压骤降" in tag:
                rag_pressure_state = "骤降"
                break
            elif "PRESSURE_DROPPING" in tag or "气压下降" in tag:
                rag_pressure_state = "骤降"
                break
            elif "PRESSURE_RISING" in tag or "气压上升" in tag:
                rag_pressure_state = "上升"
                break
            elif "PRESSURE_STABLE" in tag or "气压稳定" in tag:
                rag_pressure_state = "稳定"
                break

        kb = MasterKBRetriever.get()
        rag_records = kb.search(
            target_fish=best_match["name"],
            t_water=rag_t_water,
            pressure_state=rag_pressure_state,
            top_k=3,
        )
        # 格式化为前端友好的结构
        for rec in rag_records:
            master_tips.append({
                "master": rec.get("master", ""),
                "title": rec.get("title", ""),
                "line": rec.get("line", ""),
                "float_setup": rec.get("float_setup", ""),
                "recipe": rec.get("recipe", ""),
                "flavor": rec.get("flavor", ""),
                "rhythm": rec.get("rhythm", ""),
                "video_url": rec.get("video_url", ""),
                "season": rec.get("season", ""),
                "temp_range": f"{rec.get('temp_min', '?')}~{rec.get('temp_max', '?')}℃",
            })
    except Exception as e:
        print(f"[Warning] RAG retrieval failed in /api/predict: {e}")

    response = PredictResponse(
        recommended_fish=best_match["name"],
        recommended_fishes=recommended_fishes,
        bite_index=best_result.bite_index,
        do_trend=best_result.do_trend,
        report_stage=best_result.report_stage,
        confidence=best_result.confidence,
        tactical_tags=best_result.tactical_tags,
        time_period_advice=best_result.time_period_advice or None,
        season_note=best_result.season_note or None,
        weather_info=weather_info,
        tactical_advice=best_result.tactical_advice,
        master_tips=master_tips,
    )

    # 如果有登录态，异步或同步保存预测日志
    if x_openid and x_openid.strip():
        try:
            history = PredictionHistory(
                openid=x_openid,
                lat=req.lat,
                lng=req.lng,
                location_name=location_name,
                recommended_fish=best_match["name"],
                bite_index=best_result.bite_index,
                weather_snapshot=weather_info,
                tactical_advice=best_result.tactical_advice,
                tags=best_result.tactical_tags,
                solunar_info=best_result.solunar_info
            )
            db.add(history)
            db.commit()
            print(f"[Debug] Saved prediction history for user: {x_openid}")
        except Exception as e:
            db.rollback()
            print(f"[Error] Failed to save prediction history: {e}")
    else:
        print(f"[Warning] Prediction result not saved: X-OpenID header is missing or empty.")

    return response


class WeatherPredictRequest(BaseModel):
    """纯天气预测请求（无需传感器）"""
    fish_type: str = Field("auto", description="目标鱼种名称，传 'auto' 则全鱼种测算并推荐")
    lat: float = Field(..., description="纬度")
    lng: float = Field(..., description="经度")
    user_inventory: Optional[Dict] = Field(None, description="本次出钓装备（不传则回退钓箱全量）")
    spot_context: Optional[Dict] = Field(None, description="钓点情况 {type,density,clarity}（仅影响建议，不改开口指数）")


@app.post("/api/predict/weather", tags=["预测"])
async def predict_weather_only(
    req: WeatherPredictRequest,
    x_openid: Optional[str] = Header(None, alias="X-OpenID"),
    db: Session = Depends(get_db)
):
    """
    🌤️ 纯天气模式预测（无需传感器数据）

    钓鱼人出发前，仅凭 GPS 位置获取粗略鱼情评分和建议。
    置信度约 30%（标注为气象推测级）。
    """
    # 获取实时天气
    weather_service = QWeatherService()
    api_data = await weather_service.get_realtime_weather(req.lat, req.lng)

    # 获取气温（从实时天气中无法直接获取气温，调用预报取当前小时）
    hourly = await weather_service.get_hourly_forecast(req.lat, req.lng)
    air_temp = hourly[0]["temp"] if hourly else 22.0  # 兜底 22℃

    # 始终计算所有鱼种，以便生成完整的排行榜
    if req.fish_type != "auto" and req.fish_type not in FISH_PROFILES:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的鱼种: {req.fish_type}",
        )
    target_fishes = list(FISH_PROFILES.keys())

    # 纯天气预测允许匿名访问（出发前决策）
    # 装备上下文：优先用本次出钓勾选，未携带时回退钓箱全量
    openid = _optional_openid(x_openid)
    user_inventory = _resolve_inventory(req.user_inventory, db, openid)

    # 对目标鱼种循环跑分
    fish_results = []
    for f_name in target_fishes:
        profile = FISH_PROFILES[f_name]
        service = FishingPredictionService(fish_profile=profile)
        res = service.predict_weather_only(
            api=api_data, air_temp=air_temp, lat=req.lat, lng=req.lng,
            hourly_forecast=hourly, user_inventory=user_inventory,
            spot_context=req.spot_context,
        )
        fish_results.append({
            "name": f_name,
            "result": res,
            "bite_index": res.bite_index,
        })

    fish_results.sort(key=lambda x: x["bite_index"], reverse=True)
    # 如果指定了具体鱼种，主推荐优先锁定该鱼种，否则默认推荐得分最高的鱼种
    if req.fish_type == "auto":
        best = fish_results[0]
    else:
        best = next((item for item in fish_results if item["name"] == req.fish_type), fish_results[0])
    best_result = best["result"]

    weather_info = {
        "text": api_data.original_text,
        "wind_dir": api_data.original_wind_dir,
        "wind_speed": api_data.wind_speed,
        "humidity": api_data.humidity,
        "air_temp": air_temp,
    }

    return {
        "mode": "weather_only",
        "recommended_fish": best["name"],
        "recommended_fishes": [{"name": r["name"], "score": r["bite_index"]} for r in fish_results],
        "bite_index": best_result.bite_index,
        "confidence": best_result.confidence,
        "report_stage": "weather_only",
        "tactical_tags": best_result.tactical_tags,
        "tactical_advice": best_result.tactical_advice,
        "time_period_advice": best_result.time_period_advice,
        "season_note": best_result.season_note,
        "solunar_info": best_result.solunar_info,
        "weather_info": weather_info,
    }


@app.get("/api/forecast/today", tags=["预报"])
async def forecast_today(
    lat: float,
    lng: float,
    fish_type: str = "鲫鱼",
):
    """
    📅 今日鱼情预报

    返回未来 24 小时逐小时鱼情评分 + 最佳出钓窗口推荐。
    帮助钓鱼人决定 "几点出门最好"。
    """
    if fish_type not in FISH_PROFILES:
        raise HTTPException(status_code=400, detail=f"不支持的鱼种: {fish_type}")

    profile = FISH_PROFILES[fish_type]
    weather_service = QWeatherService()
    hourly = await weather_service.get_hourly_forecast(lat, lng)

    if not hourly:
        raise HTTPException(status_code=502, detail="无法获取天气预报数据")

    forecast_service = FishingForecastService(fish_profile=profile)

    hourly_scores = forecast_service.calc_hourly_scores(hourly, profile)
    best_windows = forecast_service.calc_best_windows(hourly, profile)
    daily_summary = forecast_service.calc_daily_summary(hourly, profile)

    return {
        "fish_type": fish_type,
        "daily_summary": daily_summary,
        "best_windows": best_windows,
        "hourly_scores": hourly_scores,
    }


@app.get("/api/forecast/3day", tags=["预报"])
async def forecast_3day(
    lat: float,
    lng: float,
    fish_type: str = "鲫鱼",
):
    """
    📅 未来 3 天鱼情日历

    帮助钓鱼人回答"这周六和周日哪天更好？"
    返回未来 3 天逐日鱼情评分、最佳日推荐和对比说明。
    """
    if fish_type not in FISH_PROFILES:
        raise HTTPException(status_code=400, detail=f"不支持的鱼种: {fish_type}")

    profile = FISH_PROFILES[fish_type]
    weather_service = QWeatherService()
    daily = await weather_service.get_3day_forecast(lat, lng)

    if not daily:
        raise HTTPException(status_code=502, detail="无法获取3天天气预报数据")

    forecast_service = FishingForecastService(fish_profile=profile)
    calendar = forecast_service.calc_3day_calendar(daily, profile)

    return {
        "fish_type": fish_type,
        **calendar,
    }


@app.post("/api/sensor/realtime", tags=["数据上报"])
async def upload_realtime(
    req: RealtimeSensorRequest,
    x_openid: Optional[str] = Header(None, alias="X-OpenID"),
    db: Session = Depends(get_db)
):
    """上报实时传感器数据（单条）"""
    if x_openid and x_openid.strip():
        record = SensorRecord(
            openid=x_openid,
            timestamp=req.sensor.timestamp,
            t_water=req.sensor.t_water,
            t_air=req.sensor.t_air,
            p_local=req.sensor.p_local,
            t_bottom=req.sensor.t_bottom,
            t_mid=req.sensor.t_mid,
            t_surface=req.sensor.t_surface,
            lat=req.lat,
            lng=req.lng
        )
        db.add(record)
        db.commit()
    else:
        print(f"[Warning] Realtime data not saved: X-OpenID header is missing or empty.")

    return {
        "status": "ok",
        "received_at": int(time.time()),
        "timestamp": req.sensor.timestamp,
    }


@app.post("/api/sensor/history", tags=["数据上报"])
async def upload_history(
    req: BatchSensorRequest,
    x_openid: Optional[str] = Header(None, alias="X-OpenID"),
    db: Session = Depends(get_db)
):
    """批量上报历史传感器数据"""
    if x_openid and x_openid.strip():
        records = [
            SensorRecord(
                openid=x_openid,
                timestamp=s.timestamp,
                t_water=s.t_water,
                t_air=s.t_air,
                p_local=s.p_local,
                t_bottom=s.t_bottom,
                t_mid=s.t_mid,
                t_surface=s.t_surface,
                lat=req.lat,
                lng=req.lng
            ) for s in req.records
        ]
        db.add_all(records)
        db.commit()
    else:
        print(f"[Warning] Batch history data not saved: X-OpenID header is missing or empty.")

    return {
        "status": "ok",
        "received_at": int(time.time()),
        "count": len(req.records),
    }


@app.get("/api/sensor/records", tags=["数据拉取"])
async def get_sensor_records(
    limit: int = 1440,
    x_openid: Optional[str] = Header(None, alias="X-OpenID"),
    db: Session = Depends(get_db)
):
    """拉取最近的传感器历史记录（用于小程序重启后恢复趋势图）"""
    if not x_openid or not x_openid.strip():
        raise HTTPException(status_code=401, detail="未提供用户标识 (X-OpenID Header is empty)")
        
    records = db.query(SensorRecord).filter(
        SensorRecord.openid == x_openid
    ).order_by(SensorRecord.timestamp.desc()).limit(limit).all()
    
    # 倒序查询出最近数据，返回时正序排列供趋势图展示
    records.reverse()
    
    return {
        "status": "ok",
        "data": [
            {
                "timestamp": r.timestamp,
                "tWater": r.t_water,
                "tAir": r.t_air,
                "pLocal": r.p_local,
                # v1 兼容字段
                "tBottom": r.t_bottom,
                "tMid": r.t_mid,
                "tSurface": r.t_surface,
            }
            for r in records
        ]
    }


class LoginRequest(BaseModel):
    code: str = Field(..., description="微信登录code")


# 微信小程序凭证从环境变量读取（请在 .env 中配置 WX_APPID / WX_APP_SECRET，切勿硬编码进源码）
WX_APPID = os.getenv("WX_APPID", "")
WX_APP_SECRET = os.getenv("WX_APP_SECRET", "")

@app.post("/api/login", tags=["用户"])
async def login(req: LoginRequest, db: Session = Depends(get_db)):
    """小程序登录（请求微信官方接口换取真实 openid）并记录"""
    from datetime import datetime
    import httpx
    
    if req.code == "test":
        real_openid = "test_openid_user_001"
    else:
        if not WX_APPID or not WX_APP_SECRET:
            raise HTTPException(status_code=500, detail="服务端未配置微信小程序凭证 (WX_APPID/WX_APP_SECRET)")
        # 请求微信官方接口
        url = f"https://api.weixin.qq.com/sns/jscode2session?appid={WX_APPID}&secret={WX_APP_SECRET}&js_code={req.code}&grant_type=authorization_code"
        async with httpx.AsyncClient() as client:
            resp = await client.get(url)
            data = resp.json()
            
        if "openid" not in data:
            raise HTTPException(status_code=400, detail=f"微信登录失败: {data.get('errmsg', '未知错误')}")
            
        real_openid = data["openid"]
    
    user = db.query(User).filter(User.openid == real_openid).first()
    if not user:
        user = User(openid=real_openid)
        db.add(user)
    else:
        user.last_login = datetime.now()
    
    db.commit()
    return {
        "status": "ok",
        "openid": real_openid,
        "message": "登录成功",
    }


@app.get("/api/history/logs", tags=["用户"])
async def get_history_logs(
    limit: int = 20,
    x_openid: Optional[str] = Header(None, alias="X-OpenID"),
    db: Session = Depends(get_db)
):
    """获取用户的作钓预测历史记录"""
    if not x_openid or not x_openid.strip():
        raise HTTPException(status_code=401, detail="未提供用户标识 (X-OpenID Header is empty)")
        
    records = db.query(PredictionHistory).filter(
        PredictionHistory.openid == x_openid
    ).order_by(PredictionHistory.created_at.desc()).limit(limit).all()
    
    return {
        "status": "ok",
        "data": [
            {
                "id": r.id,
                "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else None,
                "lat": r.lat,
                "lng": r.lng,
                "location_name": r.location_name,
                "recommended_fish": r.recommended_fish,
                "bite_index": r.bite_index,
                "weather_snapshot": r.weather_snapshot,
                "tactical_advice": r.tactical_advice,
                "tags": r.tags,
            }
            for r in records
        ]
    }


# ══════════════════════════════════════════════
#  钓鱼会话日志
# ══════════════════════════════════════════════

class SessionSaveRequest(BaseModel):
    """保存钓鱼会话摘要"""
    start_time: int = Field(..., description="会话起始 Unix 时间戳")
    end_time: int = Field(..., description="会话结束 Unix 时间戳")
    duration_min: int = Field(..., description="作钓时长（分钟）")
    data_points: int = Field(0, description="传感器数据点数")
    lat: float = 0.0
    lng: float = 0.0
    location_name: Optional[str] = None
    # 水温
    t_water_start: Optional[float] = None
    t_water_end: Optional[float] = None
    t_water_min: Optional[float] = None
    t_water_max: Optional[float] = None
    # 气温
    t_air_start: Optional[float] = None
    t_air_end: Optional[float] = None
    # 气压
    p_start: Optional[float] = None
    p_end: Optional[float] = None
    p_trend: Optional[str] = None
    # 天气
    weather_text: Optional[str] = None
    wind_desc: Optional[str] = None
    # 预测汇总
    bite_index_max: Optional[int] = None
    bite_index_avg: Optional[int] = None
    recommended_fish: Optional[str] = None
    # 本次出钓使用的装备快照 (V2 装备闭环)
    equipment_used: Optional[Dict] = Field(None, description="本次出钓使用的装备快照 {rods, mainLines, subLineHooks, floats, baits}")


@app.post("/api/session/save", tags=["会话日志"])
async def save_session(
    req: SessionSaveRequest,
    x_openid: Optional[str] = Header(None, alias="X-OpenID"),
    db: Session = Depends(get_db)
):
    """
    📝 保存钓鱼会话摘要

    用户断开 ESP32 时由小程序聚合传感器数据后调用。
    一次出钓 = 一条记录。
    """
    if not x_openid or not x_openid.strip():
        raise HTTPException(status_code=401, detail="未提供用户标识")

    # 如果前端没传 location_name，尝试反解
    loc_name = req.location_name
    if not loc_name and req.lat and req.lng:
        try:
            loc_name = await TencentLBSService.reverse_geocode(req.lat, req.lng)
        except Exception:
            loc_name = None

    session = FishingSession(
        openid=x_openid,
        start_time=req.start_time,
        end_time=req.end_time,
        duration_min=req.duration_min,
        data_points=req.data_points,
        lat=req.lat,
        lng=req.lng,
        location_name=loc_name,
        t_water_start=req.t_water_start,
        t_water_end=req.t_water_end,
        t_water_min=req.t_water_min,
        t_water_max=req.t_water_max,
        t_air_start=req.t_air_start,
        t_air_end=req.t_air_end,
        p_start=req.p_start,
        p_end=req.p_end,
        p_trend=req.p_trend,
        weather_text=req.weather_text,
        wind_desc=req.wind_desc,
        bite_index_max=req.bite_index_max,
        bite_index_avg=req.bite_index_avg,
        recommended_fish=req.recommended_fish,
        equipment_used=req.equipment_used,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    return {
        "status": "ok",
        "session_id": session.id,
        "message": "作钓日志已保存",
    }


@app.get("/api/session/list", tags=["会话日志"])
async def list_sessions(
    limit: int = 20,
    x_openid: Optional[str] = Header(None, alias="X-OpenID"),
    db: Session = Depends(get_db)
):
    """
    📋 获取用户的钓鱼会话日志列表

    按时间倒序返回，每条记录是一次完整出钓的摘要。
    """
    if not x_openid or not x_openid.strip():
        raise HTTPException(status_code=401, detail="未提供用户标识")

    records = db.query(FishingSession).filter(
        FishingSession.openid == x_openid
    ).order_by(FishingSession.created_at.desc()).limit(limit).all()

    def _fmt(r):
        return {
            "id": r.id,
            "start_time": r.start_time,
            "end_time": r.end_time,
            "duration_min": r.duration_min,
            "data_points": r.data_points,
            "lat": r.lat,
            "lng": r.lng,
            "location_name": r.location_name,
            "t_water_start": r.t_water_start,
            "t_water_end": r.t_water_end,
            "t_water_min": r.t_water_min,
            "t_water_max": r.t_water_max,
            "t_air_start": r.t_air_start,
            "t_air_end": r.t_air_end,
            "p_start": r.p_start,
            "p_end": r.p_end,
            "p_trend": r.p_trend,
            "weather_text": r.weather_text,
            "wind_desc": r.wind_desc,
            "bite_index_max": r.bite_index_max,
            "bite_index_avg": r.bite_index_avg,
            "recommended_fish": r.recommended_fish,
            "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else None,
        }

    return {
        "status": "ok",
        "data": [_fmt(r) for r in records],
    }


# ══════════════════════════════════════════════
#  V2 AI 救场与战报
# ══════════════════════════════════════════════

@app.post("/api/v2/rescue", tags=["V2 智能救场"])
async def ai_rescue(req: RescueRequest):
    """
    🚑 AI 鱼情救场（第二次握手）
    接收传感器批量 Dump 数据和用户主观症状，
    经过物理引擎处理后交由大模型生成处方。
    """
    def _to_reading(s: SensorDataIn) -> SensorReading:
        if s.t_water is not None:
            t_b = s.t_water
            if s.t_air is not None:
                t_s = round(t_b + (s.t_air - t_b) * 0.65, 2)
                t_m = round((t_s + t_b) / 2, 2)
            else:
                t_m = t_s = s.t_water
        else:
            t_b, t_m, t_s = s.t_bottom, s.t_mid, s.t_surface
        return SensorReading(
            timestamp=s.timestamp,
            t_bottom=t_b, t_mid=t_m, t_surface=t_s,
            p_local=s.p_local
        )
    
    readings = tuple(_to_reading(s) for s in req.sensors)
    series = SensorTimeSeries(readings=readings)
    
    # 1. 物理引擎分析
    engine = FishingEngine()
    engine_result = engine.evaluate(series)
    
    # 2. 调用 LLM 生成处方
    prescription_svc = PrescriptionService()
    prescription = prescription_svc.generate_prescription(
        physical_tags=engine_result["tags"],
        symptom_tags=req.symptom_tags,
        metrics=engine_result["metrics"],
        fish_context=req.fish_context,
        user_inventory=req.user_inventory
    )
    
    return {
        "status": "ok",
        "engine_metrics": engine_result["metrics"],
        "engine_tags": engine_result["tags"],
        "prescription": prescription
    }


@app.post("/api/catch/log", tags=["渔获反馈"])
async def log_catch(
    req: CatchLogRequest,
    x_openid: Optional[str] = Header(None, alias="X-OpenID"),
    db: Session = Depends(get_db),
):
    """
    🎣 记录真实渔获（反馈闭环）

    用户记录"实际钓到了什么"，连同当时的预测/环境快照一起存档。
    **仅作校准样本，不参与任何预测计算。**
    """
    openid = _require_openid(x_openid)

    location_name = None
    if req.lat and req.lng:
        try:
            location_name = await TencentLBSService.reverse_geocode(req.lat, req.lng)
        except Exception:
            location_name = None

    row = CatchLog(
        openid=openid,
        fish_species=req.fish_species,
        catch_count=req.catch_count,
        total_weight=req.total_weight,
        note=req.note,
        spot_type=req.spot_type,
        spot_density=req.spot_density,
        water_clarity=req.water_clarity,
        lat=req.lat,
        lng=req.lng,
        location_name=location_name,
        target_fish=req.target_fish,
        bite_index=req.bite_index,
        t_water=req.t_water,
        p_local=req.p_local,
        weather_text=req.weather_text,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"status": "ok", "id": row.id}


@app.get("/api/catch/list", tags=["渔获反馈"])
async def list_catch(
    limit: int = 30,
    x_openid: Optional[str] = Header(None, alias="X-OpenID"),
    db: Session = Depends(get_db),
):
    """获取当前用户的渔获记录列表（按时间倒序）。"""
    openid = _require_openid(x_openid)
    limit = max(1, min(limit, 100))
    rows = (
        db.query(CatchLog)
        .filter(CatchLog.openid == openid)
        .order_by(CatchLog.created_at.desc())
        .limit(limit)
        .all()
    )
    data = [{
        "id": r.id,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "fish_species": r.fish_species,
        "catch_count": r.catch_count,
        "total_weight": r.total_weight,
        "note": r.note,
        "spot_type": r.spot_type,
        "spot_density": r.spot_density,
        "water_clarity": r.water_clarity,
        "location_name": r.location_name,
        "target_fish": r.target_fish,
        "bite_index": r.bite_index,
        "t_water": r.t_water,
        "p_local": r.p_local,
        "weather_text": r.weather_text,
    } for r in rows]
    return {"status": "ok", "data": data}


@app.get("/api/v2/poster/{session_id}", tags=["V2 智能救场"])
async def get_poster(
    session_id: int,
    x_openid: Optional[str] = Header(None, alias="X-OpenID"),
    db: Session = Depends(get_db)
):
    """
    🏆 获取战报海报（第三次握手）
    """
    if not x_openid or not x_openid.strip():
        raise HTTPException(status_code=401, detail="未提供用户标识")
        
    session = db.query(FishingSession).filter(
        FishingSession.id == session_id,
        FishingSession.openid == x_openid
    ).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
        
    session_data = {
        "duration_min": session.duration_min,
        "delta_p": 0.0
    }
    
    if session.p_end is not None and session.p_start is not None:
        session_data["delta_p"] = round(session.p_end - session.p_start, 2)
        
    catch_level = "稳赚"
    if session.bite_index_avg:
        if session.bite_index_avg > 80: catch_level = "爆护"
        elif session.bite_index_avg > 60: catch_level = "稳赚"
        elif session.bite_index_avg > 40: catch_level = "惨淡"
        else: catch_level = "空军"
    session_data["catch_level"] = catch_level
        
    poster_gen = PosterGenerator()
    return {
        "status": "ok",
        "poster": poster_gen.generate_poster_data(session_data)
    }

# ── 开发模式入口 ──────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
