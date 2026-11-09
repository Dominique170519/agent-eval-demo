"""演示用的虚构用户。全部是手写的虚构人物，与任何真实用户无关（竞赛数据条款不允许再分发数据）。"""

PERSONAS = {
    "逾期但依然活跃": {"overdue": 1, "active_days": [6, 7, 7, 7], "play_minutes": [320, 350, 380, 360], "full_rate_pct": [45, 47, 46, 48],
                  "unique_songs": [40, 42, 45, 41], "annual_amount": 1812.8},
    "逾期且活跃递减": {"overdue": 1, "active_days": [6, 4, 2, 1], "play_minutes": [300, 190, 90, 30], "full_rate_pct": [44, 38, 30, 22],
                  "unique_songs": [38, 25, 12, 5], "annual_amount": 1812.8},
    "逾期且几乎不用": {"overdue": 1, "active_days": [1, 0, 0, 0], "play_minutes": [20, 0, 0, 0], "full_rate_pct": [30, 0, 0, 0],
                  "unique_songs": [6, 0, 0, 0], "annual_amount": 1204.5},
    "未逾期但活跃下降": {"overdue": 0, "active_days": [7, 5, 3, 2], "play_minutes": [420, 300, 160, 90], "full_rate_pct": [50, 44, 36, 30],
                   "unique_songs": [50, 36, 20, 12], "annual_amount": 1812.8},
    "未逾期且稳定活跃": {"overdue": 0, "active_days": [6, 6, 7, 6], "play_minutes": [310, 330, 350, 320], "full_rate_pct": [46, 47, 45, 46],
                   "unique_songs": [35, 37, 36, 34], "annual_amount": 2190.0},
    "未逾期、低频但稳定": {"overdue": 0, "active_days": [2, 2, 1, 2], "play_minutes": [60, 55, 30, 58], "full_rate_pct": [35, 36, 30, 34],
                    "unique_songs": [10, 9, 5, 9], "annual_amount": 1204.5},
}

PLANS = {"月费 99 元档（年化约 1,204.5）": 1204.5, "月费 149 元档（年化约 1,812.8）": 1812.8, "月费 180 元档（年化约 2,190）": 2190.0}


def same_input(a, b):
    """判断两份输入是否完全一致（用于判断是否可以直接展示预先生成的示例）。"""
    keys = ["overdue", "active_days", "play_minutes", "full_rate_pct", "unique_songs", "annual_amount"]
    norm = lambda d: {k: ([float(x) for x in d[k]] if isinstance(d[k], (list, tuple)) else float(d[k])) for k in keys}  # noqa: E731
    return norm(a) == norm(b)
