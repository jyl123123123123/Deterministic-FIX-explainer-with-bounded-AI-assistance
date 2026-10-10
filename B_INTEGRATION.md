# B 模块：本地模板解释

Python 3.11+，无 LLM、API key 或运行时第三方依赖。保留 A 的 tokenizer、解析器、规范和校验逻辑。

从本目录运行：

```sh
PYTHONPATH=src python3 examples/template_demo.py
PYTHONPATH=src python3 -m pytest
```

pytest 未安装时，可在自己的虚拟环境中安装 `python3 -m pip install -e '.[test]'`。

C 可直接复用 examples/template_demo.py 的调用：

```python
from fix_explainer import TemplateExplanationProvider, explain_with_provider
result = explain_with_provider(message, TemplateExplanationProvider(), specification, errors)
summary = result['provider_summary']
findings = result['deterministic']['validation_errors']
fallback_used = result['fallback_used']
reason = result['fallback_reason']
```

message 来自 A 的 split_message；errors 为额外完整性/规范检查结果，不要重复传 message.errors，接口已经包含它们。provider 不主动执行校验，不能从没有 findings 推导交易成功。只有规范实际提供的字段名、枚举标签和业务名称会用于解释。

## 展示与隐私边界

provider_summary 是筛选后的英文纯文本，UI 应作为文本渲染，避免 HTML 注入。默认允许 tag 35、38、40、44、54、55、59、150、39、151、14、6。敏感标识符只提示值已隐藏；其他字段默认不展示。自定义 allowed_tags 只能缩小默认集合。发送方/接收方位于 Header，本来就不进入 A 的 body facts。账户、订单、参与方与登录标识等即使出现在 Body 也隐藏。字段名与枚举名来自输入规范，不由模板猜测；数量、价格、证券代码仍会显示，默认策略不等于对任意业务数据的完全匿名化。

确定性 context、fallback 保留原始诊断和数据，**并非脱敏输出**。C 应在受控的校验面板展示这些数据，不能把整个 result 当成可公开日志或可发给未来 LLM 的 payload。诊断自由文本与未知自由文本可能包含敏感值，因此摘要仅引用记录位置并隐藏自由文本；内置固定 unknown 文案可以原样显示。异常原因只显示异常类型，不显示可能带敏感数据的异常消息。

## 引用精度

原 context 只有 evidence_tags，重复 tag 无法区分。本次向 Body fact 添加 A 已有的 ordinal，向消息类型/目的 fact 添加 evidence_fields。`[tag=55; ordinal=7]` 表示原消息第 8 个 token（ordinal 从 0 开始，包含 malformed token 的位置）。C 可以用 message.fields 中 ordinal 找到字段。它不是 repeating-group 路径，也不验证重复组结构。旧 context 没有 ordinal 时明确标记 occurrence unavailable，不能精确定位重复字段。

`[validation_errors[i]]` 引用原始校验记录；缺失字段并不存在于消息中，tag 引用只是受影响的 tag，应以该校验记录为依据，不能当成字段存在证据。`[unknowns[i]]` 引用未知项。每个事实引用还保留 context 索引。

异常、空字符串或非字符串返回会调用现有 explain_deterministically；fallback_used 与 fallback_reason 标明回退，fallback 保留全部问题。第三方 provider 收到深拷贝，修改副本不能覆盖 deterministic。第一版没有模型语义校验；模板只复述已提供事实，不推导成交、因果或枚举意义。
