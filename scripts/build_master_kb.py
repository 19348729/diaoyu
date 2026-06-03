"""
大师战术知识库构建脚本（v2 · 直读结构化 CVA JSON）
==================================================
将上游采集管线产出的干净结构化知识库 `data/master_kb_source.json`
（CVA Schema：Condition-Variable-Action）映射为检索器消费的
`data/master_kb.jsonl`。

为什么是 v2（重要架构变更）
--------------------------
旧版 v1 解析的是「渲染后的百科全书.md」，走 JSON→Markdown→正则→JSONL
的有损往返，导致 72% 气压字段在鱼种区被渲染环节丢弃、且同一视频在
鱼种区/季节区被重复计数。

v2 直接消费上游 `knowledge_base.json`（已是干净结构化 JSON、按 bv_id 去重），
彻底消除正则丢字段问题，气压/水温/线组/配方完整度大幅提升。

输入:  data/master_kb_source.json   （上游 diaoyu-paqu 的 knowledge_base.json 副本）
输出:  data/master_kb.jsonl

检索器(domain/master_kb.py)消费的字段契约:
  fish[](中文) / season(中文枚举) / temp_min,temp_max(int) /
  pressure_state(中文) / quality(int) + 展示字段
  master,title,video_url,line,float_setup,rhythm,flavor,recipe
"""
import json
import sys
from pathlib import Path

# Windows 控制台 utf-8
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "master_kb_source.json"
OUT = ROOT / "data" / "master_kb.jsonl"

# ── CVA 英文季节枚举 → 检索器中文季节桶 ──
# 检索器查询侧主要用 _season_from_temp 产出 {隆冬,初冬,初春,暮春,初夏,盛夏}，
# 故映射尽量落到这些桶，温区(temp)匹配作为主力兜底。
SEASON_MAP = {
    "spring": "初春",
    "late_spring": "暮春",
    "early_summer": "初夏",
    "summer": "盛夏",
    "late_summer": "晚夏秋水",
    "early_autumn": "晚夏秋水",
    "autumn": "晚夏秋水",
    "late_autumn": "初冬",
    "early_winter": "初冬",
    "winter": "隆冬",
}

# ── CVA 英文气压枚举 → 检索器中文气压状态 ──
PRESSURE_MAP = {
    "rising": "上升",
    "stable_high": "高压稳定",
    "stable": "稳定",
    "stable_low": "低压稳定",
    "falling": "骤降",
    "fluctuating": "",   # 波动无对应稳定态，留空不参与气压加分
}

INVALID = {"", "暂无数据", "未知", "未知博主", "未知大师", "---", "—", "无", "None", "null"}


def clean(v) -> str:
    """归一化字符串字段，占位符视为空。"""
    if v is None:
        return ""
    if isinstance(v, list):
        v = "、".join(str(x).strip() for x in v if str(x).strip())
    s = str(v).replace("`", "").strip()
    return "" if s in INVALID else s


def to_int(v):
    try:
        i = int(v)
        return i if i != 0 else None   # 0 在本数据里是「未提取」的占位
    except (TypeError, ValueError):
        return None


def build_recipe(bait: dict) -> str:
    """配方 = 品牌 + 配比细节 合并。"""
    brands = clean(bait.get("main_brands"))
    details = clean(bait.get("mix_details"))
    if brands and details:
        return f"{details}（品牌: {brands}）"
    return details or brands


def map_record(rec: dict, idx: int):
    """单条 CVA 记录 → jsonl 记录；不满足准入门槛返回 None。"""
    cva = rec.get("cva_rules")
    if not isinstance(cva, dict):
        return None

    climate = cva.get("climate_conditions") or {}
    tactical = cva.get("tactical_actions") or {}
    bait = cva.get("bait_recipe") or {}

    fish = [clean(f) for f in (cva.get("target_fish") or []) if clean(f)]
    season = SEASON_MAP.get(clean(climate.get("season")), "")
    temp_min = to_int(climate.get("water_temp_min"))
    temp_max = to_int(climate.get("water_temp_max"))
    pressure_state = PRESSURE_MAP.get(clean(climate.get("pressure_trend")), "")

    line = clean(tactical.get("line_setup"))
    float_setup = clean(tactical.get("float_tactic"))
    rhythm = clean(tactical.get("execution_tempo"))
    flavor = clean(bait.get("profile_flavor"))
    recipe = build_recipe(bait)

    # 来源标记：article(图文攻略) / video(B站视频)
    bv = str(rec.get("bv_id", ""))
    source_type = "article" if bv.startswith("art_") else "video"

    # ── 准入门槛（不再用 master 把关，因图文源本无主讲大师）──
    # 必须：① 至少一个可执行战术字段  ② 至少一个可检索条件
    has_action = bool(line or recipe or float_setup or rhythm)
    has_condition = bool(fish or season or temp_min is not None)
    if not (has_action and has_condition):
        return None

    # 数据完整度（平局打破用，0~6）
    quality = sum(bool(x) for x in (clean(cva.get("master")), line, float_setup, rhythm, flavor, recipe))

    return {
        "id": f"kb_{idx:04d}",
        "source_type": source_type,
        "master": clean(cva.get("master")),
        "title": clean(rec.get("video_title")),
        "video_url": clean(rec.get("video_url")),
        "fish": fish,
        "season": season,
        "temp_min": temp_min,
        "temp_max": temp_max,
        "pressure_state": pressure_state,
        "line": line,
        "float_setup": float_setup,
        "rhythm": rhythm,
        "flavor": flavor,
        "recipe": recipe,
        "quality": quality,
    }


def main():
    if not SRC.exists():
        print(f"[ERROR] 未找到源文件: {SRC}")
        print("        请从上游 diaoyu-paqu/fishing_knowledge/knowledge_base.json 复制过来。")
        sys.exit(1)

    db = json.loads(SRC.read_text(encoding="utf-8"))
    out_records = []
    idx = 1
    for rec in db:
        m = map_record(rec, idx)
        if m:
            out_records.append(m)
            idx += 1

    with OUT.open("w", encoding="utf-8") as f:
        for r in out_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # 统计
    n = len(out_records)
    by_source = {}
    pressure_known = 0
    fish_known = 0
    for r in out_records:
        by_source[r["source_type"]] = by_source.get(r["source_type"], 0) + 1
        if r["pressure_state"]:
            pressure_known += 1
        if r["fish"]:
            fish_known += 1
    print(f"[OK] 输出: {OUT}")
    print(f"[OK] 源 {len(db)} 条 → 准入 {n} 条")
    print(f"[OK] 按来源: {by_source}")
    print(f"[OK] 气压非空: {pressure_known}/{n} ({pressure_known*100//max(n,1)}%)")
    print(f"[OK] 鱼种非空: {fish_known}/{n} ({fish_known*100//max(n,1)}%)")
    print("[OK] 抽样:")
    for r in out_records[:3]:
        print(f"  - [{r['source_type']}] {r['fish']} {r['season']} {r['temp_min']}~{r['temp_max']}℃ 气压{r['pressure_state'] or '-'} | {r['title'][:24]}")


if __name__ == "__main__":
    main()
