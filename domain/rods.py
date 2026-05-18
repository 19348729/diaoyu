from dataclasses import dataclass
from typing import List, Dict

@dataclass(frozen=True)
class RodSeriesProfile:
    """鱼竿系列/型号 的官方参数配置库
    
    例如用户只要输入“化氏 - 一味EX”，系统就能自动获取它的调性、类型、以及可选的长度。
    无需用户手动填写这些繁琐的物理参数。
    """
    brand: str             # 品牌 (如 "化氏")
    series_name: str       # 系列名 (如 "一味EX")
    action: str            # 调性 (如 "28调", "19调")
    rod_type: str          # 种类 (如 "台钓竿", "路亚竿")
    available_lengths: List[float]  # 该系列官方发售的长度列表 (如 [3.6, 4.5, 5.4, 6.3, 7.2])
    target_fishes: List[str] # 主攻鱼种 (如 ["综合", "鲤鱼"])
    description: str = ""    # 简介

# ──────────────────────────────────────────────
#  TOP 经典商业鱼竿系列数据库 (Rod Matrix)
# ──────────────────────────────────────────────
ROD_DATABASE: Dict[str, RodSeriesProfile] = {
    # ── 化氏 (Hua Shi) ──
    "hs_yiwei_ex": RodSeriesProfile(
        brand="化氏",
        series_name="一味EX",
        action="28调",
        rod_type="台钓竿",
        available_lengths=[3.6, 4.5, 5.4, 6.3, 7.2, 8.1],
        target_fishes=["综合", "鲤鱼", "草鱼"],
        description="国内最具代表性的综合野钓竿，28偏37调，护线且腰力足。"
    ),
    "hs_longwen_li": RodSeriesProfile(
        brand="化氏",
        series_name="龙纹鲤",
        action="19调",
        rod_type="台钓竿",
        available_lengths=[4.5, 5.4, 6.3, 7.2, 8.1, 9.0],
        target_fishes=["大物", "青鱼", "鲟鱼"],
        description="专攻巨物，调性极硬，回鱼极快。"
    ),

    # ── 汉鼎 (Han Ding) ──
    "hd_luowengang": RodSeriesProfile(
        brand="汉鼎",
        series_name="螺纹钢",
        action="19调",
        rod_type="台钓竿",
        available_lengths=[4.5, 5.4, 6.3, 7.2, 8.1, 9.0, 10.0],
        target_fishes=["大物", "青鱼"],
        description="以皮实耐造、便宜大碗著称的网红大物竿。"
    ),
    "hd_yihao": RodSeriesProfile(
        brand="汉鼎",
        series_name="汉鼎1号",
        action="37调",
        rod_type="台钓竿",
        available_lengths=[2.7, 3.6, 4.5, 5.4, 6.3, 7.2],
        target_fishes=["鲫鱼", "白条"],
        description="新手入门级鲫鱼综合竿，极软护线。"
    ),

    # ── 达亿瓦 (Daiwa) ──
    "dw_bowen_li": RodSeriesProfile(
        brand="达亿瓦",
        series_name="波纹鲤",
        action="28调",
        rod_type="台钓竿",
        available_lengths=[3.6, 4.5, 5.4, 6.3, 7.2],
        target_fishes=["鲤鱼", "综合"],
        description="日系高端鲤鱼竿代表作，重量与腰力的完美平衡。"
    ),
    "dw_yige": RodSeriesProfile(
        brand="达亿瓦",
        series_name="一击",
        action="19调",
        rod_type="台钓竿",
        available_lengths=[4.5, 5.4, 6.3, 7.2],
        target_fishes=["综合", "黑坑"],
        description="主打黑坑抢鱼的硬调鱼竿。"
    ),

    # ── 禧玛诺 (Shimano) ──
    "xm_shuang_hong": RodSeriesProfile(
        brand="禧玛诺",
        series_name="爽风",
        action="37调",
        rod_type="台钓竿",
        available_lengths=[3.6, 4.5, 5.4, 6.3],
        target_fishes=["鲫鱼"],
        description="日系经典鲫鱼竿，手感轻盈，弧度优美。"
    ),

    # ── 光威 (Guang Wei) ──
    "gw_zhushan": RodSeriesProfile(
        brand="光威",
        series_name="竹山",
        action="37调",
        rod_type="台钓竿",
        available_lengths=[2.7, 3.6, 4.5, 5.4, 6.3],
        target_fishes=["综合"],
        description="国产玻璃钢/碳素复合老牌神竿，极其耐操，适合打粗。"
    ),
}
