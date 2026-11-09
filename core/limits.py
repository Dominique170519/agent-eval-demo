"""实时模型调用的限额：全站每日上限 + 单个访客会话上限。

全站计数保存在进程内存里，应用重启（休眠后唤醒、重新部署）会重置，所以它是"尽力而为"的成本保护，不是严格的计费上限。
真正的兜底是 API Key 自身的额度。日期按北京时间划分。
"""
import datetime
import threading

_lock = threading.Lock()
_state = {"date": None, "count": 0}
_TZ = datetime.timezone(datetime.timedelta(hours=8))


def _today():
    return datetime.datetime.now(_TZ).strftime("%Y-%m-%d")


def _roll():
    d = _today()
    if _state["date"] != d:
        _state["date"], _state["count"] = d, 0


def remaining(cap):
    with _lock:
        _roll()
        return max(cap - _state["count"], 0)


def try_consume(cap):
    """还有额度就占用一次并返回 True；否则返回 False。"""
    with _lock:
        _roll()
        if _state["count"] >= cap:
            return False
        _state["count"] += 1
        return True


def refund():
    """调用失败（没有真正消耗模型额度）时归还一次。"""
    with _lock:
        _roll()
        _state["count"] = max(_state["count"] - 1, 0)
