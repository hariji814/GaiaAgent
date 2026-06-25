# 工作流模式指南

> 🌐 [English](../../en/guides/workflows.md)
> **[← 返回 README](../../../README.zh.md)** | [架构](../architecture.md) | [协议规范](../../../PROTOCOL.zh.md) | [API 参考](../api-reference.md)
>
> AURC Agent 的五种经典编排模式，由 Claude 驱动

---

## 目录

1. [概述](#概述)
2. [模式 1: 提示链](#模式-1-提示链)
3. [模式 2: 智能路由](#模式-2-智能路由)
4. [模式 3: 并行扇出](#模式-3-并行扇出)
5. [模式 4: 编排器-工人](#模式-4-编排器-工人)
6. [模式 5: 评估器-优化器](#模式-5-评估器-优化器)
7. [组合模式](#组合模式)
8. [Claude 集成用于动态工作流](#claude-集成用于动态工作流)

---

## 概述

AURC 实现了 Anthropic "构建有效 Agent" 指南中的 5 种经典 Agent 编排模式。每种模式解决不同类别的问题。

```
┌──────────────────────────────────────────────────────────────────┐
│                    DynamicWorkflowEngine                         │
│                                                                  │
│  ┌──────────────┐  ┌───────────────┐  ┌──────────────────┐      │
│  │ PromptChain  │  │ 智能路由      │  │ 并行扇出         │      │
│  └──────────────┘  └───────────────┘  └──────────────────┘      │
│  ┌──────────────────────┐  ┌─────────────────────────────┐      │
│  │ 编排器-工人          │  │ 评估器-优化器               │      │
│  └──────────────────────┘  └─────────────────────────────┘      │
│                                                                  │
│  Powered by: AURC Harness + MessageRouter + Claude LLM           │
└──────────────────────────────────────────────────────────────────┘
```

### 模式选择指南

| 模式 | 何时使用 | 关键特征 |
|---|---|---|
| **提示链** | 有序子任务 | 第 N 步的输出 → 第 N+1 步的输入 |
| **路由** | 不同输入类型 | 分类器选择最佳处理函数 |
| **并行扇出** | 独立子任务 | 并发执行，结果聚合 |
| **编排器-工人** | 动态分解 | LLM 在运行时决定子任务 |
| **评估器-优化器** | 质量关键 | 迭代的"生成-评估-改进"循环 |

### 工作流结果

所有模式都返回一个 `WorkflowResult`：

```python
@dataclass
class WorkflowResult:
    success: bool                  # 是否成功
    output: Any                    # 输出数据
    steps_completed: int           # 已完成步骤
    total_steps: int               # 总步骤数
    errors: list[str]              # 错误消息
    metadata: dict[str, Any]       # 附加元数据
```

---

## 模式 1: 提示链

顺序流水线，每步的输出成为下一步的输入。

```
Input → [Step 1] → [Step 2] → [Step 3] → Output
```

**适用场景:**
- 任务可分解为有序子任务
- 每步为下一步转换数据
- 质量依赖正确顺序

### 代码示例

```python
from gaiaagent.workflows.orchestrator import PromptChain

# 定义步骤函数
async def translate(text: str) -> str:
    """翻译为英文"""
    return f"[EN] {text}"

async def summarize(text: str) -> str:
    """摘要文本"""
    return f"Summary: {text[:100]}..."

async def format_output(text: str) -> str:
    """格式化输出"""
    return f"<formatted>{text}</formatted>"

# 创建并执行链
chain = PromptChain(
    steps=[translate, summarize, format_output],
    step_names=["translate", "summarize", "format"],
)

result = await chain.execute("这是一段需要处理的中文文本")
print(f"Success: {result.success}")           # True
print(f"Output: {result.output}")             # "<formatted>Summary: [EN] 这是一段...</formatted>"
print(f"Steps: {result.steps_completed}/{result.total_steps}")  # 3/3
```

### 错误处理

如果任何步骤失败，链停止并返回部分结果:

```python
result = await chain.execute(input_data)
if not result.success:
    print(f"Failed at step: {result.steps_completed}")
    print(f"Errors: {result.errors}")
    print(f"Partial output: {result.output}")
```

---

## 模式 2: 智能路由

根据内容分类将输入路由到最佳处理函数。

```
              ┌→ Handler A (for type 1)
Input → Classify → Handler B (for type 2)
              └→ Handler C (for type 3)
```

**适用场景:**
- 输入类型差异大
- 不同输入需要不同专业处理函数
- 分类可以可靠完成

### 代码示例

```python
from gaiaagent.workflows.orchestrator import IntelligentRouter

router = IntelligentRouter()

# 定义路由
async def handle_code_request(input_data):
    return {"type": "code", "response": "Generated code..."}

async def handle_research_request(input_data):
    return {"type": "research", "report": "Research findings..."}

async def handle_general_query(input_data):
    return {"type": "general", "answer": "General response..."}

router.add_route("code", handle_code_request)
router.add_route("research", handle_research_request)
router.add_route("general", handle_general_query)

# 设置分类器（可使用 Claude!）
async def classify(input_data):
    text = str(input_data).lower()
    if any(kw in text for kw in ["code", "implement", "function", "class"]):
        return "code"
    elif any(kw in text for kw in ["research", "paper", "study", "analyze"]):
        return "research"
    return "general"

router.set_classifier(classify)

# 执行
result = await router.execute("Implement a binary search in Python")
print(f"Route: {result.metadata['route']}")  # "code"
print(f"Output: {result.output}")
```

### 使用 Claude 作为分类器

```python
from gaiaagent.integrations.claude import ClaudeLLM

llm = ClaudeLLM(model="claude-sonnet-4-20250514")

async def claude_classifier(input_data):
    response = await llm.ask(
        prompt=f"Classify this request into one of: code, research, general. "
               f"Reply with just the category name.\n\nRequest: {input_data}",
    )
    return response.text.strip().lower()

router.set_classifier(claude_classifier)
```

---

## 模式 3: 并行扇出

并发运行多个任务并聚合结果。

```
          ┌→ Task A ──→ Result A ─┐
Input ────┼→ Task B ──→ Result B ──┼──→ Aggregated Output
          └→ Task C ──→ Result C ─┘
```

**适用场景:**
- 子任务互相独立
- 延迟重要（并行更快）
- 结果可以聚合

### 三种模式

| 模式 | 行为 |
|------|--------|
| `"all"` | 等待所有任务，收集所有结果 |
| `"first"` | 返回首个成功结果，取消其他 |
| `"vote"` | 结果多数投票 |

### 代码示例: 全量模式

```python
from gaiaagent.workflows.orchestrator import ParallelFanOut

async def search_arxiv(query):
    return {"source": "arxiv", "papers": [f"Paper about {query}"]}

async def search_web(query):
    return {"source": "web", "results": [f"Web result about {query}"]}

async def search_patents(query):
    return {"source": "patents", "patents": [f"Patent about {query}"]}

fan_out = ParallelFanOut(
    tasks=[search_arxiv, search_web, search_patents],
    mode="all",
    task_names=["arxiv", "web", "patents"],
)

result = await fan_out.execute("AI agent protocols")
print(f"Success: {result.success}")
print(f"All results: {result.output}")  # 包含 3 个结果的列表
print(f"Completed: {result.steps_completed}/{result.total_steps}")
```

### 代码示例: 最快模式

```python
fan_out = ParallelFanOut(
    tasks=[slow_search, medium_search, fast_search],
    mode="first",
)

result = await fan_out.execute("query")
# 最快完成后立即返回
# 剩余任务被取消
```

### 代码示例: 投票模式

```python
async def classifier_a(text): return "positive"
async def classifier_b(text): return "positive"
async def classifier_c(text): return "negative"

fan_out = ParallelFanOut(
    tasks=[classifier_a, classifier_b, classifier_c],
    mode="vote",
)

result = await fan_out.execute("This product is great!")
print(f"Winner: {result.output}")           # "positive"（2/3 票）
print(f"Votes: {result.metadata['votes']}")  # {"positive": 2, "negative": 1}
```

---

## 模式 4: 编排器-工人

动态任务分解，编排器（通常为 Claude）在运行时决定需要什么子任务。

```
Input → Orchestrator (Claude) → [Worker A, Worker B, ...] → Synthesizer → Output
```

**适用场景:**
- 子任务无法预先确定
- 任务需要自适应规划
- 复杂、开放式问题

### 代码示例

```python
from gaiaagent.workflows.orchestrator import OrchestratorWorkers

# 定义编排器（使用 Claude 分解）
async def orchestrator(input_data):
    """分析输入并返回子任务定义列表。"""
    # 生产环境中会调用 Claude
    return [
        {"worker": "researcher", "task": f"Research: {input_data}"},
        {"worker": "coder", "task": f"Implement: {input_data}"},
        {"worker": "reviewer", "task": f"Review: {input_data}"},
    ]

# 定义工人
async def researcher(task):
    return {"findings": f"Research results for: {task}"}

async def coder(task):
    return {"code": f"Implementation for: {task}"}

async def reviewer(task):
    return {"review": f"Review of: {task}"}

# 定义综合器
async def synthesizer(results):
    combined = {}
    for r in results:
        combined.update(r["result"])
    return combined

# 创建并执行
ow = OrchestratorWorkers(
    orchestrator=orchestrator,
    workers={
        "researcher": researcher,
        "coder": coder,
        "reviewer": reviewer,
    },
    synthesizer=synthesizer,
)

result = await ow.execute("Build a web scraper for news sites")
print(f"Subtasks: {result.metadata['subtasks']}")     # 3
print(f"Workers used: {result.metadata['workers_used']}")  # 3
print(f"Output: {result.output}")
```

---

## 模式 5: 评估器-优化器

迭代优化循环：生成输出、评估质量、基于反馈改进、重复。

```
                ┌──────────────────────┐
                │                      │
Input → Generator → Output → Evaluator ──(pass?)──→ Done
                ↑                      │
                └──── feedback ────────┘ (fail)
```

**适用场景:**
- 质量至关重要
- 有明确的评估标准
- 输出可以迭代改进
- 你知道什么时候输出"足够好"

### 代码示例

```python
from gaiaagent.workflows.orchestrator import EvaluatorOptimizer, EvalResult

# 生成器：生成输出，接收上一次迭代的反馈
async def generator(input_data, feedback=None):
    if feedback:
        return f"Improved version based on: {feedback}"
    return f"Initial version for: {input_data}"

# 评估器：为输出评分
async def evaluator(output):
    quality = len(str(output)) / 100.0  # 简化的质量指标
    if quality >= 0.8:
        return EvalResult(score=quality, passed=True, feedback="Good enough!")
    return EvalResult(
        score=quality,
        passed=False,
        feedback=f"Quality is {quality:.2f}, needs more detail and depth",
    )

# 创建并执行
optimizer = EvaluatorOptimizer(
    generator=generator,
    evaluator=evaluator,
    max_iterations=5,
    quality_threshold=0.8,
)

result = await optimizer.execute("Write a comprehensive report on AI safety")
print(f"Success: {result.success}")
print(f"Iterations: {result.steps_completed}")
print(f"Final score: {result.metadata.get('final_score')}")
print(f"History: {result.metadata.get('iterations')}")
# [
#   {"iteration": 1, "score": 0.45, "passed": False, "feedback": "..."},
#   {"iteration": 2, "score": 0.82, "passed": True, "feedback": "Good enough!"}
# ]
```

---

## 组合模式

`DynamicWorkflowEngine` 提供统一接口来组合模式。

```python
from gaiaagent.workflows.orchestrator import DynamicWorkflowEngine

engine = DynamicWorkflowEngine()

# 链：顺序流水线
result = await engine.chain(
    [translate, summarize, format_output],
    initial_input="Hello world",
)

# 路由：智能分发
result = await engine.route(
    input_data=user_request,
    routes={"code": handle_code, "research": handle_research},
    classifier=classify_request,
)

# 并行：并发执行
result = await engine.parallel(
    [search_arxiv, search_web, search_patents],
    input_data="AI agents",
    mode="all",
)

# 编排：动态分解
result = await engine.orchestrate(
    orchestrator=claude_decomposer,
    workers={"research": researcher, "code": coder},
    input_data="Build a web scraper",
)

# 优化：迭代改进
result = await engine.optimize(
    generator=draft_generator,
    evaluator=quality_evaluator,
    input_data="Write a technical blog post",
    max_iterations=3,
    quality_threshold=0.9,
)
```

### 嵌套模式示例

```python
# 使用并行工人编排，链式后处理
async def parallel_researcher(task):
    fan_out = ParallelFanOut(
        [search_arxiv, search_web],
        mode="all",
    )
    return await fan_out.execute(task)

ow = OrchestratorWorkers(
    orchestrator=claude_decomposer,
    workers={
        "research": parallel_researcher,
        "code": coder,
    },
    synthesizer=chain_synthesizer,
)

result = await ow.execute("Comprehensive analysis of AI agent protocols")
```

---

## Claude 集成用于动态工作流

使用 Claude 作为编排决策的推理引擎。

### 设置

```python
from gaiaagent.integrations.claude import ClaudeLLM, ClaudeTool, ClaudeAgent

llm = ClaudeLLM(
    model="claude-sonnet-4-20250514",
    system_prompt="You are an expert task decomposer for AI agent workflows.",
)
```

### Claude 驱动的编排器

```python
async def claude_orchestrator(input_data):
    """使用 Claude 将任务分解为子任务。"""
    response = await llm.ask(
        prompt=f"Decompose this task into subtasks. For each subtask, specify "
               f"a worker name and task description. Reply as JSON array.\n\n"
               f"Task: {input_data}\n\n"
               f"Available workers: researcher, coder, reviewer",
    )
    import json
    return json.loads(response.text)
```

### Claude 工具使用

```python
# 定义 Claude 可调用的工具
tools = [
    ClaudeTool(
        name="web-search",
        description="Search the web for information",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": ["query"],
        },
        handler=web_search_function,
    ),
    ClaudeTool(
        name="read-document",
        description="Read a document by URL",
        input_schema={
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
        handler=read_document_function,
    ),
]

# 运行 Agentic 循环 — Claude 决定调用哪些工具。
# 当 `claude` CLI 在 PATH 上时,此处委托给 `claude -p --output-format stream-json`;
# 否则用内置 anthropic 循环。传入带 Python handler 的 `tools` 会强制走内置路径
# (CLI 原生运行自己的工具;把 handler 暴露给 CLI 是 MCP 桥,见 LOOP_ROADMAP.zh.md)。
response = await llm.agentic_loop(
    prompt="Research the latest developments in AI agent protocols",
    tools=tools,
    max_turns=10,
)
print(response.text)
```

### ClaudeAgent 基类

```python
from gaiaagent.sdk.decorators import aurc_agent, skill
from gaiaagent.integrations.claude import ClaudeAgent

@aurc_agent(
    id="aurc:myproject/smart-researcher:v1.0",
    display_name="Smart Research Agent",
)
class SmartResearchAgent(ClaudeAgent):

    def __init__(self):
        super().__init__(
            model="claude-sonnet-4-20250514",
            system_prompt="You are a research assistant.",
        )

    @skill("smart-research", description="AI-powered research")
    async def smart_research(self, query: str) -> dict:
        response = await self.claude.ask(
            prompt=f"Research: {query}",
            tools=self.get_claude_tools(),
        )
        return {"answer": response.text, "tool_calls": len(response.tool_calls)}
```

---

*另请参阅: [架构深入解析](../architecture.md) | [安全指南](security.md) | [API 参考](../api-reference.md)*
