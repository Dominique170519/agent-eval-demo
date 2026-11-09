"""用冻结的 Reviewer 为 6 个虚构用户预先生成示例输出（examples.json），供额度用完时降级展示。
用法：DASHSCOPE_API_KEY=... python tools/make_examples.py（或从研究项目的 .env 读取）
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import features as F, reviewer as R, scoring as S  # noqa: E402
from core.personas import PERSONAS  # noqa: E402

key = os.environ.get("DASHSCOPE_API_KEY")
if not key:
    env = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "agent-eval", ".env")
    for line in open(env, encoding="utf-8").read().splitlines():
        if line.startswith("DASHSCOPE_API_KEY="):
            key = line.split("=", 1)[1].strip()
out = {}
for name, inp in PERSONAS.items():
    feats = F.compute_features(inp)
    scored = S.score_user(feats)
    res = R.call_review(R.build_user_message(feats, scored), key)
    if res["error"]:
        sys.exit(f"{name} 生成失败: {res['error']}")
    rv = res["review"]
    out[name] = {"scored": scored, "review": rv.model_dump(), "missing": R.number_check(rv.explanation + " " + rv.script, feats, scored),
                 "flags": R.script_screen(rv.script)}
    print(name, "|", scored["risk_score"], f"T{scored['T']}", "|", rv.verdict, "|", "数字检查", "通过" if not out[name]["missing"] else out[name]["missing"],
          "| 话术筛查", "通过" if not out[name]["flags"] else out[name]["flags"])
json.dump(out, open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("已写入 examples.json")
