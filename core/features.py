"""把访问者输入的 4 周行为数据转换成与研究项目一致的特征（纯 Python，无依赖）。

口径与研究项目 features/build_features.py 的 decline_features 一致：
- 周平均跌幅：相邻两周的跌幅取平均，上升记为 0，上一周为 0 时记为 0
- 连续下降周数：从最后一周往前数，连续低于上一周的次数（0-3）
"""

N_WEEKS = 4
WINDOW_DAYS = 28


def decline(values):
    """返回 (周平均跌幅, 连续下降周数)。"""
    drops = []
    for prev, cur in zip(values[:-1], values[1:]):
        drops.append(min(max((prev - cur) / prev, 0.0), 1.0) if prev > 0 else 0.0)
    streak = 0
    for prev, cur in zip(reversed(values[:-1]), reversed(values[1:])):
        if cur < prev:
            streak += 1
        else:
            break
    return round(sum(drops) / len(drops), 4), streak


def compute_features(inp):
    """inp：overdue(0/1)，active_days / play_minutes / full_rate_pct / unique_songs（各 4 个数，按周从早到晚），annual_amount。"""
    ad = [int(x) for x in inp["active_days"]]
    secs = [float(x) for x in inp["play_minutes"]]
    full = [float(x) / 100.0 for x in inp["full_rate_pct"]]
    unq = [float(x) for x in inp["unique_songs"]]
    for name, seq in [("active_days", ad), ("play_minutes", secs), ("full_rate_pct", full), ("unique_songs", unq)]:
        if len(seq) != N_WEEKS:
            raise ValueError(f"{name} 需要 {N_WEEKS} 个数")
    f = {"overdue": int(inp["overdue"]), "annual_amount": round(float(inp["annual_amount"]), 1)}
    f["adoption_rate"] = round(min(1.0, sum(ad) / WINDOW_DAYS), 4)
    for i, v in enumerate(ad, 1):
        f[f"active_days_w{i}"] = v
    f["dau_avg_drop"], f["dau_consec"] = decline(ad)
    f["secs_avg_drop"], f["secs_consec"] = decline(secs)
    f["full_rate_avg_drop"], f["full_rate_consec"] = decline(full)
    f["unq_avg_drop"], f["unq_consec"] = decline(unq)
    return f
