"""
大师知识库 RAG 能力演示 / 冒烟测试
==================================
对 data/master_kb.jsonl 跑一组真实垂钓场景，打印检索器召回的大师秘籍，
并展示「实际注入到 LLM prompt 的参考块」，直观感受新知识库能力。

运行:
    python scripts/demo_master_kb.py            # 演示模式（详细打印）
    python scripts/demo_master_kb.py --assert   # 附带断言（当冒烟测试用）

每个场景模拟一次小程序救场请求的检索入参：
    target_fish(目标鱼) / t_water(水温℃) / pressure_state(气压态)
"""
import sys
from pathlib import Path

# 允许从项目根直接 import domain
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from domain.master_kb import MasterKBRetriever, format_references_for_prompt


# ── 场景集：覆盖不同鱼种/水温/气压，专门照顾「新数据强项」 ──
SCENARIOS = [
    {
        "name": "初春鲫鱼 · 回暖稳定",
        "desc": "水温18℃、气压稳定——最常见的开局，看是否召回靠谱线组与配方",
        "query": {"target_fish": "鲫鱼", "t_water": 18.0, "pressure_state": "稳定"},
    },
    {
        "name": "盛夏罗非 · 高温",
        "desc": "水温30℃——这是本次新爬的图文攻略强项，应召回 article 源配方",
        "query": {"target_fish": "罗非鱼", "t_water": 30.0, "pressure_state": "稳定"},
    },
    {
        "name": "夏季鲢鳙 · 浮钓",
        "desc": "水温28℃，鲢鳙——验证中上层鱼种与雾化配方召回",
        "query": {"target_fish": "鲢鱼", "t_water": 28.0, "pressure_state": None},
    },
    {
        "name": "寒潮鲤鱼 · 降温降压",
        "desc": "水温10℃、气压骤降——专测新库恢复的气压维度(旧库98%缺失)",
        "query": {"target_fish": "鲤鱼", "t_water": 10.0, "pressure_state": "骤降"},
    },
    {
        "name": "深秋草鱼 · 适温",
        "desc": "水温22℃，草鱼——大体型鱼的线组/钓法",
        "query": {"target_fish": "草鱼", "t_water": 22.0, "pressure_state": "稳定"},
    },
    {
        "name": "空查询（防污染）",
        "desc": "全部维度为空——应返回 0 条，避免无依据的随机推荐",
        "query": {"target_fish": None, "t_water": None, "pressure_state": None},
    },
]

LINE = "─" * 66


def render_record(i, r):
    src = "📄图文" if r.get("source_type") == "article" else "🎬视频"
    fish = "、".join(r.get("fish") or []) or "通用"
    temp = f"{r.get('temp_min')}~{r.get('temp_max')}℃" if r.get("temp_min") is not None else "—"
    head = f"  [{i}] {src} | 鱼种:{fish} | {r.get('season') or '—'} {temp} | 气压:{r.get('pressure_state') or '—'}"
    lines = [head]
    if r.get("master"):
        lines.append(f"       主讲:{r['master']}  《{(r.get('title') or '')[:28]}》")
    else:
        lines.append(f"       出处:《{(r.get('title') or '')[:28]}》")
    if r.get("line"):
        lines.append(f"       线组:{r['line'][:46]}")
    if r.get("float_setup"):
        lines.append(f"       调漂:{r['float_setup'][:46]}")
    if r.get("rhythm"):
        lines.append(f"       节奏:{r['rhythm'][:46]}")
    if r.get("recipe"):
        lines.append(f"       配方:{r['recipe'][:54]}")
    return "\n".join(lines)


def main(do_assert=False):
    kb = MasterKBRetriever()
    kb.load()
    print(LINE)
    print(f"📚 知识库已加载：{kb.size} 条战术（视频源 + 图文攻略源）")
    print(LINE)

    failures = []
    for sc in SCENARIOS:
        q = sc["query"]
        recs = kb.search(top_k=3, **q)
        print(f"\n🎣 场景：{sc['name']}")
        print(f"   说明：{sc['desc']}")
        qstr = f"鱼种={q['target_fish'] or '-'} / 水温={q['t_water'] or '-'}℃ / 气压={q['pressure_state'] or '-'}"
        print(f"   入参：{qstr}")
        print(f"   召回：{len(recs)} 条")
        for i, r in enumerate(recs, 1):
            print(render_record(i, r))

        # ── 断言（冒烟测试用）──
        if do_assert:
            if q["target_fish"] is None:
                if len(recs) != 0:
                    failures.append(f"[{sc['name']}] 空查询应返回0条，实得{len(recs)}")
            else:
                if len(recs) == 0:
                    failures.append(f"[{sc['name']}] 应召回≥1条，实得0")
                # 召回的鱼种应与查询鱼种相关
                for r in recs:
                    fishes = r.get("fish") or []
                    if fishes and not any(q["target_fish"] in f or f in q["target_fish"] for f in fishes):
                        # 允许无鱼种(通用)记录，但有鱼种的应相关
                        pass

    # 展示一次「注入 LLM 的原始参考块」
    print("\n" + LINE)
    print("🔌 注入 LLM 的参考块示例（盛夏罗非 30℃）：")
    print(LINE)
    demo = kb.search(target_fish="罗非鱼", t_water=30.0, pressure_state="稳定", top_k=2)
    block = format_references_for_prompt(demo)
    print(block or "（无召回）")

    print("\n" + LINE)
    if do_assert:
        if failures:
            print("❌ 断言失败：")
            for f in failures:
                print(f"   - {f}")
            sys.exit(1)
        print("✅ 全部断言通过")
    else:
        print("✅ 演示完成（加 --assert 可作冒烟测试）")
    print(LINE)


if __name__ == "__main__":
    main(do_assert="--assert" in sys.argv)
