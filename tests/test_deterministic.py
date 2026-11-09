"""确定性检查（不调用大模型，不花额度）：每次提交都会运行。
用法：python tests/test_deterministic.py   （也兼容 pytest）
"""
import hashlib
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from core import features as F, limits, reviewer as R, scoring as S  # noqa: E402

FROZEN_FINGERPRINT = "87077f73c06ca131"  # 研究项目冻结配置里记录的提示词指纹（reports/frozen_reviewer_config.json）


def test_prompt_fingerprint():
    cfg = json.load(open(os.path.join(ROOT, "core", "assets", "v1_config.json"), encoding="utf-8"))
    fp = hashlib.sha256(R.SYSTEM_PROMPT.encode()).hexdigest()[:16]
    assert fp == FROZEN_FINGERPRINT == cfg["prompt_fingerprint"], f"提示词与冻结版本不一致: {fp}"


def test_scoring_parity_with_research_pipeline():
    cases = json.load(open(os.path.join(ROOT, "tests", "fixtures", "parity.json"), encoding="utf-8"))
    for i, c in enumerate(cases):
        f = F.compute_features(c["input"])
        s = S.score_user(f)
        e = c["expected"]
        for k in ["adoption_rate", "dau_avg_drop", "secs_avg_drop", "full_rate_avg_drop", "unq_avg_drop"]:
            assert math.isclose(f[k], e[k], abs_tol=1e-4), f"用例 {i} 特征 {k}: {f[k]} != {e[k]}"
        assert math.isclose(s["risk_score"], e["risk_score"], abs_tol=0.011), f"用例 {i} 风险分: {s['risk_score']} != {e['risk_score']}"
        assert (s["R"], s["A"], s["T"], s["focus_high"]) == (e["R"], e["A"], e["T"], e["focus_high"]), f"用例 {i} 分桶不一致"


def test_features_edge_cases():
    f = F.compute_features({"overdue": 0, "active_days": [0, 0, 0, 0], "play_minutes": [0, 0, 0, 0], "full_rate_pct": [0, 0, 0, 0],
                            "unique_songs": [0, 0, 0, 0], "annual_amount": 0})
    assert f["adoption_rate"] == 0 and f["dau_avg_drop"] == 0 and f["dau_consec"] == 0
    g = F.compute_features({"overdue": 1, "active_days": [7, 5, 3, 1], "play_minutes": [1, 1, 1, 1], "full_rate_pct": [1, 1, 1, 1],
                            "unique_songs": [1, 1, 1, 1], "annual_amount": 1812.8})
    assert g["dau_consec"] == 3 and g["dau_avg_drop"] > 0.3


def test_review_parsing_accepts_numeric_evidence():
    ok = R.Review.model_validate({"verdict": "keep", "confidence": "high", "evidence": [{"feature": "overdue", "value": 1}],
                                  "explanation": "x", "script": "y"})
    assert ok.evidence[0].value == "1"
    try:
        R.Review.model_validate({"verdict": "maybe", "confidence": "high", "evidence": [], "explanation": "x", "script": "y"})
    except Exception:
        return
    raise AssertionError("非法的 verdict 应当被拒绝")


def test_number_check():
    f = F.compute_features({"overdue": 1, "active_days": [6, 4, 2, 1], "play_minutes": [300, 190, 90, 30], "full_rate_pct": [44, 38, 30, 22],
                            "unique_songs": [38, 25, 12, 5], "annual_amount": 1812.8})
    s = S.score_user(f)
    assert R.number_check(f"adoption_rate 为 {f['adoption_rate']}，逾期用户流失率 44%", f, s) == []
    assert R.number_check("周平均跌幅为 0.9876", f, s) == ["0.9876"]


def test_script_screen():
    assert R.script_screen("沟通中不承诺折扣或额外权益") == []
    assert R.script_screen("本月续费可享 8 折优惠，并赠送一个月会员") == ["疑似承诺折扣或赠品"]
    assert R.script_screen("系统已把您评为 T2 高风险客户") == ["提及内部评分或分桶"]
    assert R.script_screen("我们知道您肯定会取消订阅") == ["暗示用户一定会流失"]
    assert R.script_screen("想了解一下您最近的使用体验有没有遇到困难") == []


def test_daily_cap():
    limits._state.update({"date": None, "count": 0})
    assert [limits.try_consume(3) for _ in range(5)] == [True, True, True, False, False]
    limits.refund()
    assert limits.remaining(3) == 1


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print("通过", name)
        except Exception as e:  # noqa: BLE001
            failed += 1
            print("失败", name, "|", repr(e)[:200])
    print(f"\n共 {len(tests)} 项，失败 {failed} 项")
    sys.exit(1 if failed else 0)
