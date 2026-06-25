# Workflow Patterns Guide

> 🌐 [中文版](../../zh/guides/workflows.md)
> **[← Back to README](../../../README.md)** | [Architecture](../architecture.md) | [Protocol Spec](../../../PROTOCOL.md) | [API Reference](../api-reference.md)
>
> Five canonical orchestration patterns for AURC agents, powered by Claude

---

## Table of Contents

1. [Overview](#overview)
2. [Pattern 1: Prompt Chaining](#pattern-1-prompt-chaining)
3. [Pattern 2: Intelligent Routing](#pattern-2-intelligent-routing)
4. [Pattern 3: Parallel Fan-Out](#pattern-3-parallel-fan-out)
5. [Pattern 4: Orchestrator-Workers](#pattern-4-orchestrator-workers)
6. [Pattern 5: Evaluator-Optimizer](#pattern-5-evaluator-optimizer)
7. [Combining Patterns](#combining-patterns)
8. [Claude Integration for Dynamic Workflows](#claude-integration-for-dynamic-workflows)

---

## Overview

AURC implements the 5 canonical agent orchestration patterns from Anthropic's "Building Effective Agents" guide. Each pattern solves a different class of problem.

```
┌──────────────────────────────────────────────────────────────────┐
│                    DynamicWorkflowEngine                         │
│                                                                  │
│  ┌──────────────┐  ┌───────────────┐  ┌──────────────────┐      │
│  │ PromptChain  │  │ Intelligent   │  │ ParallelFanOut   │      │
│  │              │  │ Router        │  │                  │      │
│  └──────────────┘  └───────────────┘  └──────────────────┘      │
│  ┌──────────────────────┐  ┌─────────────────────────────┐      │
│  │ OrchestratorWorkers  │  │ EvaluatorOptimizer          │      │
│  │                      │  │                             │      │
│  └──────────────────────┘  └─────────────────────────────┘      │
│                                                                  │
│  Powered by: AURC Harness + MessageRouter + Claude LLM           │
└──────────────────────────────────────────────────────────────────┘
```

### Pattern Selection Guide

| Pattern | When to Use | Key Characteristic |
|---|---|---|
| **Prompt Chaining** | Ordered subtasks, data transformation | Output of step N → input of step N+1 |
| **Routing** | Varied input types | Classifier selects best handler |
| **Parallel Fan-Out** | Independent subtasks | Concurrent execution, result aggregation |
| **Orchestrator-Workers** | Dynamic decomposition | LLM decides subtasks at runtime |
| **Evaluator-Optimizer** | Quality-critical tasks | Iterative generate-evaluate-improve loop |

### WorkflowResult

All patterns return a `WorkflowResult`:

```python
@dataclass
class WorkflowResult:
    success: bool                  # Whether execution succeeded
    output: Any                    # The output data
    steps_completed: int           # Steps completed
    total_steps: int               # Total steps
    errors: list[str]              # Error messages
    metadata: dict[str, Any]       # Additional metadata
```

---

## Pattern 1: Prompt Chaining

Sequential pipeline where the output of each step becomes the input to the next.

```
Input → [Step 1] → [Step 2] → [Step 3] → Output
```

**Use when:**
- Task can be decomposed into ordered subtasks
- Each step transforms data for the next
- Quality depends on correct ordering

### Code Example

```python
from gaiaagent.workflows.orchestrator import PromptChain

# Define step functions
async def translate(text: str) -> str:
    """Translate to English"""
    return f"[EN] {text}"

async def summarize(text: str) -> str:
    """Summarize the text"""
    return f"Summary: {text[:100]}..."

async def format_output(text: str) -> str:
    """Format for presentation"""
    return f"<formatted>{text}</formatted>"

# Create and execute the chain
chain = PromptChain(
    steps=[translate, summarize, format_output],
    step_names=["translate", "summarize", "format"],
)

result = await chain.execute("这是一段需要处理的中文文本")
print(f"Success: {result.success}")           # True
print(f"Output: {result.output}")             # "<formatted>Summary: [EN] 这是一段...</formatted>"
print(f"Steps: {result.steps_completed}/{result.total_steps}")  # 3/3
```

### Error Handling

If any step fails, the chain stops and returns partial results:

```python
result = await chain.execute(input_data)
if not result.success:
    print(f"Failed at step: {result.steps_completed}")
    print(f"Errors: {result.errors}")
    print(f"Partial output: {result.output}")
```

---

## Pattern 2: Intelligent Routing

Routes input to the best handler based on content classification.

```
              ┌→ Handler A (for type 1)
Input → Classify → Handler B (for type 2)
              └→ Handler C (for type 3)
```

**Use when:**
- Input types vary significantly
- Different inputs need different specialized handlers
- Classification can be done reliably

### Code Example

```python
from gaiaagent.workflows.orchestrator import IntelligentRouter

router = IntelligentRouter()

# Define routes
async def handle_code_request(input_data):
    return {"type": "code", "response": "Generated code..."}

async def handle_research_request(input_data):
    return {"type": "research", "report": "Research findings..."}

async def handle_general_query(input_data):
    return {"type": "general", "answer": "General response..."}

router.add_route("code", handle_code_request)
router.add_route("research", handle_research_request)
router.add_route("general", handle_general_query)

# Set the classifier (can use Claude!)
async def classify(input_data):
    text = str(input_data).lower()
    if any(kw in text for kw in ["code", "implement", "function", "class"]):
        return "code"
    elif any(kw in text for kw in ["research", "paper", "study", "analyze"]):
        return "research"
    return "general"

router.set_classifier(classify)

# Execute
result = await router.execute("Implement a binary search in Python")
print(f"Route: {result.metadata['route']}")  # "code"
print(f"Output: {result.output}")
```

### Using Claude as Classifier

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

## Pattern 3: Parallel Fan-Out

Run multiple tasks concurrently and aggregate results.

```
          ┌→ Task A ──→ Result A ─┐
Input ────┼→ Task B ──→ Result B ──┼──→ Aggregated Output
          └→ Task C ──→ Result C ─┘
```

**Use when:**
- Subtasks are independent
- Latency matters (parallel is faster)
- Results can be aggregated

### Three Modes

| Mode | Behavior |
|------|--------|
| `"all"` | Wait for all tasks, collect all results |
| `"first"` | Return first successful result, cancel others |
| `"vote"` | Majority vote across results |

### Code Example: All Mode

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
print(f"All results: {result.output}")  # List of 3 results
print(f"Completed: {result.steps_completed}/{result.total_steps}")
```

### Code Example: First Mode

```python
fan_out = ParallelFanOut(
    tasks=[slow_search, medium_search, fast_search],
    mode="first",
)

result = await fan_out.execute("query")
# Returns as soon as the fastest one completes
# Remaining tasks are cancelled
```

### Code Example: Vote Mode

```python
async def classifier_a(text): return "positive"
async def classifier_b(text): return "positive"
async def classifier_c(text): return "negative"

fan_out = ParallelFanOut(
    tasks=[classifier_a, classifier_b, classifier_c],
    mode="vote",
)

result = await fan_out.execute("This product is great!")
print(f"Winner: {result.output}")           # "positive" (2/3 votes)
print(f"Votes: {result.metadata['votes']}")  # {"positive": 2, "negative": 1}
```

---

## Pattern 4: Orchestrator-Workers

Dynamic task decomposition where the orchestrator (typically Claude) decides what subtasks are needed at runtime.

```
Input → Orchestrator (Claude) → [Worker A, Worker B, ...] → Synthesizer → Output
```

**Use when:**
- Subtasks cannot be predetermined
- Task requires adaptive planning
- Complex, open-ended problems

### Code Example

```python
from gaiaagent.workflows.orchestrator import OrchestratorWorkers

# Define the orchestrator (uses Claude to decompose)
async def orchestrator(input_data):
    """Analyze input and return list of subtask definitions."""
    # In production, this would call Claude
    return [
        {"worker": "researcher", "task": f"Research: {input_data}"},
        {"worker": "coder", "task": f"Implement: {input_data}"},
        {"worker": "reviewer", "task": f"Review: {input_data}"},
    ]

# Define workers
async def researcher(task):
    return {"findings": f"Research results for: {task}"}

async def coder(task):
    return {"code": f"Implementation for: {task}"}

async def reviewer(task):
    return {"review": f"Review of: {task}"}

# Define synthesizer
async def synthesizer(results):
    combined = {}
    for r in results:
        combined.update(r["result"])
    return combined

# Create and execute
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

## Pattern 5: Evaluator-Optimizer

Iterative refinement loop: generate output, evaluate quality, improve based on feedback, repeat.

```
                ┌──────────────────────┐
                │                      │
Input → Generator → Output → Evaluator ──(pass?)──→ Done
                ↑                      │
                └──── feedback ────────┘ (fail)
```

**Use when:**
- Quality is critical
- There are clear evaluation criteria
- Output can be iteratively improved
- You know when output is "good enough"

### Code Example

```python
from gaiaagent.workflows.orchestrator import EvaluatorOptimizer, EvalResult

# Generator: produces output, takes feedback from previous iteration
async def generator(input_data, feedback=None):
    if feedback:
        return f"Improved version based on: {feedback}"
    return f"Initial version for: {input_data}"

# Evaluator: scores the output
async def evaluator(output):
    quality = len(str(output)) / 100.0  # Simplified quality metric
    if quality >= 0.8:
        return EvalResult(score=quality, passed=True, feedback="Good enough!")
    return EvalResult(
        score=quality,
        passed=False,
        feedback=f"Quality is {quality:.2f}, needs more detail and depth",
    )

# Create and execute
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

## Combining Patterns

The `DynamicWorkflowEngine` provides a unified interface for combining patterns.

```python
from gaiaagent.workflows.orchestrator import DynamicWorkflowEngine

engine = DynamicWorkflowEngine()

# Chain: sequential pipeline
result = await engine.chain(
    [translate, summarize, format_output],
    initial_input="Hello world",
)

# Route: intelligent dispatch
result = await engine.route(
    input_data=user_request,
    routes={"code": handle_code, "research": handle_research},
    classifier=classify_request,
)

# Parallel: concurrent execution
result = await engine.parallel(
    [search_arxiv, search_web, search_patents],
    input_data="AI agents",
    mode="all",
)

# Orchestrate: dynamic decomposition
result = await engine.orchestrate(
    orchestrator=claude_decomposer,
    workers={"research": researcher, "code": coder},
    input_data="Build a web scraper",
)

# Optimize: iterative refinement
result = await engine.optimize(
    generator=draft_generator,
    evaluator=quality_evaluator,
    input_data="Write a technical blog post",
    max_iterations=3,
    quality_threshold=0.9,
)
```

### Nested Pattern Example

```python
# Orchestrate with parallel workers and chain post-processing
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

## Claude Integration for Dynamic Workflows

Use Claude as the reasoning engine for orchestration decisions.

### Setup

```python
from gaiaagent.integrations.claude import ClaudeLLM, ClaudeTool, ClaudeAgent

llm = ClaudeLLM(
    model="claude-sonnet-4-20250514",
    system_prompt="You are an expert task decomposer for AI agent workflows.",
)
```

### Claude-Powered Orchestrator

```python
async def claude_orchestrator(input_data):
    """Use Claude to decompose a task into subtasks."""
    response = await llm.ask(
        prompt=f"Decompose this task into subtasks. For each subtask, specify "
               f"a worker name and task description. Reply as JSON array.\n\n"
               f"Task: {input_data}\n\n"
               f"Available workers: researcher, coder, reviewer",
    )
    import json
    return json.loads(response.text)
```

### Claude with Tool Use

```python
# Define tools that Claude can call
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

# Run agentic loop — Claude decides which tools to call.
# When the `claude` CLI is on PATH, this delegates to `claude -p --output-format
# stream-json`; otherwise it uses the built-in anthropic-based loop. Passing
# `tools` with Python handlers forces the built-in path (the CLI runs its own
# tools natively; exposing handlers to it is the MCP bridge, see LOOP_ROADMAP.md).
response = await llm.agentic_loop(
    prompt="Research the latest developments in AI agent protocols",
    tools=tools,
    max_turns=10,
)
print(response.text)
```

### ClaudeAgent Base Class

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

*See also: [Architecture Deep Dive](../architecture.md) | [Security Guide](security.md) | [API Reference](../api-reference.md)*
