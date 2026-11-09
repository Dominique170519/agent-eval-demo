"""规则 v1 的单用户打分：风险分 → R 桶 → A 桶 → T 层级。

权重与切点在研究项目里由 train 集校准得到，导出为 core/assets/v1_config.json（只含汇总参数，不含任何用户数据）。
"""
import json
import math
import os

_CFG = json.load(open(os.path.join(os.path.dirname(__file__), "assets", "v1_config.json"), encoding="utf-8"))


def risk_score(f):
    w = _CFG["weights_v1"]
    drop_share, drop_full = _CFG["drop_share"], _CFG["drop_full"]
    unq_frac = drop_share * min(f["unq_avg_drop"] / drop_full, 1.0) + (1 - drop_share) * (f["unq_consec"] / 3)
    score = w["adoption"] * (1 - f["adoption_rate"]) + w["unq"] * unq_frac + w["overdue"] * f["overdue"]
    return round(score, 2)


def r_bucket(score):
    r = 6
    for i in range(len(_CFG["r_cutoffs"]) - 1, -1, -1):
        if score >= _CFG["r_cutoffs"][i]:
            r = i + 1
    return r


def a_bucket(amount):
    a = len(_CFG["a_edges"]) + 1
    for i in range(len(_CFG["a_edges"]) - 1, -1, -1):
        if amount >= _CFG["a_edges"][i]:
            a = i + 1
    return a


def score_user(f):
    s = risk_score(f)
    r, a = r_bucket(s), a_bucket(f["annual_amount"])
    t = min(4, math.ceil((r + a) / 2))
    return {"risk_score": s, "R": r, "A": a, "T": t, "focus_high": t <= 2}
