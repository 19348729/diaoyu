"""
大师战术知识库清洗脚本
======================
将 `大师战术与配方百科全书.md` 解析为结构化 JSONL，供 RAG 检索使用。

输入:  d:/diaoyu/diaoyu/大师战术与配方百科全书.md
输出:  d:/diaoyu/diaoyu/data/master_kb.jsonl

字段规范 (每条):
{
  "id": "tactic_001",
  "title": "春钓小鲫鱼",
  "video_url": "https://www.bilibili.com/video/BV1v44y1N7QS/",
  "master": "刘志强",
  "fish": ["鲫鱼"],          # 列表，可能多个
  "season": "初春",           # 初春/暮春/初夏/盛夏/晚夏秋水/初冬/隆冬/未知
  "temp_min": 8,              # ℃
  "temp_max": 18,
  "pressure_state": "稳定",   # 稳定/上升/骤降/低压/高压/未知
  "line": "主线0.8号+子线0.4号+袖钩6号",
  "float_setup": "调7目钓2目，2.5克枣核漂",
  "rhythm": "每分钟1竿...",
  "flavor": "腥香微甜",
  "recipe": "野战蓝鲫50%+九一八30%+酒米20%",
  "source": "season"          # season(第二部分)/fish(第一部分)
}

清洗规则:
- 字段值出现 `暂无数据 / 未知 / --- / 空字符串` 视为无效
- 至少满足: master 有效 + (line 或 recipe) 有效 → 保留
"""
import json
import re
import os
import sys
from pathlib import Path
from typing import Optional

# Windows 控制台 utf-8
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "大师战术与配方百科全书.md"
OUT_DIR = ROOT / "data"
OUT = OUT_DIR / "master_kb.jsonl"

# ── 季节区段标题正则 ──
SEASON_HEADERS = {
    "初春时节": "初春",
    "暮春花谢": "暮春",
    "初夏温升": "初夏",
    "盛夏酷暑": "盛夏",
    "晚夏秋水": "晚夏秋水",
    "深秋寒霜": "深秋",
    "初冬寒潮": "初冬",
    "隆冬严寒": "隆冬",
}

# ── 鱼种区段标题正则 ──
FISH_HEADERS = {
    "鲫鱼专区": ["鲫鱼"],
    "鲤鱼专区": ["鲤鱼"],
    "草鱼专区": ["草鱼"],
    "鲢鱼专区": ["鲢鱼"],
    "鳙鱼专区": ["鳙鱼"],
    "白鲢专区": ["白鲢"],
    "花鲢专区": ["花鲢"],
    "青鱼专区": ["青鱼"],
    "翘嘴专区": ["翘嘴"],
    "翘嘴鲌专区": ["翘嘴", "翘嘴鲌"],
    "鳊鱼专区": ["鳊鱼"],
    "综合野钓/其他专区": [],
}

INVALID_TOKENS = {"", "暂无数据", "未知", "未知博主", "未知大师", "---", "—— ---", "—", "?~?℃", "未知季节"}


def is_invalid(s: Optional[str]) -> bool:
    if s is None:
        return True
    s2 = s.strip().strip("`").strip()
    return (not s2) or s2 in INVALID_TOKENS or s2.startswith("---")


def clean(s: Optional[str]) -> str:
    if s is None:
        return ""
    return s.replace("`", "").strip()


def parse_temp_range(text: str):
    """从形如 '14~20℃' 或 '0~10℃' 提取整数范围。"""
    m = re.search(r"(-?\d+)\s*~\s*(-?\d+)\s*[℃°]", text)
    if not m:
        return None, None
    try:
        return int(m.group(1)), int(m.group(2))
    except Exception:
        return None, None


def parse_pressure(text: str) -> str:
    """从环境/气压描述中归一化气压状态。"""
    if "气压上升" in text or "黄金窗口" in text or "📈" in text:
        return "上升"
    if "气压骤降" in text or "鱼口微弱" in text or "📉" in text:
        return "骤降"
    if "高压稳定" in text or "🔵" in text:
        return "高压稳定"
    if "低压稳定" in text or "微缺氧" in text or "🟡" in text:
        return "低压稳定"
    if "气压稳定" in text or "适宜垂钓" in text or "🟢" in text:
        return "稳定"
    return "未知"


def season_from_temp(t_min: Optional[int], t_max: Optional[int]) -> str:
    """根据气温区间反推季节段（用于第一部分鱼种区条目，因为它们没有季节标题）。"""
    if t_min is None or t_max is None:
        return "未知"
    avg = (t_min + t_max) / 2
    if avg <= 5:
        return "隆冬"
    if avg <= 12:
        return "初冬"
    if avg <= 18:
        return "初春"
    if avg <= 23:
        return "暮春"
    if avg <= 28:
        return "初夏"
    return "盛夏"


# ─────────────────────────────────────────────
#  第二部分: 季节表格解析
# ─────────────────────────────────────────────
TABLE_ROW_RE = re.compile(r"^\|\s*\[")


def parse_season_section(lines, start_idx, season):
    """从季节小节起始位置，向下扫描所有表格行，产出条目。
    返回 (records, next_idx)。"""
    records = []
    i = start_idx
    n = len(lines)
    while i < n:
        line = lines[i].rstrip()
        # 遇到下一个 ## 或 ### 退出
        if line.startswith("## ") or line.startswith("### "):
            break
        if TABLE_ROW_RE.match(line):
            row = _parse_season_row(line)
            if row:
                row["season"] = season
                row["source"] = "season"
                records.append(row)
        i += 1
    return records, i


def _parse_season_row(line: str) -> Optional[dict]:
    """解析单行季节表格。"""
    # 切分四列
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    if len(cells) < 4:
        return None
    col_video, col_env, col_setup, col_recipe = cells[:4]

    # 视频与大师
    m_url = re.search(r"\[([^\]]+)\]\(([^)]+)\)", col_video)
    title = m_url.group(1) if m_url else ""
    video_url = m_url.group(2) if m_url else ""
    m_master = re.search(r"\*\*主讲\*\*：`([^`]*)`", col_video)
    master = clean(m_master.group(1)) if m_master else ""

    # 气温与气压
    t_min, t_max = parse_temp_range(col_env)
    pressure_state = parse_pressure(col_env)

    # 线组/调漂/节奏
    line_eq = _extract_field(col_setup, r"\*\*线组\*\*：`?([^`<]*)`?")
    float_setup = _extract_field(col_setup, r"\*\*调漂\*\*：([^<]*?)(?=<br>|$)")
    rhythm = _extract_field(col_setup, r"\*\*节奏\*\*：([^<]*?)(?=<br>|$)")

    # 味型/细节
    flavor = _extract_field(col_recipe, r"\*\*味型\*\*：`?([^`<]*)`?")
    recipe = _extract_field(col_recipe, r"\*\*细节\*\*：([^<]*?)(?=<br>|$)")

    return {
        "title": title,
        "video_url": video_url,
        "master": master,
        "fish": [],  # 第二部分不区分鱼种，留空，由检索器降级处理
        "temp_min": t_min,
        "temp_max": t_max,
        "pressure_state": pressure_state,
        "line": clean(line_eq),
        "float_setup": clean(float_setup),
        "rhythm": clean(rhythm),
        "flavor": clean(flavor),
        "recipe": clean(recipe),
    }


def _extract_field(text: str, pat: str) -> str:
    m = re.search(pat, text)
    if not m:
        return ""
    return m.group(1).strip(" `")


# ─────────────────────────────────────────────
#  第一部分: 鱼种区块解析
# ─────────────────────────────────────────────
TACTIC_HEADER_RE = re.compile(r"^>\s*####\s*🏷️\s*战术\s*\d+\s*：\s*\[([^\]]+)\]\(([^)]+)\)")


def parse_fish_section(lines, start_idx, fish_list):
    """从鱼种小节起始位置，逐战术块解析，返回 (records, next_idx)。"""
    records = []
    i = start_idx
    n = len(lines)
    cur = None
    while i < n:
        line = lines[i].rstrip()
        if line.startswith("## ") or line.startswith("### "):
            if cur:
                records.append(cur)
                cur = None
            break
        m = TACTIC_HEADER_RE.match(line)
        if m:
            if cur:
                records.append(cur)
            cur = {
                "title": m.group(1),
                "video_url": m.group(2),
                "master": "",
                "fish": list(fish_list),
                "temp_min": None,
                "temp_max": None,
                "pressure_state": "未知",
                "line": "",
                "float_setup": "",
                "rhythm": "",
                "flavor": "",
                "recipe": "",
                "source": "fish",
            }
        elif cur is not None:
            _fill_fish_field(cur, line)
        i += 1
    if cur:
        records.append(cur)
    return records, i


FIELD_PATTERNS = [
    ("master_env", re.compile(r"\*\*主讲大师\*\*：`([^`]*)`\s*\|\s*\*\*适用环境\*\*：(.*)$")),
    ("line", re.compile(r"\*\*🎣 大师线组配比\*\*：`([^`]*)`")),
    ("float_setup", re.compile(r"\*\*🌊 调漂与浮漂动作\*\*：(.*)$")),
    ("rhythm", re.compile(r"\*\*⏱️ 作钓实操节奏\*\*：(.*)$")),
    ("flavor_recipe", re.compile(r"\*\*🧪 独门味型与配比\*\*：`([^`]*)`\s*——\s*(.*)$")),
]


def _fill_fish_field(cur, line):
    for key, pat in FIELD_PATTERNS:
        m = pat.search(line)
        if not m:
            continue
        if key == "master_env":
            cur["master"] = clean(m.group(1))
            env = m.group(2)
            t_min, t_max = parse_temp_range(env)
            cur["temp_min"] = t_min
            cur["temp_max"] = t_max
            cur["pressure_state"] = parse_pressure(env)
        elif key == "flavor_recipe":
            cur["flavor"] = clean(m.group(1))
            cur["recipe"] = clean(m.group(2))
        else:
            cur[key] = clean(m.group(1))
        return


# ─────────────────────────────────────────────
#  主流程
# ─────────────────────────────────────────────
def quality_score(rec) -> int:
    """有效字段计数, 用于过滤低质条目。"""
    score = 0
    if not is_invalid(rec.get("master")):
        score += 1
    if not is_invalid(rec.get("line")):
        score += 1
    if not is_invalid(rec.get("recipe")):
        score += 1
    if not is_invalid(rec.get("rhythm")):
        score += 1
    if not is_invalid(rec.get("float_setup")):
        score += 1
    if not is_invalid(rec.get("flavor")):
        score += 1
    return score


def normalize(rec) -> dict:
    """对所有可能的"暂无数据"占位做空字符串归一化。"""
    for k in ("master", "line", "float_setup", "rhythm", "flavor", "recipe", "title"):
        v = rec.get(k, "")
        if is_invalid(v):
            rec[k] = ""
        else:
            rec[k] = clean(v)
    if rec.get("source") == "fish" and not rec.get("season"):
        rec["season"] = season_from_temp(rec.get("temp_min"), rec.get("temp_max"))
    if not rec.get("season"):
        rec["season"] = "未知"
    return rec


def main():
    if not SRC.exists():
        print(f"[ERROR] 未找到源文件: {SRC}")
        sys.exit(1)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    text = SRC.read_text(encoding="utf-8")
    lines = text.splitlines()
    n = len(lines)
    all_records = []

    i = 0
    while i < n:
        line = lines[i].strip()
        # 鱼种区
        m_fish = re.match(r"^### 🎯\s+([^\s(（]+)\s*(?:\(|（)", line)
        if m_fish:
            label = m_fish.group(1).strip()
            # 找到键
            key = None
            for k in FISH_HEADERS:
                if k.startswith(label) or label.startswith(k):
                    key = k
                    break
            fish_list = FISH_HEADERS.get(key, [])
            recs, next_i = parse_fish_section(lines, i + 1, fish_list)
            all_records.extend(recs)
            i = next_i
            continue
        # 季节区
        m_season = re.match(r"^### [^\s]+\s+([^\s(（]+)\s*(?:\(|（)", line)
        if m_season:
            label = m_season.group(1).strip()
            season = SEASON_HEADERS.get(label)
            if season:
                recs, next_i = parse_season_section(lines, i + 1, season)
                all_records.extend(recs)
                i = next_i
                continue
        i += 1

    # 归一化 + 过滤
    cleaned = []
    for idx, r in enumerate(all_records):
        r = normalize(r)
        score = quality_score(r)
        # 准入门槛: 有大师 且 (有线组 或 有配方)
        if not r.get("master"):
            continue
        if not (r.get("line") or r.get("recipe")):
            continue
        r["id"] = f"tactic_{idx + 1:04d}"
        r["quality"] = score
        cleaned.append(r)

    with OUT.open("w", encoding="utf-8") as f:
        for r in cleaned:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # 统计
    by_season = {}
    by_source = {}
    for r in cleaned:
        by_season[r["season"]] = by_season.get(r["season"], 0) + 1
        by_source[r["source"]] = by_source.get(r["source"], 0) + 1

    print(f"[OK] 输出: {OUT}")
    print(f"[OK] 总条数: {len(cleaned)} (源 {len(all_records)} → 清洗 {len(cleaned)})")
    print(f"[OK] 按来源: {by_source}")
    print(f"[OK] 按季节: {by_season}")
    print(f"[OK] 抽样:")
    for r in cleaned[:3]:
        print(f"  - [{r['id']}] {r['master']} | {r['season']} {r['temp_min']}~{r['temp_max']}℃ | {r['title'][:30]}")


if __name__ == "__main__":
    main()
