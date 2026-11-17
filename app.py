"""客户续约风险研判 Demo：规则 v1 打分 + Reviewer 生成说明与话术。
教学演示，数据为虚构，输出不构成任何业务建议。"""
import json
import os

import streamlit as st

from core import features as F
from core import limits, obs as O, reviewer as R, scoring as S
from core.personas import PERSONAS, PLANS, same_input

st.set_page_config(page_title="续约风险研判 Demo", page_icon="📊", layout="wide")


def secret(name, default=None):
    try:
        if name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass
    return os.environ.get(name, default)


DAILY_CAP, SESSION_CAP = int(secret("DAILY_CAP", 10)), 3
API_KEY = secret("DASHSCOPE_API_KEY")
EXAMPLES = json.load(open(os.path.join(os.path.dirname(__file__), "examples.json"), encoding="utf-8"))


@st.cache_resource
def get_obs():
    return O.Obs(secret("LANGFUSE_PUBLIC_KEY"), secret("LANGFUSE_SECRET_KEY"), secret("LANGFUSE_HOST"))


obs = get_obs()
st.session_state.setdefault("live_used", 0)

st.title("📊 客户续约风险研判 Demo")
st.caption("复刻“指标加权 → 风险分桶 × 金额分桶 → 优先级分层”链路，并用大模型生成给销售的风险说明。"
           "**教学演示：所有用户均为虚构，输出由大模型生成，不构成业务建议。**")

with st.sidebar:
    quota_slot = st.empty()  # 先占位，等本次请求处理完再显示最新剩余次数
    st.caption(f"每位访客最多 {SESSION_CAP} 次；额度用完后自动降级为规则结果和预先生成的示例。")
    st.caption({"connected": "监控：Langfuse 已连接并通过认证",
                "auth_failed": "监控：Langfuse 认证失败，目前仅记录本地日志",
                "local": "监控：仅本地日志（未配置 Langfuse）"}[obs.status])
    if obs.status == "auth_failed" and obs.error:
        st.caption(f"原因：{obs.error}")

tab1, tab2 = st.tabs(["体验", "评测结果与监控"])

with tab1:
    pname = st.selectbox("选择一个虚构用户（可在下面修改数值）", list(PERSONAS))
    p = PERSONAS[pname]
    c0, c1 = st.columns(2)
    overdue = c0.checkbox("快照日前最后一笔交易已关闭自动续费或为取消（逾期）", value=bool(p["overdue"]), key=f"{pname}_od")
    plan_labels = list(PLANS)
    idx = [v for v in PLANS.values()].index(p["annual_amount"]) if p["annual_amount"] in PLANS.values() else 1
    plan = c1.selectbox("套餐", plan_labels, index=idx, key=f"{pname}_plan")
    st.markdown("**最近 4 周的行为**")
    ad, pm, fr, us = [], [], [], []
    for i, col in enumerate(st.columns(4)):
        with col:
            st.markdown(f"第 {i + 1} 周" + ("（最近一周）" if i == 3 else ""))
            ad.append(st.number_input("活跃天数", 0, 7, int(p["active_days"][i]), key=f"{pname}_ad{i}"))
            pm.append(st.number_input("播放分钟", 0.0, 3000.0, float(p["play_minutes"][i]), step=10.0, key=f"{pname}_pm{i}"))
            fr.append(st.number_input("完整播放占比 %", 0.0, 100.0, float(p["full_rate_pct"][i]), step=1.0, key=f"{pname}_fr{i}"))
            us.append(st.number_input("不同歌曲数", 0, 500, int(p["unique_songs"][i]), key=f"{pname}_us{i}"))
    inp = {"overdue": int(overdue), "active_days": ad, "play_minutes": pm, "full_rate_pct": fr, "unique_songs": us, "annual_amount": PLANS[plan]}

    if st.button("生成研判", type="primary"):
        feats = F.compute_features(inp)
        scored = S.score_user(feats)
        preset = same_input(inp, p)
        res = {"features": feats, "scored": scored, "mode": "rules_only", "review": None, "trace_id": None, "note": "", "feedback": False}
        msg = R.build_user_message(feats, scored)
        if not scored["focus_high"]:
            # Reviewer 只在 T1/T2 名单上评测过，名单外的用户不调用模型
            res["mode"], res["note"] = "not_in_list", "该用户不在高风险名单（T3/T4），Reviewer 只复核 T1/T2 的用户，所以不生成说明。可以换一个逾期用户试试。"
            res["trace_id"] = obs.degraded_event("not_in_list", feats, scored)
            obs.local_log({"event": "request", "mode": "not_in_list", "features": feats, "scored": scored})
            st.session_state["result"] = res
            st.rerun()
        can_live = bool(API_KEY) and st.session_state["live_used"] < SESSION_CAP
        reason = "" if can_live else ("未配置 API Key" if not API_KEY else "你的会话次数已达上限")
        if can_live and not limits.try_consume(DAILY_CAP):
            can_live, reason = False, "今日实时调用额度已用完"
        if can_live:
            with st.spinner("大模型正在生成说明……"):
                call, trace_id = obs.observed_call(lambda: R.call_review(msg, API_KEY), msg, feats, scored, R.MODEL)
            if call["error"]:
                limits.refund()
                can_live, reason = False, f"实时调用失败（{call['error']}）"
            else:
                st.session_state["live_used"] += 1
                rv = call["review"]
                text = rv.explanation + " " + rv.script
                miss, flags = R.number_check(text, feats, scored), R.script_screen(rv.script)
                res.update(mode="live", review=rv.model_dump(), trace_id=trace_id, missing=miss, flags=flags,
                           latency=call["latency_s"], tokens=call["prompt_tokens"] + call["completion_tokens"])
                obs.score(trace_id, "number_check_ok", not miss)
                obs.score(trace_id, "script_screen_ok", not flags)
                obs.score(trace_id, "format_ok", 1)
        if res["mode"] != "live":
            ex = EXAMPLES.get(pname) if preset else None
            if ex:
                res.update(mode="precomputed", review=ex["review"], missing=ex["missing"], flags=ex["flags"],
                           note=f"{reason}，以下是预先生成的示例输出。")
            else:
                res["note"] = f"{reason}，且你修改了数值，这里只显示规则结果。可以选择未修改的虚构用户查看示例说明。"
            res["trace_id"] = obs.degraded_event(reason, feats, scored)
        obs.local_log({"event": "request", "mode": res["mode"], "reason": reason, "features": feats, "scored": scored,
                       "verdict": (res["review"] or {}).get("verdict"), "latency_s": res.get("latency"), "tokens": res.get("tokens"),
                       "number_check_ok": not res.get("missing") if res["review"] else None, "script_screen_ok": not res.get("flags") if res["review"] else None})
        st.session_state["result"] = res

    res = st.session_state.get("result")
    if res:
        sc = res["scored"]
        st.divider()
        m = st.columns(5)
        m[0].metric("规则风险分（v1）", sc["risk_score"])
        m[1].metric("风险桶 R", sc["R"])
        m[2].metric("金额桶 A", sc["A"])
        m[3].metric("优先级 T", sc["T"])
        m[4].metric("高风险名单", "是（T1/T2）" if sc["focus_high"] else "否")
        if res["note"]:
            st.info(res["note"])
        rv = res["review"]
        if rv:
            st.subheader("Reviewer 的说明" + ("（实时生成）" if res["mode"] == "live" else "（预先生成的示例）"))
            st.write(f"**结论**：{'维持高风险' if rv['verdict'] == 'keep' else '建议下调'}　**置信度**：{rv['confidence']}")
            st.write(f"**风险说明**：{rv['explanation']}")
            st.write(f"**沟通建议**：{rv['script']}")
            with st.expander("引用的证据"):
                st.table([{"字段": e["feature"], "取值": e["value"]} for e in rv["evidence"]])
            ok1, ok2 = not res["missing"], not res["flags"]
            st.caption(("✅ 数字检查通过：说明里的小数和百分比都出自输入或历史统计" if ok1 else f"⚠️ 数字检查发现无法对上的数字：{res['missing']}") + "　|　"
                       + ("✅ 话术筛查通过" if ok2 else f"⚠️ 话术筛查：{'、'.join(res['flags'])}"))
            if res["mode"] == "live":
                st.caption(f"耗时 {res['latency']} 秒，约 {res['tokens']} token")
            if not res["feedback"]:
                b = st.columns([1, 1, 6])
                for col, label, val in [(b[0], "👍 有用", 1), (b[1], "👎 没用", 0)]:
                    if col.button(label, key=f"fb{val}"):
                        obs.score(res["trace_id"], "user_feedback", val)
                        obs.local_log({"event": "feedback", "value": val, "mode": res["mode"]})
                        res["feedback"] = True
                        st.rerun()
            else:
                st.success("感谢反馈！")

with tab2:
    st.markdown(open(os.path.join(os.path.dirname(__file__), "RESULTS.md"), encoding="utf-8").read())

quota_slot.metric("今日剩余实时调用", f"{limits.remaining(DAILY_CAP)} / {DAILY_CAP}")
