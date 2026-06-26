"""AURC CLI — Command-line tools for common AURC operations.
AURC 命令行工具 — 常用 AURC 操作的 CLI

Provides subcommands for:
- Starting an HTTP server with optional health dashboard (serve)
- Printing version and protocol info (version, info)
- Validating Agent Descriptor JSON files (validate)
- Testing protocol bridge translations (bridge test)
- Exporting the local registry to JSON (registry export)

Usage / 用法:
    aurc serve --host 0.0.0.0 --port 8080 --dashboard
    aurc version
    aurc info
    aurc validate descriptor.json
    aurc bridge test --protocol mcp
    aurc registry export
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from gaiaagent import __version__

# =============================================================================
# Status indicators / 状态指示符
# =============================================================================


def _supports_unicode() -> bool:
    """Check if stdout supports Unicode characters. 检查标准输出是否支持 Unicode"""
    try:
        encoding = getattr(sys.stdout, "encoding", None) or ""
        if encoding.lower() in ("utf-8", "utf8"):
            return True
        # Try encoding a test character to detect capability / 尝试编码测试字符
        "✓".encode(encoding)
        return True
    except (UnicodeEncodeError, LookupError):
        return False


_UNICODE = _supports_unicode()
_OK = "✓" if _UNICODE else "[OK]"
_FAIL = "✗" if _UNICODE else "[FAIL]"
_ARROW = "→" if _UNICODE else "->"


def _print(message: str, quiet: bool = False) -> None:
    """Print a message unless quiet mode is active. 安静模式下不输出"""
    if not quiet:
        print(message)


def _error(message: str) -> None:
    """Print an error message to stderr."""
    print(f"{_FAIL} {message}", file=sys.stderr)


# =============================================================================
# Command: serve / 启动服务器
# =============================================================================


def _load_agent_module(path: str) -> Any:
    """Import a user agent module and return its first @aurc_agent instance."""
    import importlib.util

    file_path = Path(path)
    if not file_path.exists():
        _error(f"Agent module not found: {file_path}")
        raise SystemExit(1)

    spec = importlib.util.spec_from_file_location("_aurc_user_agent", file_path)
    if spec is None or spec.loader is None:
        _error(f"Cannot load agent module: {file_path}")
        raise SystemExit(1)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    for _name in dir(mod):
        obj = getattr(mod, _name)
        if isinstance(obj, type) and hasattr(obj, "_aurc_descriptor"):
            return obj()
    _error(f"No @aurc_agent class found in {file_path}")
    raise SystemExit(1)


def _make_echo_agent() -> Any:
    """A minimal built-in agent so 'gaiaagent serve' works out of the box."""
    from gaiaagent.sdk.decorators import aurc_agent, skill

    @aurc_agent(
        id="aurc:builtin/echo:v1.0",
        display_name="Echo",
        description="Built-in echo agent for zero-config serve",
        protocols=["mcp/2025-06-18"],
    )
    class _Echo:
        @skill("echo", description="Echo back any text")
        async def echo(self, text: str) -> dict[str, Any]:
            return {"echo": text}

        @skill("ping", description="Health probe")
        async def ping(self) -> dict[str, Any]:
            return {"pong": True}

    return _Echo()


def _cmd_serve(args: argparse.Namespace) -> int:
    """Start the AURC HTTP server.
    启动 AURC HTTP 服务器

    POST /aurc routes to real @skill methods on registered agents. A built-in
    echo agent is registered by default; pass --agent to load your own.
    可选启用健康仪表盘端点
    """
    from gaiaagent.security.audit import AuditLog
    from gaiaagent.server import AURCServer
    from gaiaagent.transport.http import HTTPTransportServer

    # One shared audit log: the hot-path authz guard writes decisions
    # here, and the dashboard (if enabled) reads the same instance, so
    # /metrics and the audit table reflect real authorization events.
    aurc = AURCServer(audit_log=AuditLog())

    # Register the user-supplied agent if given, else a built-in echo agent.
    agents_loaded: list[str] = []
    user_agent = _load_agent_module(args.agent) if args.agent else None
    if user_agent is not None:
        asyncio.run(aurc.register_agent(user_agent))
        agents_loaded.append(user_agent.aurc_descriptor.aurc_id)
    else:
        asyncio.run(aurc.register_agent(_make_echo_agent()))
        agents_loaded.append("aurc:builtin/echo:v1.0")

    http = HTTPTransportServer(host=args.host, port=args.port)
    http.set_handler(aurc.http_handler)

    if args.dashboard:
        from gaiaagent.observability.dashboard import DashboardAPI, HealthDashboard

        dashboard = HealthDashboard(
            aurc.harness, aurc.audit_log or AuditLog(), aurc.router
        )
        http.set_dashboard_api(DashboardAPI(dashboard))

    quiet = args.quiet
    _print(f"{_OK} AURC server starting...", quiet)
    _print(f"  {_ARROW} Endpoint: http://{args.host}:{args.port}/aurc", quiet)
    _print(f"  {_ARROW} Health:   http://{args.host}:{args.port}/health", quiet)
    for aid in agents_loaded:
        _print(f"  {_ARROW} Agent:    {aid}", quiet)
    if args.dashboard:
        _print(f"  {_ARROW} Dashboard: http://{args.host}:{args.port}/dashboard", quiet)

    try:
        asyncio.run(http.start())
    except KeyboardInterrupt:
        _print(f"\n{_OK} Server stopped.  服务器已停止", quiet)
    except Exception as exc:
        _error(f"Server failed to start: {exc}")
        return 1

    return 0


# =============================================================================
# Command: version / 版本信息
# =============================================================================


def _cmd_version(args: argparse.Namespace) -> int:
    """Print version info. 打印版本信息"""
    quiet = args.quiet

    if quiet:
        print(__version__)
    else:
        print(f"AURC CLI v{__version__}")
        print(f"  {_ARROW} gaiaagent package version: {__version__}")
        print(f"  {_ARROW} Protocol: aurc/0.1")

    return 0


# =============================================================================
# Command: info / 协议信息
# =============================================================================


def _cmd_info(args: argparse.Namespace) -> int:
    """Print protocol and system info. 打印协议和系统信息

    Shows AURC version, supported bridges, and Python version.
    显示 AURC 版本、支持的桥接器和 Python 版本
    """
    from gaiaagent.bridges.a2a import A2ABridge
    from gaiaagent.bridges.base import BridgeRegistry, MCPBridge

    quiet = args.quiet

    # Collect supported bridges / 收集支持的桥接器
    registry = BridgeRegistry()
    registry.register(MCPBridge())
    registry.register(A2ABridge())
    protocols = registry.list_protocols()

    python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

    if quiet:
        info = {
            "aurc_version": __version__,
            "protocol": "aurc/0.1",
            "bridges": protocols,
            "python_version": python_version,
        }
        print(json.dumps(info, indent=2))
    else:
        print("AURC Protocol Info / AURC 协议信息")
        print(f"  {_ARROW} AURC version:    {__version__}")
        print(f"  {_ARROW} Protocol:        aurc/0.1")
        print(f"  {_ARROW} Python version:  {python_version}")
        print(f"  {_ARROW} Supported bridges / 支持的桥接器:")
        for proto in protocols:
            print(f"      {_OK} {proto}")

    return 0


# =============================================================================
# Command: validate / 验证描述文档
# =============================================================================


def _cmd_validate(args: argparse.Namespace) -> int:
    """Validate an Agent Descriptor JSON file.
    验证 Agent 描述文档 JSON 文件

    Checks that the file conforms to the AgentDescriptor schema.
    检查文件是否符合 AgentDescriptor 模式
    """
    from gaiaagent.core.identity import AgentDescriptor

    quiet = args.quiet
    file_path = Path(args.file)

    # Check file exists / 检查文件是否存在
    if not file_path.exists():
        _error(f"File not found: {file_path}  文件不存在")
        return 1

    if not file_path.suffix == ".json":
        _error(f"Expected .json file, got: {file_path.suffix}")
        return 1

    # Read and parse / 读取并解析
    try:
        raw = file_path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        _error(f"Invalid JSON: {exc}  JSON 格式错误")
        return 1
    except OSError as exc:
        _error(f"Cannot read file: {exc}")
        return 1

    # Validate against descriptor model / 根据描述文档模型验证
    try:
        descriptor = AgentDescriptor(**data)
    except Exception as exc:
        _print(f"{_FAIL} Validation failed / 验证失败", quiet)
        _print(f"  {_ARROW} {exc}", quiet)
        if quiet:
            print(json.dumps({"valid": False, "error": str(exc)}))
        return 1

    # Success output / 成功输出
    if quiet:
        print(json.dumps({"valid": True, "aurc_id": descriptor.aurc_id}))
    else:
        print(f"{_OK} Valid Agent Descriptor / 有效的 Agent 描述文档")
        print(f"  {_ARROW} AURC ID:      {descriptor.aurc_id}")
        print(f"  {_ARROW} Display name: {descriptor.display_name}")
        print(f"  {_ARROW} Version:      {descriptor.version}")
        skills = [s.name for s in descriptor.capabilities.provides]
        if skills:
            print(f"  {_ARROW} Skills:       {', '.join(skills)}")
        bridges = descriptor.protocols.bridges
        if bridges:
            print(f"  {_ARROW} Bridges:      {', '.join(bridges)}")

    return 0


# =============================================================================
# Command: bridge test / 桥接器测试
# =============================================================================


# Sample messages for each protocol / 各协议的示例消息
_SAMPLE_MCP_MESSAGE: dict[str, Any] = {
    "jsonrpc": "2.0",
    "id": "test-1",
    "method": "tools/call",
    "params": {
        "name": "web-search",
        "arguments": {"query": "AURC protocol"},
    },
}

_SAMPLE_A2A_MESSAGE: dict[str, Any] = {
    "jsonrpc": "2.0",
    "id": "test-2",
    "method": "tasks/send",
    "params": {
        "id": "task-001",
        "sessionId": "session-abc",
        "messages": [
            {
                "role": "user",
                "parts": [{"type": "text", "text": "Research the AURC protocol"}],
            }
        ],
    },
}

_SAMPLE_ACP_MESSAGE: dict[str, Any] = {
    "method": "invoke",
    "id": "acp-req-1",
    "params": {
        "agent_id": "acp-agent-01",
        "task": "Summarize the latest AI news",
        "input": {"topic": "AI agents"},
        "session_id": "session-acp-001",
    },
}


def _cmd_bridge_test(args: argparse.Namespace) -> int:
    """Test bridge translation with sample messages.
    使用示例消息测试桥接器翻译

    Supports MCP, A2A, and ACP protocols.
    支持 MCP、A2A 和 ACP 协议
    """
    from gaiaagent.bridges.a2a import A2ABridge
    from gaiaagent.bridges.acp import ACPBridge
    from gaiaagent.bridges.base import MCPBridge

    quiet = args.quiet
    protocol = args.protocol

    # Select bridge and sample message / 选择桥接器和示例消息
    if protocol == "mcp":
        bridge: MCPBridge | A2ABridge | ACPBridge = MCPBridge()
        sample = _SAMPLE_MCP_MESSAGE
    elif protocol == "a2a":
        bridge = A2ABridge()
        sample = _SAMPLE_A2A_MESSAGE
    elif protocol == "acp":
        bridge = ACPBridge()
        sample = _SAMPLE_ACP_MESSAGE
    else:
        _error(f"Unknown protocol: {protocol}. Use: mcp, a2a, or acp")
        return 1

    async def _run_test() -> int:
        source_proto = bridge.source_protocol

        _print(f"{_OK} Testing {source_proto} bridge / 测试 {source_proto} 桥接器", quiet)
        _print("", quiet)

        # Step 1: External → AURC / 步骤 1: 外部协议 → AURC
        _print(f"{_ARROW} Step 1: {source_proto} {_ARROW} AURC (translate_to_aurc)", quiet)
        _print(f"  Input ({source_proto}):", quiet)
        _print(f"    {json.dumps(sample, indent=4)}", quiet)

        try:
            aurc_msg = await bridge.translate_to_aurc(sample)
            _print(f"  {_OK} Translation successful / 翻译成功", quiet)
            _print("  Output (AURC):", quiet)
            aurc_dict = aurc_msg.model_dump(mode="json", exclude_none=True)
            _print(f"    {json.dumps(aurc_dict, indent=4, default=str)}", quiet)
        except Exception as exc:
            _print(f"  {_FAIL} Translation failed / 翻译失败: {exc}", quiet)
            return 1

        _print("", quiet)

        # Step 2: AURC → External / 步骤 2: AURC → 外部协议
        _print(f"{_ARROW} Step 2: AURC {_ARROW} {source_proto} (translate_from_aurc)", quiet)
        try:
            external_msg = await bridge.translate_from_aurc(aurc_msg)
            _print(f"  {_OK} Translation successful / 翻译成功", quiet)
            _print(f"  Output ({source_proto}):", quiet)
            _print(f"    {json.dumps(external_msg, indent=4, default=str)}", quiet)
        except Exception as exc:
            _print(f"  {_FAIL} Translation failed / 翻译失败: {exc}", quiet)
            return 1

        _print("", quiet)

        # Step 3: Capability mapping / 步骤 3: 能力映射
        _print(f"{_ARROW} Step 3: Capability mapping / 能力映射", quiet)
        try:
            if protocol == "mcp":
                sample_caps = [
                    {"name": "web-search", "description": "Search the web", "inputSchema": {}},
                ]
            else:
                sample_caps = [
                    {"id": "research", "name": "Research", "description": "Research topics"},
                ]
            mapped = await bridge.map_capabilities(sample_caps)
            _print(
                f"  {_OK} Mapped {len(mapped)} capabilities / 映射了 {len(mapped)} 项能力",
                quiet,
            )
            for skill in mapped:
                _print(
                    f"      {_OK} {skill.get('skill_id', '')}: {skill.get('name', '')}",
                    quiet,
                )
        except Exception as exc:
            _print(f"  {_FAIL} Capability mapping failed / 能力映射失败: {exc}", quiet)
            return 1

        _print("", quiet)
        _print(f"{_OK} All bridge tests passed / 所有桥接器测试通过", quiet)

        if quiet:
            print(json.dumps({
                "protocol": source_proto,
                "status": "passed",
                "steps": ["translate_to_aurc", "translate_from_aurc", "capability_mapping"],
            }))

        return 0

    return asyncio.run(_run_test())


# =============================================================================
# Command: registry export / 注册中心导出
# =============================================================================


def _cmd_registry_export(args: argparse.Namespace) -> int:
    """Export registry to JSON (prints to stdout).
    将注册中心导出为 JSON（输出到标准输出）

    Creates a temporary registry and exports its contents.
    创建临时注册中心并导出其内容
    """
    from gaiaagent.registry.local import LocalRegistry

    quiet = args.quiet
    registry = LocalRegistry()

    # In a real deployment, the registry would be populated by the server.
    # For CLI export, we output whatever is currently in the registry.
    # 在实际部署中，注册中心由服务器填充。
    # 对于 CLI 导出，我们输出注册中心当前的内容。

    data = registry.export_to_dict()

    if quiet:
        print(json.dumps(data, indent=2, default=str))
    else:
        count = len(data)
        if count == 0:
            _print(f"{_OK} Registry exported: 0 entries (empty registry)", quiet)
            _print(f"  {_ARROW} No agents are currently registered.", quiet)
            _print(f"  {_ARROW} Start a server and register agents to populate registry.", quiet)
        else:
            _print(f"{_OK} Registry exported: {count} entries / 导出 {count} 个条目", quiet)
        # Always print JSON to stdout for piping / 始终输出 JSON 以便管道使用
        print(json.dumps(data, indent=2, default=str))

    return 0


# =============================================================================
# Command: demo / 演示
# =============================================================================


def _cmd_demo(args: argparse.Namespace) -> int:
    """Run the AURC demo - 3 agents, cross-protocol chain, live dashboard.
    运行 AURC 演示 - 3 个 Agent，跨协议链，实时仪表盘
    """
    from gaiaagent.demo import run_demo

    quiet = args.quiet
    if not quiet:
        print("Starting AURC demo...")

    try:
        asyncio.run(run_demo(
            host=args.host,
            port=args.port,
            open_browser=not args.no_browser,
            api_key=args.api_key,
            provider=args.llm_provider,
            model=args.model,
        ))
    except KeyboardInterrupt:
        _print(f"\n{_OK} Demo stopped.  演示已停止", quiet)
    except Exception as exc:
        _error(f"Demo failed: {exc}")
        return 1

    return 0


# =============================================================================
# Argument parser construction / 参数解析器构建
# =============================================================================


_AGENT_TEMPLATE = '''"""__PROJECT__ - an AURC agent built with GaiaAgent."""

from __future__ import annotations

from typing import Any

from gaiaagent.sdk.decorators import aurc_agent, skill


@aurc_agent(
    id="aurc:__PROJECT__/myagent:v1.0",
    display_name="My Agent",
    description="A starter AURC agent - edit me!",
    protocols=["mcp/2025-06-18"],
    tags=["starter"],
)
class MyAgent:

    @skill("greet", description="Greet someone by name")
    async def greet(self, name: str) -> dict[str, Any]:
        return {"message": f"Hello, {name}! Welcome to AURC."}

    @skill("echo", description="Echo back any input")
    async def echo(self, text: str) -> dict[str, Any]:
        return {"echo": text}


if __name__ == "__main__":
    import asyncio

    from gaiaagent import RuntimeHarness

    async def main() -> None:
        harness = RuntimeHarness()
        agent = MyAgent()
        await harness.register(agent.aurc_descriptor)
        await harness.start(agent.aurc_descriptor.aurc_id)
        print(await agent.greet("World"))
        await harness.complete(agent.aurc_descriptor.aurc_id)

    asyncio.run(main())
'''

_README_TEMPLATE = '''# __PROJECT__

An AURC agent built with GaiaAgent.

## Quick Start

    pip install gaiaagent[http]
    python agent.py

## Run the full AURC demo

    gaiaagent demo

## Learn More

- AURC Protocol: https://github.com/gaiaagent/gaiaagent
- Getting Started: https://gaiaagent.dev/docs
'''


def _cmd_init(args: argparse.Namespace) -> int:
    """Scaffold a new AURC agent project with a working template."""
    project_dir = Path(args.name)

    if project_dir.exists():
        _error(f"Directory already exists: {project_dir}")
        return 1

    project_dir.mkdir()

    (project_dir / "agent.py").write_text(
        _AGENT_TEMPLATE.replace("__PROJECT__", args.name), encoding="utf-8"
    )
    (project_dir / "README.md").write_text(
        _README_TEMPLATE.replace("__PROJECT__", args.name), encoding="utf-8"
    )
    (project_dir / "requirements.txt").write_text(
        "gaiaagent[http]\n", encoding="utf-8"
    )

    _print(f"{_OK} Created AURC agent project: {args.name}")
    _print(f"  {_ARROW} {project_dir / 'agent.py'}")
    _print(f"  {_ARROW} {project_dir / 'README.md'}")
    _print(f"  {_ARROW} {project_dir / 'requirements.txt'}")
    _print("")
    _print("Next steps:")
    _print(f"  cd {args.name}")
    _print("  pip install -r requirements.txt")
    _print("  python agent.py        # run your agent")
    _print("  gaiaagent demo         # see the full AURC demo")

    return 0


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with all subcommands.
    构建包含所有子命令的参数解析器
    """
    # Shared parent parser with --quiet flag / 共享父级解析器，包含 --quiet 标志
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        default=False,
        help="Machine-readable output (JSON where applicable) / 机器可读输出",
    )

    parser = argparse.ArgumentParser(
        prog="aurc",
        description=(
            "AURC CLI — Agent Unified Runtime & Communication tools.\n"
            "AURC 命令行工具 — Agent 统一运行时与通信工具"
        ),
        parents=[parent],
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands / 可用命令")

    # --- serve ---
    p_serve = subparsers.add_parser(
        "serve",
        parents=[parent],
        help="Start the AURC HTTP server / 启动 AURC HTTP 服务器",
    )
    p_serve.add_argument(
        "--host",
        default="0.0.0.0",
        help="Bind host (default: 0.0.0.0) / 绑定主机",
    )
    p_serve.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Bind port (default: 8080) / 绑定端口",
    )
    p_serve.add_argument(
        "--dashboard",
        action="store_true",
        default=False,
        help="Enable health dashboard / 启用健康仪表盘",
    )

    p_serve.add_argument(
        "--agent",
        default=None,
        help="Python file with a @aurc_agent class to serve / 要加载的 Agent 模块",
    )

    # --- demo ---
    p_demo = subparsers.add_parser(
        "demo",
        parents=[parent],
        help="Run the AURC demo (3 agents, cross-protocol, no API key) / 运行 AURC 演示",
    )
    p_demo.add_argument(
        "--host",
        default="127.0.0.1",
        help="Dashboard host (default: 127.0.0.1) / 仪表盘主机",
    )
    p_demo.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Dashboard port (default: 8080) / 仪表盘端口",
    )
    p_demo.add_argument(
        "--api-key",
        default=None,
        help="LLM API key for real model calls (OpenAI/Anthropic). Omit for stub mode.",
    )
    p_demo.add_argument(
        "--llm-provider",
        default="openai",
        choices=["openai", "anthropic"],
        help="LLM provider when --api-key is set (default: openai)",
    )
    p_demo.add_argument(
        "--model",
        default="auto",
        help="Model name (default: auto -> gpt-4o-mini / claude-3-5-sonnet)",
    )
    p_demo.add_argument(
        "--no-browser",
        action="store_true",
        default=False,
        help="Do not auto-open the browser / 不自动打开浏览器",
    )

    # --- init ---
    p_init = subparsers.add_parser(
        "init",
        parents=[parent],
        help="Scaffold a new AURC agent project",
    )
    p_init.add_argument(
        "name",
        help="Project directory name",
    )

    # --- version ---
    subparsers.add_parser(
        "version",
        parents=[parent],
        help="Print version info / 打印版本信息",
    )

    # --- info ---
    subparsers.add_parser(
        "info",
        parents=[parent],
        help="Print protocol and system info / 打印协议和系统信息",
    )

    # --- validate ---
    p_validate = subparsers.add_parser(
        "validate",
        parents=[parent],
        help="Validate an Agent Descriptor JSON file / 验证 Agent 描述文档",
    )
    p_validate.add_argument(
        "file",
        help="Path to the Agent Descriptor JSON file / Agent 描述文档 JSON 文件路径",
    )

    # --- bridge ---
    p_bridge = subparsers.add_parser(
        "bridge",
        parents=[parent],
        help="Bridge operations / 桥接器操作",
    )
    bridge_sub = p_bridge.add_subparsers(
        dest="bridge_command",
        help="Bridge subcommands / 桥接器子命令",
    )

    p_bridge_test = bridge_sub.add_parser(
        "test",
        parents=[parent],
        help="Test bridge translation with sample messages / 使用示例消息测试桥接翻译",
    )
    p_bridge_test.add_argument(
        "--protocol",
        required=True,
        choices=["mcp", "a2a", "acp"],
        help="Protocol to test: mcp, a2a, or acp / 要测试的协议",
    )

    # --- registry ---
    p_registry = subparsers.add_parser(
        "registry",
        parents=[parent],
        help="Registry operations / 注册中心操作",
    )
    registry_sub = p_registry.add_subparsers(
        dest="registry_command",
        help="Registry subcommands / 注册中心子命令",
    )

    registry_sub.add_parser(
        "export",
        parents=[parent],
        help="Export registry to JSON (stdout) / 导出注册中心为 JSON",
    )

    return parser


# =============================================================================
# Entry point / 入口点
# =============================================================================


def main() -> None:
    """CLI entry point. CLI 入口点

    Dispatches to the appropriate command handler based on arguments.
    根据参数分派到相应的命令处理函数
    """
    parser = _build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    # Command dispatch / 命令分派
    handlers: dict[str, Any] = {
        "serve": _cmd_serve,
        "demo": _cmd_demo,
        "version": _cmd_version,
        "info": _cmd_info,
        "validate": _cmd_validate,
        "init": _cmd_init,
    }

    # Handle nested subcommands (bridge test, registry export) / 处理嵌套子命令
    if args.command == "bridge":
        if getattr(args, "bridge_command", None) == "test":
            sys.exit(_cmd_bridge_test(args))
        else:
            # No bridge subcommand given; print bridge help / 未提供桥接器子命令
            parser.parse_args(["bridge", "--help"])
            sys.exit(0)

    if args.command == "registry":
        if getattr(args, "registry_command", None) == "export":
            sys.exit(_cmd_registry_export(args))
        else:
            parser.parse_args(["registry", "--help"])
            sys.exit(0)

    handler = handlers.get(args.command)
    if handler:
        sys.exit(handler(args))
    else:
        _error(f"Unknown command: {args.command}")
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
