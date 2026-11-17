"""可观测性：Langfuse 追踪（可选）+ 本地 JSONL 日志（始终写入）。

每次请求记录：输入特征（不含任何用户标识）、规则打分、模型输出、token、耗时、报错、检查结果、是否降级。
Langfuse 不可用或未配置时，应用照常运行，只写本地日志。
"""
import json
import os
import threading
import time

LOG_PATH = os.environ.get("DEMO_LOG_PATH", os.path.join("logs", "requests.jsonl"))
_lock = threading.Lock()


class Obs:
    def __init__(self, public_key=None, secret_key=None, host=None):
        self.lf = None
        self.status = "local"  # local：未配置；connected：已通过认证；auth_failed：密钥或区域不对
        if public_key and secret_key:
            try:
                from langfuse import Langfuse

                lf = Langfuse(public_key=public_key, secret_key=secret_key, host=host or "https://cloud.langfuse.com", timeout=10)
                try:
                    ok = bool(lf.auth_check())
                except Exception:
                    ok = False
                if ok:
                    self.lf, self.status = lf, "connected"
                else:
                    self.status = "auth_failed"
            except Exception:
                self.status = "auth_failed"

    @property
    def enabled(self):
        return self.lf is not None

    def local_log(self, rec):
        rec = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), **rec}
        try:
            os.makedirs(os.path.dirname(LOG_PATH) or ".", exist_ok=True)
            with _lock, open(LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def observed_call(self, fn, user_message, features, scored, model, prompt_version="v2"):
        """执行 fn()（模型调用），并在 Langfuse 里记录为一次 generation。返回 (结果, trace_id)。"""
        res, trace_id = None, None
        if self.lf:
            try:
                with self.lf.start_as_current_observation(name="risk_reviewer", as_type="generation", model=model, input=user_message,
                                                          metadata={"prompt_version": prompt_version}) as gen:
                    res = fn()
                    out = res["review"].model_dump() if res["review"] else {"error": res["error"]}
                    gen.update(output=out, usage_details={"input": res["prompt_tokens"], "output": res["completion_tokens"]},
                               level="ERROR" if res["error"] else "DEFAULT", status_message=res["error"])
                    self.lf.update_current_trace(name="demo_request", tags=["demo", "live"], input={"features": features, "scored": scored}, output=out)
                    trace_id = self.lf.get_current_trace_id()
                self.lf.flush()
            except Exception:
                pass
        if res is None:
            res = fn()
        return res, trace_id

    def degraded_event(self, reason, features, scored):
        """记录一次被降级（未调用模型）的请求。"""
        trace_id = None
        if self.lf:
            try:
                with self.lf.start_as_current_observation(name="degraded_request", as_type="span", input={"features": features, "scored": scored},
                                                          metadata={"reason": reason}):
                    self.lf.update_current_trace(name="demo_request", tags=["demo", "degraded"])
                    trace_id = self.lf.get_current_trace_id()
                self.lf.flush()
            except Exception:
                pass
        return trace_id

    def score(self, trace_id, name, value, comment=None):
        if self.lf and trace_id:
            try:
                self.lf.create_score(trace_id=trace_id, name=name, value=float(value), data_type="NUMERIC", comment=comment)
                self.lf.flush()
            except Exception:
                pass
