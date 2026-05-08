"""
FastAPI 应用入口 — AI 钓鱼预测 API 服务
======================================
启动方式:
  开发: python server.py
  生产: gunicorn server:app -c gunicorn.conf.py
"""
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
from infrastructure.database import engine, Base, get_db
from infrastructure.models import User, SensorRecord, PredictionHistory

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
    t_bottom: Optional[float] = Field(None, description="水底温度 ℃")
    t_mid: Optional[float] = Field(None, description="水下1米温度 ℃")
    t_surface: Optional[float] = Field(None, description="水面温度 ℃")
    p_local: Optional[float] = Field(None, description="本地气压 hPa")


class PredictRequest(BaseModel):
    """预测请求"""
    fish_type: str = Field("auto", description="目标鱼种名称，传 'auto' 则全鱼种测算并推荐")
    sensors: List[SensorDataIn] = Field(..., description="传感器时序数据（按时间升序）", min_length=1)
    lat: float = Field(0.0, description="纬度")
    lng: float = Field(0.0, description="经度")
    altitude: float = Field(0.0, ge=0, description="海拔 米")


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
    if req.fish_type == "auto":
        target_fishes = list(FISH_PROFILES.keys())
    else:
        if req.fish_type not in FISH_PROFILES:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的鱼种: {req.fish_type}，可选: {', '.join(FISH_PROFILES.keys())}",
            )
        target_fishes = [req.fish_type]

    # 获取实时天气数据与地名解析并列执行
    weather_service = QWeatherService()
    api_data = await weather_service.get_realtime_weather(req.lat, req.lng, req.altitude)
    location_name = await TencentLBSService.reverse_geocode(req.lat, req.lng)

    # 构建时序数据
    readings = tuple(
        SensorReading(
            timestamp=s.timestamp,
            t_bottom=s.t_bottom,
            t_mid=s.t_mid,
            t_surface=s.t_surface,
            p_local=s.p_local,
        )
        for s in req.sensors
    )
    series = SensorTimeSeries(readings=readings)

    # 对目标鱼种循环跑分
    fish_results = []
    for f_name in target_fishes:
        profile = FISH_PROFILES[f_name]
        service = FishingPredictionService(fish_profile=profile)
        res = service.predict_from_series(series=series, api=api_data)
        fish_results.append({
            "name": f_name,
            "result": res,
            "bite_index": res.bite_index
        })

    # 按照 bite_index 降序排列
    fish_results.sort(key=lambda x: x["bite_index"], reverse=True)
    best_match = fish_results[0]
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


@app.post("/api/predict/weather", tags=["预测"])
async def predict_weather_only(req: WeatherPredictRequest):
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

    # 决定鱼种列表
    if req.fish_type == "auto":
        target_fishes = list(FISH_PROFILES.keys())
    else:
        if req.fish_type not in FISH_PROFILES:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的鱼种: {req.fish_type}",
            )
        target_fishes = [req.fish_type]

    # 对目标鱼种循环跑分
    fish_results = []
    for f_name in target_fishes:
        profile = FISH_PROFILES[f_name]
        service = FishingPredictionService(fish_profile=profile)
        res = service.predict_weather_only(
            api=api_data, air_temp=air_temp, lat=req.lat, lng=req.lng,
            hourly_forecast=hourly,
        )
        fish_results.append({
            "name": f_name,
            "result": res,
            "bite_index": res.bite_index,
        })

    fish_results.sort(key=lambda x: x["bite_index"], reverse=True)
    best = fish_results[0]
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
            t_bottom=req.sensor.t_bottom,
            t_mid=req.sensor.t_mid,
            t_surface=req.sensor.t_surface,
            p_local=req.sensor.p_local,
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
                t_bottom=s.t_bottom,
                t_mid=s.t_mid,
                t_surface=s.t_surface,
                p_local=s.p_local,
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


class LoginRequest(BaseModel):
    code: str = Field(..., description="微信登录code")


WX_APPID = "wx8766f98bf34482de"
WX_APP_SECRET = "f330ef82a7b7be368834392466d5b699"

@app.post("/api/login", tags=["用户"])
async def login(req: LoginRequest, db: Session = Depends(get_db)):
    """小程序登录（请求微信官方接口换取真实 openid）并记录"""
    from datetime import datetime
    import httpx
    
    if req.code == "test":
        real_openid = "test_openid_user_001"
    else:
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


# ── 开发模式入口 ──────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
