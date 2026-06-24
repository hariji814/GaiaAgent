"""AURC Dynamic Workflow Orchestrator.
AURC 动态工作流编排器

Implements the 5 canonical agent orchestration patterns from
Anthropic's "Building Effective Agents" guide, integrated with
the AURC runtime harness and message bus.

Patterns / 模式:
1. Prompt Chaining — sequential pipeline / 顺序流水线
2. Routing — intelligent task dispatch / 智能任务分发
3. Parallelization — concurrent fan-out / 并发扇出
4. Orchestrator-Workers — dynamic task decomposition / 动态任务分解
5. Evaluator-Optimizer — iterative refinement / 迭代优化

Architecture / 架构:

    ┌──────────────────────────────────────────┐
    │  DynamicWorkflowOrchestrator              │
    │                                          │
    │  ┌──────────┐  ┌──────────┐  ┌────────┐ │
    │  │ Pipeline │  │ Router   │  │ FanOut │ │
    │  └──────────┘  └──────────┘  └────────┘ │
    │  ┌──────────────┐  ┌─────────────────┐  │
    │  │ Orch-Workers │  │ Eval-Optimizer  │  │
    │  └──────────────┘  └─────────────────┘  │
    │                                          │
    │  Powered by: AURC Harness + Claude LLM   │
    └──────────────────────────────────────────┘
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

from ..core.message import AURCMessage, MessageBody
from ..core.types import MessageDirection
from ..bus.router import MessageRouter

logger = logging.getLogger(__name__)

# Type aliases / 类型别名
SkillHandler = Callable[..., Awaitable[Any]]
"""Async function that handles a skill invocation."""


@dataclass
class WorkflowResult:
    """Result of a workflow execution. 工作流执行结果"""

    success: bool
    output: Any = None
    steps_completed: int = 0
    total_steps: int = 0
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


# =============================================================================
# Pattern 1: Prompt Chaining / 模式 1: 提示链
# =============================================================================


class PromptChain:
    """Sequential pipeline — output of step N becomes input to step N+1.
    顺序流水线 — 步骤 N 的输出成为步骤 N+1 的输入

    Use when / 适用场景:
    - Task can be decomposed into ordered subtasks / 任务可分解为有序子任务
    - Each step transforms data for the next / 每步为下一步转换数据
    - Quality depends on correct ordering / 质量依赖正确顺序

    Example: Translate → Summarize → Format
    """

    def __init__(self, steps: list[SkillHandler], step_names: list[str] | None = None) -> None:
        self._steps = steps
        self._names = step_names or [f"step_{i}" for i in range(len(steps))]

    async def execute(self, initial_input: Any) -> WorkflowResult:
        """Execute the chain sequentially. 顺序执行链"""
        current = initial_input
        errors: list[str] = []

        for i, (step, name) in enumerate(zip(self._steps, self._names)):
            try:
                logger.info("PromptChain: executing step %d/%d (%s)", i + 1, len(self._steps), name)
                current = await step(current)
            except Exception as e:
                errors.append(f"Step {name} failed: {e}")
                return WorkflowResult(
                    success=False,
                    output=current,
                    steps_completed=i,
                    total_steps=len(self._steps),
                    errors=errors,
                )

        return WorkflowResult(
            success=True,
            output=current,
            steps_completed=len(self._steps),
            total_steps=len(self._steps),
            errors=errors,
        )


# =============================================================================
# Pattern 2: Routing / 模式 2: 路由
# =============================================================================


class IntelligentRouter:
    """Routes input to the best handler based on content.
    根据内容将输入路由到最佳处理函数

    Uses Claude (or a simple classifier) to decide which handler to invoke.

    Use when / 适用场景:
    - Input types vary significantly / 输入类型差异大
    - Different inputs need different specialized handlers / 不同输入需要不同专业处理函数
    - Classification can be done reliably / 分类可以可靠完成
    """

    def __init__(self) -> None:
        self._routes: dict[str, SkillHandler] = {}
        self._classifier: Callable[[Any], Awaitable[str]] | None = None

    def add_route(self, name: str, handler: SkillHandler) -> None:
        """Add a named route with its handler. 添加命名路由及其处理函数"""
        self._routes[name] = handler

    def set_classifier(self, classifier: Callable[[Any], Awaitable[str]]) -> None:
        """Set the routing classifier function.
        设置路由分类函数

        The classifier receives input and returns a route name.
        """
        self._classifier = classifier

    async def execute(self, input_data: Any) -> WorkflowResult:
        """Route and execute. 路由并执行"""
        if not self._classifier:
            return WorkflowResult(
                success=False,
                errors=["No classifier set"],
            )

        try:
            route_name = await self._classifier(input_data)
            handler = self._routes.get(route_name)

            if not handler:
                return WorkflowResult(
                    success=False,
                    errors=[f"Unknown route: {route_name}. Available: {list(self._routes.keys())}"],
                )

            logger.info("Router: classified as '%s'", route_name)
            result = await handler(input_data)
            return WorkflowResult(
                success=True,
                output=result,
                steps_completed=1,
                total_steps=1,
                metadata={"route": route_name},
            )

        except Exception as e:
            return WorkflowResult(success=False, errors=[str(e)])


# =============================================================================
# Pattern 3: Parallelization / 模式 3: 并行化
# =============================================================================


class ParallelFanOut:
    """Concurrent fan-out — run multiple tasks simultaneously.
    并发扇出 — 同时运行多个任务

    Use when / 适用场景:
    - Subtasks are independent / 子任务互相独立
    - Latency matters (parallel is faster) / 延迟重要（并行更快）
    - Results can be aggregated / 结果可以聚合

    Modes / 模式:
    - "all": wait for all tasks, aggregate results / 等待所有任务，聚合结果
    - "first": return first successful result / 返回首个成功结果
    - "vote": majority vote across results / 结果多数投票
    """

    def __init__(
        self,
        tasks: list[SkillHandler],
        mode: str = "all",
        task_names: list[str] | None = None,
    ) -> None:
        self._tasks = tasks
        self._mode = mode
        self._names = task_names or [f"task_{i}" for i in range(len(tasks))]

    async def execute(self, input_data: Any) -> WorkflowResult:
        """Execute tasks in parallel. 并行执行任务"""
        if self._mode == "all":
            return await self._execute_all(input_data)
        elif self._mode == "first":
            return await self._execute_first(input_data)
        elif self._mode == "vote":
            return await self._execute_vote(input_data)
        else:
            return WorkflowResult(success=False, errors=[f"Unknown mode: {self._mode}"])

    async def _execute_all(self, input_data: Any) -> WorkflowResult:
        """Run all tasks and collect all results."""
        coros = [self._run_task(i, task, input_data) for i, task in enumerate(self._tasks)]
        results = await asyncio.gather(*coros, return_exceptions=True)

        successes = []
        errors = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                errors.append(f"{self._names[i]}: {result}")
            else:
                successes.append(result)

        return WorkflowResult(
            success=len(errors) == 0,
            output=successes,
            steps_completed=len(successes),
            total_steps=len(self._tasks),
            errors=errors,
        )

    async def _execute_first(self, input_data: Any) -> WorkflowResult:
        """Return the first successful result."""
        tasks = [asyncio.create_task(self._run_task(i, t, input_data)) for i, t in enumerate(self._tasks)]

        for completed in asyncio.as_completed(tasks):
            try:
                result = await completed
                # Cancel remaining tasks / 取消剩余任务
                for t in tasks:
                    t.cancel()
                return WorkflowResult(success=True, output=result, steps_completed=1, total_steps=len(self._tasks))
            except Exception:
                continue

        return WorkflowResult(success=False, errors=["All tasks failed"])

    async def _execute_vote(self, input_data: Any) -> WorkflowResult:
        """Majority vote across results."""
        result = await self._execute_all(input_data)
        if not result.success and not result.output:
            return result

        # Simple majority vote / 简单多数投票
        from collections import Counter
        votes = Counter(str(r) for r in result.output)
        winner = votes.most_common(1)[0]

        return WorkflowResult(
            success=True,
            output=winner[0],
            steps_completed=len(result.output),
            total_steps=len(self._tasks),
            metadata={"votes": dict(votes), "winner_count": winner[1]},
        )

    async def _run_task(self, index: int, task: SkillHandler, input_data: Any) -> Any:
        """Run a single task with error context."""
        try:
            return await task(input_data)
        except Exception as e:
            raise RuntimeError(f"{self._names[index]} failed: {e}") from e


# =============================================================================
# Pattern 4: Orchestrator-Workers / 模式 4: 编排器-工人
# =============================================================================


class OrchestratorWorkers:
    """Dynamic task decomposition — orchestrator decides subtasks at runtime.
    动态任务分解 — 编排器在运行时决定子任务

    This is the most "dynamic" pattern. The orchestrator (typically Claude)
    analyzes the input, decides what subtasks are needed, delegates to workers,
    and synthesizes the final result.

    Use when / 适用场景:
    - Subtasks cannot be predetermined / 子任务无法预先确定
    - Task requires adaptive planning / 任务需要自适应规划
    - Complex, open-ended problems / 复杂、开放式问题

    Architecture / 架构:
        Input → Orchestrator (Claude) → [Worker A, Worker B, ...] → Synthesis
    """

    def __init__(
        self,
        orchestrator: Callable[[Any], Awaitable[list[dict]]],
        workers: dict[str, SkillHandler],
        synthesizer: Callable[[list[Any]], Awaitable[Any]] | None = None,
    ) -> None:
        """
        Args:
            orchestrator: Function that takes input and returns list of
                         subtask definitions: [{"worker": "name", "task": "..."}]
            workers: Dict of worker name → handler function
            synthesizer: Optional function to combine worker results
        """
        self._orchestrator = orchestrator
        self._workers = workers
        self._synthesizer = synthesizer

    async def execute(self, input_data: Any) -> WorkflowResult:
        """Execute orchestrator-workers pattern. 执行编排器-工人模式"""
        try:
            # Step 1: Orchestrator decomposes / 步骤 1: 编排器分解
            logger.info("Orchestrator: analyzing input...")
            subtasks = await self._orchestrator(input_data)
            logger.info("Orchestrator: created %d subtasks", len(subtasks))

            # Step 2: Execute subtasks (parallel where possible) / 步骤 2: 执行子任务
            results = []
            errors = []
            for i, subtask in enumerate(subtasks):
                worker_name = subtask.get("worker", "")
                task_input = subtask.get("task", input_data)
                worker = self._workers.get(worker_name)

                if not worker:
                    errors.append(f"Worker '{worker_name}' not found for subtask {i}")
                    continue

                try:
                    logger.info("Worker '%s': executing subtask %d", worker_name, i + 1)
                    result = await worker(task_input)
                    results.append({"worker": worker_name, "result": result})
                except Exception as e:
                    errors.append(f"Worker '{worker_name}' subtask {i} failed: {e}")

            # Step 3: Synthesize results / 步骤 3: 综合结果
            if self._synthesizer and results:
                logger.info("Synthesizer: combining %d results", len(results))
                final_output = await self._synthesizer(results)
            else:
                final_output = results

            return WorkflowResult(
                success=len(errors) == 0,
                output=final_output,
                steps_completed=len(results),
                total_steps=len(subtasks),
                errors=errors,
                metadata={"subtasks": len(subtasks), "workers_used": len(set(s.get("worker") for s in subtasks))},
            )

        except Exception as e:
            return WorkflowResult(success=False, errors=[f"Orchestrator failed: {e}"])


# =============================================================================
# Pattern 5: Evaluator-Optimizer / 模式 5: 评估器-优化器
# =============================================================================


class EvaluatorOptimizer:
    """Iterative refinement — generate, evaluate, improve, repeat.
    迭代优化 — 生成、评估、改进、重复

    Use when / 适用场景:
    - Quality is critical / 质量至关重要
    - There are clear evaluation criteria / 有明确的评估标准
    - Output can be iteratively improved / 输出可以迭代改进
    - You know when output is "good enough" / 你知道什么时候输出"足够好"

    Architecture / 架构:
        Input → Generator → Output → Evaluator → (pass? → done : feedback → Generator)
    """

    def __init__(
        self,
        generator: Callable[[Any, str | None], Awaitable[Any]],
        evaluator: Callable[[Any], Awaitable[EvalResult]],
        max_iterations: int = 5,
        quality_threshold: float = 0.8,
    ) -> None:
        """
        Args:
            generator: Generates output. Takes (input, feedback_from_previous_iteration)
            evaluator: Evaluates output quality, returns EvalResult
            max_iterations: Maximum refinement iterations
            quality_threshold: Score threshold to stop iterating (0.0-1.0)
        """
        self._generator = generator
        self._evaluator = evaluator
        self._max_iterations = max_iterations
        self._threshold = quality_threshold

    async def execute(self, input_data: Any) -> WorkflowResult:
        """Execute evaluator-optimizer loop. 执行评估器-优化器循环"""
        current_output = None
        feedback: str | None = None
        iterations: list[dict] = []
        errors: list[str] = []

        for i in range(self._max_iterations):
            try:
                # Generate / 生成
                logger.info("EvaluatorOptimizer: iteration %d/%d", i + 1, self._max_iterations)
                current_output = await self._generator(input_data, feedback)

                # Evaluate / 评估
                eval_result = await self._evaluator(current_output)
                iterations.append({
                    "iteration": i + 1,
                    "score": eval_result.score,
                    "passed": eval_result.passed,
                    "feedback": eval_result.feedback,
                })

                logger.info(
                    "EvaluatorOptimizer: score=%.2f, passed=%s",
                    eval_result.score,
                    eval_result.passed,
                )

                # Check if good enough / 检查是否足够好
                if eval_result.passed or eval_result.score >= self._threshold:
                    return WorkflowResult(
                        success=True,
                        output=current_output,
                        steps_completed=i + 1,
                        total_steps=self._max_iterations,
                        metadata={
                            "iterations": iterations,
                            "final_score": eval_result.score,
                        },
                    )

                # Prepare feedback for next iteration / 为下次迭代准备反馈
                feedback = eval_result.feedback

            except Exception as e:
                errors.append(f"Iteration {i + 1} failed: {e}")

        # Max iterations reached / 达到最大迭代次数
        return WorkflowResult(
            success=False,
            output=current_output,
            steps_completed=len(iterations),
            total_steps=self._max_iterations,
            errors=errors + [f"Max iterations ({self._max_iterations}) reached without passing"],
            metadata={"iterations": iterations},
        )


@dataclass
class EvalResult:
    """Result of an evaluation. 评估结果"""

    score: float  # 0.0 to 1.0
    passed: bool = False
    feedback: str = ""
    details: dict[str, Any] = field(default_factory=dict)


# =============================================================================
# Unified Workflow Engine / 统一工作流引擎
# =============================================================================


class DynamicWorkflowEngine:
    """Combines all 5 patterns into a unified workflow engine.
    将 5 种模式组合为统一的工作流引擎

    Usage / 用法:
        engine = DynamicWorkflowEngine()

        # Simple chain / 简单链
        result = await engine.chain(
            [translate, summarize, format],
            initial_input="Hello world",
        )

        # Parallel fan-out / 并行扇出
        result = await engine.parallel(
            [search_arxiv, search_web, search_patents],
            input_data="AI agents",
            mode="all",
        )

        # Orchestrator-workers with Claude / 用 Claude 的编排器-工人
        result = await engine.orchestrate(
            orchestrator=claude_decomposer,
            workers={"research": researcher, "code": coder},
            input_data="Build a web scraper",
        )
    """

    async def chain(self, steps: list[SkillHandler], initial_input: Any, **kwargs: Any) -> WorkflowResult:
        """Execute a prompt chain. 执行提示链"""
        return await PromptChain(steps, **kwargs).execute(initial_input)

    async def route(self, input_data: Any, routes: dict[str, SkillHandler],
                    classifier: Callable[[Any], Awaitable[str]]) -> WorkflowResult:
        """Execute intelligent routing. 执行智能路由"""
        router = IntelligentRouter()
        for name, handler in routes.items():
            router.add_route(name, handler)
        router.set_classifier(classifier)
        return await router.execute(input_data)

    async def parallel(self, tasks: list[SkillHandler], input_data: Any,
                       mode: str = "all", **kwargs: Any) -> WorkflowResult:
        """Execute parallel fan-out. 执行并行扇出"""
        return await ParallelFanOut(tasks, mode=mode, **kwargs).execute(input_data)

    async def orchestrate(self, orchestrator: Callable, workers: dict[str, SkillHandler],
                          input_data: Any, **kwargs: Any) -> WorkflowResult:
        """Execute orchestrator-workers pattern. 执行编排器-工人模式"""
        return await OrchestratorWorkers(orchestrator, workers, **kwargs).execute(input_data)

    async def optimize(self, generator: Callable, evaluator: Callable,
                       input_data: Any, **kwargs: Any) -> WorkflowResult:
        """Execute evaluator-optimizer loop. 执行评估器-优化器循环"""
        return await EvaluatorOptimizer(generator, evaluator, **kwargs).execute(input_data)
