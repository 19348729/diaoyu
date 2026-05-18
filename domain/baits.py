from dataclasses import dataclass, field
from typing import List, Dict

@dataclass(frozen=True)
class BaitProfile:
    """商品饵料属性定义
    
    Attributes:
        brand:          品牌名称 (如：老鬼、化氏、天元等)
        name:           单品名称 (如：九一八野战篇、大板鲫等)
        flavor:         主要味型 (如：麸香、浓腥、腥香、酸臭等)
        weight_class:   比重状态 (如：大比重、轻比重、状态饵)
        target_fishes:  主要作钓目标鱼种
        best_seasons:   最适宜季节 (spring, summer, autumn, winter 或 all)
        is_additive:    是否为状态饵/添加剂 (如：拉丝粉、雪花粉、轻麸)
        description:    一句话特点描述
    """
    brand: str
    name: str
    flavor: str
    weight_class: str
    target_fishes: List[str]
    best_seasons: List[str]
    is_additive: bool = False
    description: str = ""

# ──────────────────────────────────────────────
#  TOP 经典商业饵料数据库 (Bait Matrix)
# ──────────────────────────────────────────────
BAIT_DATABASE: Dict[str, BaitProfile] = {
    # ── 老鬼 (Lao Gui) ──
    "lg_918_yezhan": BaitProfile(
        brand="老鬼",
        name="九一八野战篇",
        flavor="麸香",
        weight_class="大比重",
        target_fishes=["鲫鱼", "鲤鱼", "草鱼", "鳊鱼"],
        best_seasons=["all"],
        description="国内最经典的野钓综合饵，天然麦麸香，主打大个态和留底。"
    ),
    "lg_yeluans_blue": BaitProfile(
        brand="老鬼",
        name="野战蓝鲫",
        flavor="香腥",
        weight_class="中比重",
        target_fishes=["鲫鱼", "鲤鱼"],
        best_seasons=["all"],
        description="单开即爆护的神饵，拉丝粉含量高，雾化好，四季通用。"
    ),
    "lg_sugong_2": BaitProfile(
        brand="老鬼",
        name="速攻2号",
        flavor="奶香/甜香",
        weight_class="轻比重",
        target_fishes=["鲫鱼", "鲢鳙"],
        best_seasons=["spring", "summer", "autumn"],
        is_additive=True,
        description="老三样核心状态饵，可减轻比重，增加雾化，自带诱人奶香。"
    ),
    "lg_luoli": BaitProfile(
        brand="老鬼",
        name="螺鲤 (1/2/3号)",
        flavor="腥/香/酵",
        weight_class="超大比重",
        target_fishes=["鲤鱼", "青鱼"],
        best_seasons=["summer", "autumn"],
        description="底钓大物必备，含大量田螺肉和动植物蛋白，入水后直达水底。"
    ),
    
    # ── 化氏 (Hua Shi) ──
    "hs_dabanjie": BaitProfile(
        brand="化氏",
        name="大板鲫",
        flavor="谷物香",
        weight_class="中大比重",
        target_fishes=["鲫鱼"],
        best_seasons=["all"],
        description="主攻大体型鲫鱼，谷物天然香味，诱鱼持久不乱杂鱼。"
    ),
    "hs_4_6": BaitProfile(
        brand="化氏",
        name="4号/6号鲫",
        flavor="浓腥/腥香",
        weight_class="轻比重",
        target_fishes=["鲫鱼"],
        best_seasons=["winter", "spring"],
        description="低温期野钓利器，动物蛋白含量极高，状态极佳的拉饵。"
    ),
    "hs_chiweiqing": BaitProfile(
        brand="化氏",
        name="赤尾青",
        flavor="极腥",
        weight_class="轻比重",
        target_fishes=["罗非鱼", "鲫鱼", "鲤鱼"],
        best_seasons=["winter", "spring"],
        is_additive=True,
        description="纯正南极磷虾粉，极度腥香，提腥诱鱼神添加剂。"
    ),

    # ── 天元 (Tian Yuan) ──
    "ty_hongchong_fengbao": BaitProfile(
        brand="天元",
        name="红虫风暴",
        flavor="浓腥",
        weight_class="轻比重",
        target_fishes=["鲫鱼", "鲤鱼"],
        best_seasons=["winter", "spring", "autumn"],
        description="含有真实冻干红虫，腥味穿透力极强，冷水期抢口首选。"
    ),
    "ty_daban_jie": BaitProfile(
        brand="天元",
        name="天元大板鲫",
        flavor="甜香",
        weight_class="中比重",
        target_fishes=["鲫鱼"],
        best_seasons=["all"],
        description="状态完美的鲫鱼拉饵，散落性好，诱钓结合。"
    ),
    "ty_fuxiang_juexisha": BaitProfile(
        brand="天元",
        name="浮水鲢鳙(绝杀)",
        flavor="酸臭/草莓",
        weight_class="超轻比重",
        target_fishes=["鲢鳙"],
        best_seasons=["summer", "autumn"],
        description="极度雾化，迅速在水体中上层形成立体雾化带，专攻大头。"
    ),

    # ── 南北/广东特色 (Nan Bei & Guangdong) ──
    "nb_nanbeiling": BaitProfile(
        brand="南北",
        name="南北钓鲮",
        flavor="腥香",
        weight_class="大比重",
        target_fishes=["土鲮", "鲮鱼"],
        best_seasons=["summer", "autumn"],
        description="广东台钓土鲮鼻祖饵，针对鲮鱼下口刮食特性研制。"
    ),
    "local_huashengku": BaitProfile(
        brand="基础料",
        name="纯花生枯",
        flavor="浓香",
        weight_class="大比重",
        target_fishes=["土鲮", "草鱼", "鲤鱼"],
        best_seasons=["all"],
        is_additive=True,
        description="榨油后的花生饼打粉，天然纯香，打窝及钓土鲮的绝对核心料。"
    ),
    "local_dongliao": BaitProfile(
        brand="特色",
        name="冷冻活饵(肝/腥)",
        flavor="腥臭/肝味",
        weight_class="中大比重",
        target_fishes=["罗非鱼", "塘鲺"],
        best_seasons=["summer", "autumn"],
        description="广东赌塘钓罗非必杀技，鸡肝鸭肝秋刀鱼绞碎冷冻，生猛诱惑。"
    ),

    # ── 西部风 (Xi Bu Feng) ──
    "xbf_laotan_yumi": BaitProfile(
        brand="西部风",
        name="老坛发酵玉米",
        flavor="酸甜发酵",
        weight_class="大比重",
        target_fishes=["草鱼", "鲤鱼", "青鱼"],
        best_seasons=["summer", "autumn"],
        description="老坛工艺发酵，酸甜适口，避小鱼专攻大体型底栖鱼。"
    ),
    "xbf_niub_jiyu": BaitProfile(
        brand="西部风",
        name="牛B鲫",
        flavor="麝香/甜香",
        weight_class="液态/粉状",
        target_fishes=["鲫鱼"],
        best_seasons=["all"],
        is_additive=True,
        description="著名的泡酒米添加剂，穿透力极强，打窝留鱼神器。"
    ),

    # ── 基础状态饵 & 活饵 ──
    "basic_hongchong": BaitProfile(
        brand="基础活饵",
        name="鲜活红虫/蚯蚓",
        flavor="活体肉腥",
        weight_class="大比重",
        target_fishes=["鲫鱼", "塘鲺", "黄颡鱼"],
        best_seasons=["winter", "spring"],
        description="万能活造化，低温期鱼类无法抗拒的高蛋白活体诱惑。"
    ),
    "state_lasi_fen": BaitProfile(
        brand="状态辅料",
        name="拉丝粉",
        flavor="无味",
        weight_class="状态饵",
        target_fishes=["all"],
        best_seasons=["all"],
        is_additive=True,
        description="增加面饵粘度和拉丝网络，开拉饵必不可少的蛋白纤维。"
    ),
    "state_xuehua_fen": BaitProfile(
        brand="状态辅料",
        name="雪花粉",
        flavor="薯香",
        weight_class="极轻比重",
        target_fishes=["all"],
        best_seasons=["all"],
        is_additive=True,
        description="极大地减轻饵料比重，增加饵团入水后的膨胀和层层剥落感。"
    )
}
