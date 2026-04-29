"""
FastAPI 应用入口 — AI 钓鱼预测 API 服务
======================================
启动方式:
  开发: python server.py
  生产: gunicorn server:app -c gunicorn.conf.py
"""
import time
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from domain.value_objects import (
    ApiData, SensorReading, SensorTimeSeries,
)
from domain.services import FishingPredictionService
from domain.constants import FISH_PROFILES
from domain.weather import QWeatherService


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
async def predict(req: PredictRequest):
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

    # 获取实时天气数据
    weather_service = QWeatherService()
    api_data = await weather_service.get_realtime_weather(req.lat, req.lng, req.altitude)

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

    return PredictResponse(
        recommended_fish=best_match["name"],
        recommended_fishes=recommended_fishes,
        bite_index=best_result.bite_index,
        do_trend=best_result.do_trend,
        report_stage=best_result.report_stage,
        confidence=best_result.confidence,
        tactical_tags=best_result.tactical_tags,
        time_period_advice=best_result.time_period_advice or None,
        season_note=best_result.season_note or None,
        solunar_info=best_result.solunar_info,
        tactical_advice=best_result.tactical_advice,
    )


@app.post("/api/sensor/realtime", tags=["数据上报"])
async def upload_realtime(req: RealtimeSensorRequest):
    """上报实时传感器数据（单条）

    小程序每收到一条 BLE 实时帧后调用此接口。
    当前版本仅做 ACK，后续可接入存储层。
    """
    return {
        "status": "ok",
        "received_at": int(time.time()),
        "timestamp": req.sensor.timestamp,
    }


@app.post("/api/sensor/history", tags=["数据上报"])
async def upload_history(req: BatchSensorRequest):
    """批量上报历史传感器数据

    小程序收到 BLE 历史帧（CMD=0x03）后批量调用此接口。
    当前版本仅做 ACK，后续可接入存储层。
    """
    return {
        "status": "ok",
        "received_at": int(time.time()),
        "count": len(req.records),
    }


@app.post("/api/login", tags=["用户"])
async def login(req: Dict):
    """小程序登录（换取 openid）

    目前仅做演示，返回固定 openid。
    实际生产环境需调用微信 API: https://api.weixin.qq.com/sns/jscode2session
    """
    return {
        "status": "ok",
        "openid": "test_openid_user_001",
        "message": "登录成功（演示模式）",
    }


# ── 开发模式入口 ──────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
