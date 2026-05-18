from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class Rod:
    """鱼竿实体"""
    id: str
    length: float          # 长度，单位米，如 4.5, 5.4
    action: str            # 调性，如 "28调", "37调", "19调"
    type: str              # 种类，如 "台钓竿", "路亚竿", "矶钓竿", "溪流竿"
    brand: str = ""        # 品牌，如 "化氏", "达亿瓦"
    name: str = ""         # 型号/名称，如 "一味EX"

@dataclass
class MainLine:
    """主线组实体 (包含太空豆、漂座、铅皮座)"""
    id: str
    size: float            # 主线号数，如 1.5, 2.0
    length: float          # 适配竿长，如 4.5
    brand: str = ""        # 品牌

@dataclass
class SubLineHook:
    """子线双钩实体 (子线与鱼钩是绑在一起的)"""
    id: str
    line_size: float       # 子线号数，如 0.8, 1.0
    hook_type: str         # 钩型，如 "袖钩", "伊势尼", "伊豆"
    hook_size: float       # 钩号，如 3.0, 4.0
    has_barb: bool = False # 是否有倒刺

@dataclass
class Float:
    """浮漂实体"""
    id: str
    name: str              # 漂名，如 "大物漂", "鲫鱼漂"
    material: str          # 材质，如 "芦苇", "巴尔杉木", "纳米"
    shape: str             # 漂身形状，如 "枣核型", "细长身"
    lead_weight: float     # 吃铅量(克)，如 1.5, 3.0

@dataclass
class UserInventory:
    """用户的数字钓箱 (云端装备库)
    
    用于 AI 在提供作钓建议和救场方案时，基于用户实际拥有的物资进行精准匹配，
    而非给出用户无法执行的理论建议。
    """
    user_id: str
    rods: List[Rod] = field(default_factory=list)
    main_lines: List[MainLine] = field(default_factory=list)
    sub_line_hooks: List[SubLineHook] = field(default_factory=list)
    floats: List[Float] = field(default_factory=list)
    
    # 这里存储 domain/baits.py 中 BAIT_DATABASE 里的饵料 ID (如 "lg_918_yezhan")
    bait_ids: List[str] = field(default_factory=list)

    def add_rod(self, rod: Rod):
        """添加鱼竿"""
        self.rods.append(rod)
        
    def add_main_line(self, main_line: MainLine):
        """添加主线组"""
        self.main_lines.append(main_line)
        
    def add_sub_line_hook(self, sub_hook: SubLineHook):
        """添加子线双钩"""
        self.sub_line_hooks.append(sub_hook)

    def add_float(self, float_item: Float):
        """添加浮漂"""
        self.floats.append(float_item)
        
    def add_bait(self, bait_id: str):
        """添加饵料资产 (去重)"""
        if bait_id not in self.bait_ids:
            self.bait_ids.append(bait_id)
            
    def remove_bait(self, bait_id: str):
        """消耗/移除饵料资产"""
        if bait_id in self.bait_ids:
            self.bait_ids.remove(bait_id)

    def get_max_rod_length(self) -> float:
        """获取用户拥有的最长鱼竿长度 (用于判断能否钓深水)"""
        if not self.rods:
            return 0.0
        return max(r.length for r in self.rods)
        
    def get_max_line_strength(self) -> float:
        """获取用户拥有的最大主线号数 (用于评估断线风险)"""
        if not self.main_lines:
            return 0.0
        return max(l.size for l in self.main_lines)

# ──────────────────────────────────────────────
#  测试与初始化帮助函数
# ──────────────────────────────────────────────
def create_mock_inventory(user_id: str) -> UserInventory:
    """创建一个模拟的初学者数字钓箱，用于测试 AI 逻辑。"""
    inv = UserInventory(user_id=user_id)
    
    # 初始化两把竿：一把短竿钓鲫鱼，一把中长竿兼顾
    inv.add_rod(Rod(id="r1", length=3.6, action="37调", type="台钓竿", brand="光威", name="竹山"))
    inv.add_rod(Rod(id="r2", length=4.5, action="28调", type="台钓竿", brand="化氏", name="一味"))
    
    # 初始化两套主线
    inv.add_main_line(MainLine(id="m1", size=1.0, length=3.6))
    inv.add_main_line(MainLine(id="m2", size=1.5, length=4.5))
    
    # 初始化几套子线双钩
    inv.add_sub_line_hook(SubLineHook(id="s1", line_size=0.6, hook_type="袖钩", hook_size=3, has_barb=False))
    inv.add_sub_line_hook(SubLineHook(id="s2", line_size=1.0, hook_type="伊豆", hook_size=4, has_barb=True))
    
    # 初始化浮漂
    inv.add_float(Float(id="f1", name="浅水漂", material="芦苇", shape="细长身", lead_weight=1.2))
    inv.add_float(Float(id="f2", name="大底漂", material="纳米", shape="枣核型", lead_weight=3.5))

    # 初始化一些基础老鬼/化氏饵料
    inv.add_bait("lg_918_yezhan")
    inv.add_bait("lg_yeluans_blue")
    inv.add_bait("hs_dabanjie")
    inv.add_bait("state_lasi_fen")
    
    return inv
