# 客户续约风险研判：Agent 评测 Demo

一个个人项目的演示：用 Kaggle「WSDM - KKBox's Churn Prediction Challenge」的真实订阅数据，复刻"指标加权 → 风险分桶 × 金额分桶 → 优先级分层"的客户续约风险研判链路，用大模型为高风险用户生成给销售的风险说明，并补上系统化的评测、监控和回归。

**在线体验**：https://agent-eval-demo-enpscc4q7yw7xzaeszp5sa.streamlit.app/

> 教学演示：页面上的用户均为虚构，说明由大模型生成，不构成任何业务建议。
> 竞赛数据条款不允许再分发数据，所以本仓库**没有任何 KKBox 原始数据和用户 ID**，只有汇总参数和合成样例。

## 它做什么

1. 访客选择或修改一个虚构用户最近 4 周的行为；
2. 规则 v1（权重在 train 集上校准）给出风险分、风险桶 R、金额桶 A、优先级 T；
3. 若用户在高风险名单（T1/T2），冻结的 Reviewer（kimi-k3 + 提示词 v2）生成风险说明和沟通建议；
4. 自动检查：说明里的小数和百分比必须出自输入或历史统计；话术不得承诺折扣、提及内部评分、暗示一定会流失；
5. 每次请求记录到 Langfuse（耗时、token、报错、检查结果），访客可以点"有用/没用"。

## 成本与安全

- 全站实时调用每天最多 10 次（`DAILY_CAP`），每位访客最多 3 次；超限后自动降级为规则结果和预先生成的示例（`examples.json`）。
- 全站计数保存在进程内存里，应用重启会重置，只是尽力而为的保护；真正的兜底是 API Key 自身的额度。
- 模型只会看到特征数字，没有任何用户标识；Key 只放在部署平台的 secrets 里，不进仓库。

## 本地运行

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # 填入自己的 Key；该文件已被 .gitignore 忽略
streamlit run app.py
```

不配置 Key 也能运行：会降级为规则结果和预先生成的示例。

## 部署到 Streamlit Community Cloud

1. 把本仓库推送到 GitHub；
2. 在 share.streamlit.io 新建应用，选择本仓库，入口文件为 `app.py`；
3. 在应用的 Settings → Secrets 里填写：

```toml
DASHSCOPE_API_KEY = "..."          # 阿里云百炼的 API Key
LANGFUSE_PUBLIC_KEY = "..."
LANGFUSE_SECRET_KEY = "..."
LANGFUSE_HOST = "https://cloud.langfuse.com"
DAILY_CAP = 10
```

## 回归

- `tests/test_deterministic.py`：不调用大模型，每次提交由 GitHub Actions 运行。覆盖：规则打分与研究项目完整流程的一致性（40 个合成用例）、提示词指纹（确保与评测时冻结的版本一致）、解析与检查逻辑、限额逻辑。
- `tests/llm_regression.py`：每周一次真实模型小样本回归（需要仓库 secret `DASHSCOPE_API_KEY`），检查解析成功率、数字忠实度、话术违规、逾期用户不被下调、耗时 P95；低于阈值则工作流失败。

## 目录

```
app.py            Streamlit 界面
core/             特征、规则打分、Reviewer、限额、可观测性
core/assets/      从研究项目导出的冻结提示词、字段说明、历史统计、v1 参数
examples.json     预先生成的示例输出（额度用完时降级展示）
tests/            确定性检查与真实模型回归
tools/            生成示例的脚本
RESULTS.md        评测结果摘要（页面第二个标签页展示）
```
