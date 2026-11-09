"""真实模型的小样本回归（每周一次，也可手动触发）。指标低于阈值则退出码为 1，工作流随之失败。

固定 8 个虚构的高风险名单用户，调用冻结的 Reviewer，检查：
- 解析成功率 ≥ 87.5%（8 个里最多允许 1 个失败）
- 说明和话术里的数字全部出自输入或历史统计（对不上的数字 = 0）
- 话术筛查无违规
- 逾期用户不被下调（dev / test 上被下调的都是未逾期或极个别用户，逾期且活跃的用户应当 keep）
- 单次耗时 P95 ≤ 60 秒
结果写入 regression_report.json。用法：DASHSCOPE_API_KEY=... python tests/llm_regression.py
"""
import json
import os
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from core import features as F, reviewer as R, scoring as S  # noqa: E402
from core.personas import PERSONAS  # noqa: E402


def make_inputs():
    base = [PERSONAS["逾期但依然活跃"], PERSONAS["逾期且活跃递减"], PERSONAS["逾期且几乎不用"]]
    extra = [
        {"overdue": 1, "active_days": [7, 7, 7, 7], "play_minutes": [400, 410, 420, 400], "full_rate_pct": [50, 50, 50, 50], "unique_songs": [50, 50, 50, 50], "annual_amount": 2190.0},
        {"overdue": 1, "active_days": [4, 4, 3, 3], "play_minutes": [200, 190, 150, 140], "full_rate_pct": [40, 38, 36, 35], "unique_songs": [25, 24, 20, 19], "annual_amount": 1812.8},
        {"overdue": 1, "active_days": [3, 2, 1, 0], "play_minutes": [150, 80, 30, 0], "full_rate_pct": [35, 30, 20, 0], "unique_songs": [18, 10, 4, 0], "annual_amount": 1812.8},
        {"overdue": 1, "active_days": [2, 2, 2, 1], "play_minutes": [80, 70, 70, 40], "full_rate_pct": [30, 30, 28, 20], "unique_songs": [10, 9, 9, 5], "annual_amount": 2190.0},
        {"overdue": 1, "active_days": [0, 0, 0, 0], "play_minutes": [0, 0, 0, 0], "full_rate_pct": [0, 0, 0, 0], "unique_songs": [0, 0, 0, 0], "annual_amount": 1812.8},
    ]
    out = []
    for inp in base + extra:
        f = F.compute_features(inp)
        s = S.score_user(f)
        if s["focus_high"]:
            out.append((inp, f, s))
    return out


def main():
    key = os.environ.get("DASHSCOPE_API_KEY")
    if not key:
        sys.exit("缺少 DASHSCOPE_API_KEY")
    cases = make_inputs()
    rows = []
    for inp, f, s in cases:
        res = R.call_review(R.build_user_message(f, s), key)
        rv = res["review"]
        row = {"overdue": f["overdue"], "error": res["error"], "latency_s": res["latency_s"], "tokens": res["prompt_tokens"] + res["completion_tokens"]}
        if rv:
            row.update(verdict=rv.verdict, missing_numbers=R.number_check(rv.explanation + " " + rv.script, f, s), script_flags=R.script_screen(rv.script))
        rows.append(row)
    ok = [r for r in rows if not r["error"]]
    lat = sorted(r["latency_s"] for r in ok) or [0]
    p95 = lat[min(len(lat) - 1, int(0.95 * len(lat)))]
    checks = {
        "解析成功率": (len(ok) / len(rows), len(ok) / len(rows) >= 0.875),
        "数字对不上的条数": (sum(1 for r in ok if r["missing_numbers"]), all(not r["missing_numbers"] for r in ok)),
        "话术违规条数": (sum(1 for r in ok if r["script_flags"]), all(not r["script_flags"] for r in ok)),
        "逾期用户被下调的人数": (sum(1 for r in ok if r["overdue"] and r["verdict"] == "downgrade"), all(not (r["overdue"] and r["verdict"] == "downgrade") for r in ok)),
        "耗时 P95（秒）": (p95, p95 <= 60),
    }
    report = {"时间": time.strftime("%Y-%m-%d %H:%M:%S"), "用例数": len(rows), "指标": {k: {"值": v[0], "通过": v[1]} for k, v in checks.items()},
              "平均 token": statistics.mean(r["tokens"] for r in ok) if ok else 0, "明细": rows}
    json.dump(report, open(os.path.join(ROOT, "regression_report.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for k, (v, passed) in checks.items():
        print(("通过" if passed else "失败"), k, v)
    sys.exit(0 if all(p for _, p in checks.values()) else 1)


if __name__ == "__main__":
    main()
