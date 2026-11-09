"""Reviewer（冻结配置：kimi-k3 + 提示词 v2）：生成风险说明与沟通建议，并做规则检查。

提示词文本、字段说明、历史统计都由研究项目导出（core/assets/），保证与评测时完全一致，指纹见 tests。
"""
import json
import os
import re
import time
from typing import List, Literal

from openai import APIStatusError, OpenAI
from pydantic import BaseModel, ValidationError, field_validator

ASSETS = os.path.join(os.path.dirname(__file__), "assets")
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
MODEL = "kimi-k3"

SYSTEM_PROMPT = open(os.path.join(ASSETS, "prompt_v2.txt"), encoding="utf-8").read()
STATS_TEXT = open(os.path.join(ASSETS, "stats.txt"), encoding="utf-8").read()
FIELDS = json.load(open(os.path.join(ASSETS, "fields.json"), encoding="utf-8"))


class Evidence(BaseModel):
    feature: str
    value: str

    @field_validator("value", mode="before")
    @classmethod
    def _to_str(cls, v):
        return str(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else v


class Review(BaseModel):
    verdict: Literal["keep", "downgrade"]
    confidence: Literal["high", "medium", "low"]
    evidence: List[Evidence]
    explanation: str
    script: str


def build_user_message(features, scored):
    merged = {**features, **scored}
    return "用户数据：\n" + "\n".join(f"- {k}（{desc}）：{merged[k]}" for k, desc in FIELDS)


def call_review(user_message, api_key, model=MODEL):
    """返回 dict：review、raw、prompt_tokens、completion_tokens、latency_s、error。解析失败最多重试 1 次。"""
    client = OpenAI(api_key=api_key, base_url=BASE_URL, max_retries=0, timeout=60)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_message}]
    p_tok = c_tok = 0
    raw, err = None, None
    for attempt in (1, 2):
        t0 = time.time()
        try:
            r = client.chat.completions.create(model=model, messages=messages, temperature=0.0, max_tokens=900,
                                               response_format={"type": "json_object"}, extra_body={"enable_thinking": False})
        except APIStatusError as e:
            return {"review": None, "raw": None, "prompt_tokens": p_tok, "completion_tokens": c_tok, "latency_s": 0, "error": f"{e.status_code}:{getattr(e, 'code', None)}"}
        except Exception as e:
            return {"review": None, "raw": None, "prompt_tokens": p_tok, "completion_tokens": c_tok, "latency_s": 0, "error": type(e).__name__}
        p_tok += r.usage.prompt_tokens
        c_tok += r.usage.completion_tokens
        raw = r.choices[0].message.content
        try:
            return {"review": Review.model_validate(json.loads(raw)), "raw": raw, "prompt_tokens": p_tok, "completion_tokens": c_tok,
                    "latency_s": round(time.time() - t0, 2), "error": None}
        except (json.JSONDecodeError, ValidationError):
            err = "format_invalid"
    return {"review": None, "raw": raw, "prompt_tokens": p_tok, "completion_tokens": c_tok, "latency_s": 0, "error": err}


NUM = re.compile(r"\d+(?:\.\d+)?%?")


def _allowed_values(features, scored):
    vals = set()
    for k, _ in FIELDS:
        v = {**features, **scored}.get(k)
        try:
            v = float(v)
        except (TypeError, ValueError):
            continue
        vals.update({round(v, 4), round(v * 100, 2), round(v, 2), round(v, 1), round(v)})
    for m in NUM.findall(STATS_TEXT):  # 提示词里提供的历史统计允许被引用
        x = float(m.rstrip("%"))
        vals.update({x, x / 100})
    return vals


def number_check(text, features, scored):
    """只检查带小数点或百分号的数字是否出自输入或提示词里的历史统计。返回找不到的数字列表。"""
    vals = _allowed_values(features, scored)
    missing = []
    for m in NUM.findall(text):
        if "." not in m and "%" not in m:
            continue
        x = float(m.rstrip("%"))
        cands = {x, x / 100} if m.endswith("%") else {x}
        if not any(abs(c - v) <= max(0.011, 0.01 * abs(v)) for c in cands for v in vals):
            missing.append(m)
    return missing


SCRIPT_RULES = [
    (re.compile(r"\d折|折扣|优惠|赠送|赠品|免费|礼品|礼包|代金券|优惠券|返现|补贴|立减"), "疑似承诺折扣或赠品"),
    (re.compile(r"风险分|分桶|评分|风险等级|\b[RAT][1-6]\b"), "提及内部评分或分桶"),
    (re.compile(r"一定会(流失|取消|离开)|肯定会(流失|取消|离开|走)"), "暗示用户一定会流失"),
]


NEGATIONS = ("不", "避免", "勿", "无需", "没有", "别")


def script_screen(script):
    """返回话术里的疑似违规类型。命中词前 8 个字内出现否定词（如"不承诺折扣"）时不算违规。"""
    flags = []
    for pat, msg in SCRIPT_RULES:
        for m in pat.finditer(script):
            window = script[max(0, m.start() - 8):m.start()]
            if not any(n in window for n in NEGATIONS):
                flags.append(msg)
                break
    return flags
