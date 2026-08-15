"""trace_signature 单测 — 验证按 (tab, keyword, rule, category) 元组分组。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "impl"))

from taobao_guanghe._link_ops import trace_signature


def test_same_trace_same_signature():
    t1 = {"tab": "preferred", "keyword": "小米17", "rule": "主推品", "category": "全部"}
    t2 = {"tab": "preferred", "keyword": "小米17", "rule": "主推品", "category": "全部"}
    assert trace_signature(t1) == trace_signature(t2)


def test_different_keyword_different_signature():
    t1 = {"tab": "preferred", "keyword": "小米17", "rule": "", "category": ""}
    t2 = {"tab": "preferred", "keyword": "手机壳", "rule": "", "category": ""}
    assert trace_signature(t1) != trace_signature(t2)


def test_missing_fields_default_to_empty_string():
    t = {"tab": "shop"}
    assert trace_signature(t) == ("shop", "", "", "")


def test_empty_trace():
    assert trace_signature({}) == ("", "", "", "")


def test_grouping_use_case():
    """模拟 spec 6.3 的场景:A、B 同轨迹,C 不同。"""
    items = [
        {"id": "123", "trace": {"tab": "preferred", "keyword": "小米17", "rule": "主推品", "category": "全部"}},
        {"id": "124", "trace": {"tab": "preferred", "keyword": "小米17", "rule": "主推品", "category": "全部"}},
        {"id": "125", "trace": {"tab": "preferred", "keyword": "手机壳", "rule": "", "category": ""}},
    ]
    groups = {}
    for it in items:
        sig = trace_signature(it["trace"])
        groups.setdefault(sig, []).append(it["id"])
    assert len(groups) == 2
    assert groups[trace_signature(items[0]["trace"])] == ["123", "124"]
    assert groups[trace_signature(items[2]["trace"])] == ["125"]
