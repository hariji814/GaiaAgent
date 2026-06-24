"""Tests for AURC Dynamic Workflow Orchestrator."""

import asyncio

import pytest

from gaiaagent.workflows.orchestrator import (
    DynamicWorkflowEngine,
    EvaluatorOptimizer,
    EvalResult,
    IntelligentRouter,
    OrchestratorWorkers,
    ParallelFanOut,
    PromptChain,
    WorkflowResult,
)


class TestPromptChain:
    """Tests for sequential prompt chaining."""

    @pytest.mark.asyncio
    async def test_simple_chain(self):
        async def step_a(x):
            return x + " → A"

        async def step_b(x):
            return x + " → B"

        chain = PromptChain([step_a, step_b], step_names=["a", "b"])
        result = await chain.execute("start")

        assert result.success is True
        assert result.output == "start → A → B"
        assert result.steps_completed == 2

    @pytest.mark.asyncio
    async def test_chain_with_failure(self):
        async def step_a(x):
            return x + " → A"

        async def step_fail(x):
            raise ValueError("step B failed")

        chain = PromptChain([step_a, step_fail])
        result = await chain.execute("start")

        assert result.success is False
        assert result.steps_completed == 1
        assert len(result.errors) == 1

    @pytest.mark.asyncio
    async def test_empty_chain(self):
        chain = PromptChain([])
        result = await chain.execute("input")
        assert result.success is True
        assert result.output == "input"


class TestIntelligentRouter:
    """Tests for intelligent routing."""

    @pytest.mark.asyncio
    async def test_route_to_correct_handler(self):
        router = IntelligentRouter()

        async def handle_research(x):
            return {"type": "research", "data": x}

        async def handle_code(x):
            return {"type": "code", "data": x}

        router.add_route("research", handle_research)
        router.add_route("code", handle_code)

        async def classifier(x):
            return "research" if "paper" in x else "code"

        router.set_classifier(classifier)

        result = await router.execute("find papers on AI")
        assert result.success is True
        assert result.output["type"] == "research"
        assert result.metadata["route"] == "research"

    @pytest.mark.asyncio
    async def test_unknown_route(self):
        router = IntelligentRouter()
        router.add_route("a", lambda x: x)

        async def classifier(x):
            return "unknown"

        router.set_classifier(classifier)
        result = await router.execute("input")
        assert result.success is False


class TestParallelFanOut:
    """Tests for parallel fan-out execution."""

    @pytest.mark.asyncio
    async def test_parallel_all(self):
        async def task_a(x):
            return f"a:{x}"

        async def task_b(x):
            return f"b:{x}"

        fan = ParallelFanOut([task_a, task_b], mode="all")
        result = await fan.execute("test")

        assert result.success is True
        assert len(result.output) == 2
        assert "a:test" in result.output
        assert "b:test" in result.output

    @pytest.mark.asyncio
    async def test_parallel_with_failure(self):
        async def task_ok(x):
            return "ok"

        async def task_fail(x):
            raise RuntimeError("boom")

        fan = ParallelFanOut([task_ok, task_fail], mode="all")
        result = await fan.execute("test")

        assert result.success is False
        assert len(result.output) == 1  # One succeeded
        assert len(result.errors) == 1

    @pytest.mark.asyncio
    async def test_parallel_first(self):
        async def slow_task(x):
            await asyncio.sleep(1)
            return "slow"

        async def fast_task(x):
            return "fast"

        fan = ParallelFanOut([slow_task, fast_task], mode="first")
        result = await fan.execute("test")

        assert result.success is True
        assert result.output == "fast"

    @pytest.mark.asyncio
    async def test_parallel_vote(self):
        async def task_a(x):
            return "answer_1"

        async def task_b(x):
            return "answer_1"

        async def task_c(x):
            return "answer_2"

        fan = ParallelFanOut([task_a, task_b, task_c], mode="vote")
        result = await fan.execute("test")

        assert result.success is True
        assert result.output == "answer_1"
        assert result.metadata["votes"]["answer_1"] == 2


class TestOrchestratorWorkers:
    """Tests for dynamic orchestrator-workers pattern."""

    @pytest.mark.asyncio
    async def test_orchestrate_and_execute(self):
        async def orchestrator(input_data):
            return [
                {"worker": "researcher", "task": f"research {input_data}"},
                {"worker": "summarizer", "task": f"summarize {input_data}"},
            ]

        async def researcher(task):
            return {"findings": f"found info about {task}"}

        async def summarizer(task):
            return {"summary": f"summary of {task}"}

        ow = OrchestratorWorkers(
            orchestrator=orchestrator,
            workers={"researcher": researcher, "summarizer": summarizer},
        )
        result = await ow.execute("AI agents")

        assert result.success is True
        assert result.steps_completed == 2
        assert len(result.output) == 2

    @pytest.mark.asyncio
    async def test_orchestrate_with_synthesizer(self):
        async def orchestrator(input_data):
            return [
                {"worker": "a", "task": "part1"},
                {"worker": "b", "task": "part2"},
            ]

        async def worker_a(task):
            return f"result_{task}"

        async def worker_b(task):
            return f"result_{task}"

        async def synthesizer(results):
            combined = [r["result"] for r in results]
            return {"combined": " | ".join(combined)}

        ow = OrchestratorWorkers(
            orchestrator=orchestrator,
            workers={"a": worker_a, "b": worker_b},
            synthesizer=synthesizer,
        )
        result = await ow.execute("input")

        assert result.success is True
        assert "combined" in result.output

    @pytest.mark.asyncio
    async def test_missing_worker(self):
        async def orchestrator(input_data):
            return [{"worker": "nonexistent", "task": "do something"}]

        ow = OrchestratorWorkers(
            orchestrator=orchestrator,
            workers={"other_worker": lambda x: x},
        )
        result = await ow.execute("input")

        assert result.success is False
        assert len(result.errors) == 1


class TestEvaluatorOptimizer:
    """Tests for evaluator-optimizer iterative refinement."""

    @pytest.mark.asyncio
    async def test_passes_on_first_try(self):
        call_count = 0

        async def generator(input_data, feedback):
            nonlocal call_count
            call_count += 1
            return {"quality": "high", "content": "great answer"}

        async def evaluator(output):
            return EvalResult(score=0.95, passed=True, feedback="Excellent!")

        eo = EvaluatorOptimizer(generator, evaluator, max_iterations=3)
        result = await eo.execute("question")

        assert result.success is True
        assert call_count == 1  # Only one iteration needed
        assert result.metadata["final_score"] == 0.95

    @pytest.mark.asyncio
    async def test_improves_over_iterations(self):
        iteration = 0

        async def generator(input_data, feedback):
            nonlocal iteration
            iteration += 1
            return {"iteration": iteration, "quality": iteration * 0.3}

        async def evaluator(output):
            score = output["quality"]
            return EvalResult(
                score=score,
                passed=score >= 0.8,
                feedback=f"Score {score:.1f}, needs improvement" if score < 0.8 else "Good!",
            )

        eo = EvaluatorOptimizer(generator, evaluator, max_iterations=5, quality_threshold=0.8)
        result = await eo.execute("question")

        assert result.success is True
        assert result.steps_completed == 3  # 0.3, 0.6, 0.9 → passes at 3
        assert result.metadata["final_score"] >= 0.8

    @pytest.mark.asyncio
    async def test_max_iterations_reached(self):
        async def generator(input_data, feedback):
            return {"quality": 0.3}

        async def evaluator(output):
            return EvalResult(score=0.3, passed=False, feedback="Not good enough")

        eo = EvaluatorOptimizer(generator, evaluator, max_iterations=3)
        result = await eo.execute("question")

        assert result.success is False
        assert result.steps_completed == 3


class TestDynamicWorkflowEngine:
    """Tests for the unified workflow engine."""

    @pytest.mark.asyncio
    async def test_chain(self):
        engine = DynamicWorkflowEngine()

        async def double(x):
            return x * 2

        async def add_one(x):
            return x + 1

        result = await engine.chain([double, add_one], initial_input=5)
        assert result.success is True
        assert result.output == 11  # (5*2) + 1

    @pytest.mark.asyncio
    async def test_parallel(self):
        engine = DynamicWorkflowEngine()

        async def square(x):
            return x ** 2

        async def cube(x):
            return x ** 3

        result = await engine.parallel([square, cube], input_data=3)
        assert result.success is True
        assert set(result.output) == {9, 27}
