"""
大师战术知识库检索器 (Master Tactics Retriever)
================================================
按 (鱼种 / 季节 / 气温 / 气压状态) 维度从 data/master_kb.jsonl
召回 Top-K 大师秘籍，注入到 LLM prompt 中。

设计要点:
- 进程级单例懒加载, 避免每次请求都 IO
- 评分制: 不同维度命中给不同权重, 最终按总分排序取 Top-K
- 任意维度都可缺省: 缺省的维度跳过加分, 不影响其他维度命中
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import List, Optional

# 数据文件位置
_KB_PATH = Path(__file__).resolve().parent.parent / "data" / "master_kb.jsonl"

# ── 季节归一化映射 ──
_SEASON_ALIASES = {
    "spring": "初春", "early_spring": "初春",
    "late_spring": "暮春",
    "summer": "盛夏", "early_summer": "初夏", "mid_summer": "盛夏",
    "autumn": "晚夏秋水", "fall": "晚夏秋水",
    "winter": "隆冬", "early_winter": "初冬", "deep_winter": "隆冬",
}

# ── 月份 → 季节 兜底 ──
_MONTH_TO_SEASON = {
    1: "隆冬", 2: "隆冬", 3: "初春", 4: "暮春",
    5: "初夏", 6: "盛夏", 7: "盛夏", 8: "盛夏",
    9: "晚夏秋水", 10: "晚夏秋水", 11: "初冬", 12: "隆冬",
}

# ── 气压标签 → 知识库气压状态 ──
_PRESSURE_TAG_MAP = {
    "STATUS_PRESSURE_CRASH": "骤降",
    "STATUS_PRESSURE_DROPPING": "骤降",
    "STATUS_PRESSURE_RISING": "上升",
    "STATUS_PRESSURE_STABLE": "稳定",
    "气压骤降": "骤降",
    "气压下降": "骤降",
    "气压上升": "上升",
    "气压稳定": "稳定",
}


def _season_from_temp(t: Optional[float]) -> Optional[str]:
    if t is None:
        return None
    if t <= 5:
        return "隆冬"
    if t <= 12:
        return "初冬"
    if t <= 18:
        return "初春"
    if t <= 23:
        return "暮春"
    if t <= 28:
        return "初夏"
    return "盛夏"


def _normalize_season(season: Optional[str]) -> Optional[str]:
    if not season:
        return None
    s = season.strip()
    if s in _SEASON_ALIASES:
        return _SEASON_ALIASES[s]
    # 已经是中文季节直接返回
    if s in {"初春", "暮春", "初夏", "盛夏", "晚夏秋水", "深秋", "初冬", "隆冬"}:
        return s
    return None


def _normalize_pressure(tag_or_state: Optional[str]) -> Optional[str]:
    if not tag_or_state:
        return None
    s = tag_or_state.strip()
    if s in _PRESSURE_TAG_MAP:
        return _PRESSURE_TAG_MAP[s]
    if s in {"上升", "骤降", "稳定", "高压稳定", "低压稳定"}:
        return s
    return None


class MasterKBRetriever:
    """大师战术知识库检索器, 进程级单例。"""

    _instance: Optional["MasterKBRetriever"] = None
    _lock = threading.Lock()

    def __init__(self, kb_path: Optional[Path] = None):
        self._kb_path = Path(kb_path) if kb_path else _KB_PATH
        self._records: List[dict] = []
        self._loaded = False

    # ── 单例访问 ──
    @classmethod
    def get(cls) -> "MasterKBRetriever":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    inst = cls()
                    inst.load()
                    cls._instance = inst
        return cls._instance

    def load(self) -> None:
        if self._loaded:
            return
        if not self._kb_path.exists():
            self._records = []
            self._loaded = True
            return
        records = []
        with self._kb_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        self._records = records
        self._loaded = True

    @property
    def size(self) -> int:
        return len(self._records)

    # ── 评分检索 ──
    def search(
        self,
        target_fish: Optional[str] = None,
        season: Optional[str] = None,
        t_water: Optional[float] = None,
        pressure_state: Optional[str] = None,
        top_k: int = 3,
    ) -> List[dict]:
        """按多维度过滤打分, 返回 Top-K 秘籍。

        参数全部可选, 缺省维度不参与过滤; 全部为空时返回 [] 避免污染。
        """
        if not self._loaded:
            self.load()
        if not self._records:
            return []
        # 全部维度都没传, 不做随机推荐
        if all(x is None for x in (target_fish, season, t_water, pressure_state)):
            return []

        season_norm = _normalize_season(season) or _season_from_temp(t_water)
        pressure_norm = _normalize_pressure(pressure_state)

        scored = []
        for rec in self._records:
            score = 0
            # 1. 鱼种命中 (+5, 鱼种是最强约束)
            if target_fish and rec.get("fish"):
                if any(target_fish in f or f in target_fish for f in rec["fish"]):
                    score += 5
            elif target_fish and not rec.get("fish"):
                # 第二部分条目无鱼种, 不扣分但也不加分
                pass

            # 2. 季节命中 (+3)
            if season_norm and rec.get("season") == season_norm:
                score += 3

            # 3. 气温区间命中 (+3 完全包含 / +1 接近)
            if t_water is not None and rec.get("temp_min") is not None and rec.get("temp_max") is not None:
                t_min, t_max = rec["temp_min"], rec["temp_max"]
                if t_min - 1 <= t_water <= t_max + 1:
                    score += 3
                elif abs((t_min + t_max) / 2 - t_water) <= 5:
                    score += 1

            # 4. 气压状态命中 (+2)
            if pressure_norm and rec.get("pressure_state") == pressure_norm:
                score += 2
            elif pressure_norm == "稳定" and rec.get("pressure_state") in {"高压稳定", "低压稳定"}:
                score += 1

            # 5. 数据完整度 (+0~+1, 用于平局打破)
            score += min(rec.get("quality", 0), 6) * 0.1

            if score > 0:
                scored.append((score, rec))

        # 按分数降序, 取 Top-K
        scored.sort(key=lambda x: x[0], reverse=True)
        # 至少要求 score >= 3 才认为可用 (避免只命中"数据完整度"的弱推荐)
        result = [rec for sc, rec in scored if sc >= 3][:top_k]
        return result


def format_references_for_prompt(records: List[dict]) -> str:
    """把检索到的秘籍格式化为 LLM prompt 友好的纯文本块。"""
    if not records:
        return ""
    lines = []
    for i, r in enumerate(records, 1):
        head = f"[{i}] 大师 {r.get('master', '?')} · 《{r.get('title', '?')}》"
        env = f"   环境: {r.get('season', '?')} {r.get('temp_min')}~{r.get('temp_max')}℃ / 气压{r.get('pressure_state', '?')}"
        line = f"   线组: {r.get('line') or '-'}"
        floatx = f"   调漂: {r.get('float_setup') or '-'}"
        rhythm = f"   节奏: {r.get('rhythm') or '-'}"
        flavor = f"   味型: {r.get('flavor') or '-'}"
        recipe = f"   配方: {r.get('recipe') or '-'}"
        url = f"   视频: {r.get('video_url') or '-'}"
        lines.append("\n".join([head, env, line, floatx, rhythm, flavor, recipe, url]))
    return "\n\n".join(lines)
