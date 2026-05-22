"""
大师战术知识库检索器测试
========================
验证:
- 知识库正常加载
- 多维度检索按命中分排序
- 缺省维度不污染结果
- prompt 格式化输出正确
"""
import pytest
from domain.master_kb import (
    MasterKBRetriever,
    format_references_for_prompt,
    _normalize_season,
    _normalize_pressure,
    _season_from_temp,
)


class TestRetrieverLoading:
    def test_singleton_load(self):
        kb1 = MasterKBRetriever.get()
        kb2 = MasterKBRetriever.get()
        assert kb1 is kb2

    def test_kb_has_records(self):
        kb = MasterKBRetriever.get()
        assert kb.size > 100, f"知识库条目过少: {kb.size}"

    def test_kb_record_schema(self):
        kb = MasterKBRetriever.get()
        if kb.size == 0:
            pytest.skip("知识库为空（数据文件未生成）")
        rec = kb._records[0]
        for field in ("id", "master", "season", "temp_min", "temp_max", "pressure_state"):
            assert field in rec, f"缺字段: {field}"


class TestNormalize:
    def test_season_normalize(self):
        assert _normalize_season("初春") == "初春"
        assert _normalize_season("spring") == "初春"
        assert _normalize_season("winter") == "隆冬"
        assert _normalize_season(None) is None
        assert _normalize_season("乱码") is None

    def test_pressure_normalize(self):
        assert _normalize_pressure("STATUS_PRESSURE_RISING") == "上升"
        assert _normalize_pressure("STATUS_PRESSURE_CRASH") == "骤降"
        assert _normalize_pressure("稳定") == "稳定"
        assert _normalize_pressure(None) is None

    def test_season_from_temp(self):
        assert _season_from_temp(2) == "隆冬"
        assert _season_from_temp(8) == "初冬"
        assert _season_from_temp(15) == "初春"
        assert _season_from_temp(20) == "暮春"
        assert _season_from_temp(26) == "初夏"
        assert _season_from_temp(32) == "盛夏"
        assert _season_from_temp(None) is None


class TestSearch:
    @pytest.fixture(scope="class")
    def kb(self):
        return MasterKBRetriever.get()

    def test_no_dimension_returns_empty(self, kb):
        """全部维度为空不应该乱推荐。"""
        if kb.size == 0:
            pytest.skip("知识库为空")
        assert kb.search() == []

    def test_search_by_fish(self, kb):
        if kb.size == 0:
            pytest.skip("知识库为空")
        recs = kb.search(target_fish="鲫鱼", top_k=3)
        # 应该至少能找到几条 (鲫鱼专区有 42 条)
        assert len(recs) > 0
        # 命中条目的 fish 列表里应该包含鲫鱼
        # (注意第二部分 fish 为空, 所以验证: 有鱼种字段时应包含鲫鱼)
        for r in recs:
            if r.get("fish"):
                assert any("鲫" in f for f in r["fish"])

    def test_search_winter_low_temp(self, kb):
        """隆冬低温场景: 应该召回到隆冬条目。"""
        if kb.size == 0:
            pytest.skip("知识库为空")
        recs = kb.search(target_fish="鲫鱼", t_water=3, pressure_state="稳定", top_k=3)
        assert len(recs) > 0
        # Top-1 至少有一项符合: 隆冬 OR 鲫鱼
        top1 = recs[0]
        ok = (top1.get("season") in {"隆冬", "初冬"}) or any("鲫" in f for f in top1.get("fish", []))
        assert ok, f"Top-1 不符合预期: {top1}"

    def test_search_summer_lianyu(self, kb):
        """盛夏鲢鳙场景。"""
        if kb.size == 0:
            pytest.skip("知识库为空")
        recs = kb.search(target_fish="鲢鱼", t_water=29, pressure_state="稳定", top_k=3)
        assert len(recs) > 0

    def test_top_k_limit(self, kb):
        if kb.size == 0:
            pytest.skip("知识库为空")
        recs = kb.search(target_fish="鲫鱼", t_water=18, top_k=2)
        assert len(recs) <= 2


class TestPromptFormat:
    def test_empty_records(self):
        assert format_references_for_prompt([]) == ""

    def test_single_record(self):
        rec = {
            "master": "刘志强",
            "title": "春钓小鲫鱼",
            "season": "初春",
            "temp_min": 8,
            "temp_max": 18,
            "pressure_state": "稳定",
            "line": "主线0.8号+子线0.4号+袖钩6号",
            "float_setup": "调7目钓2目",
            "rhythm": "每分钟1竿",
            "flavor": "腥香微甜",
            "recipe": "野战蓝鲫50%+九一八30%+酒米20%",
            "video_url": "https://www.bilibili.com/video/BV1v44y1N7QS/",
        }
        text = format_references_for_prompt([rec])
        assert "刘志强" in text
        assert "春钓小鲫鱼" in text
        assert "野战蓝鲫" in text
        assert "https://www.bilibili.com" in text
