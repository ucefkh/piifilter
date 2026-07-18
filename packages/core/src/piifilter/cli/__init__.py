"""PIIFilter CLI — command-line interface using Click."""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown

from piifilter import __version__, FilterPipeline
from piifilter.config import FilterConfig
from piifilter.shared.models import FilterRequest, ReplacementMode, RiskLevel

console = Console()
CONFIG_PATH = Path("config.yaml")


@click.group()
@click.version_option(version=__version__)
def cli_group():
    """PIIFilter — Local-first AI privacy gateway."""
    pass


@cli_group.command()
@click.option("--host", "-h", default="127.0.0.1", help="Host to bind to")
@click.option("--port", "-p", default=8000, help="Port to bind to")
@click.option("--config", "-c", default=None, help="Path to config.yaml")
@click.option("--reload", is_flag=True, help="Enable auto-reload for development")
def serve(host, port, config, reload):
    """Start the PIIFilter REST API server."""
    from piifilter.api.server import create_app

    cfg = FilterConfig.from_yaml(config or CONFIG_PATH) if config else FilterConfig()
    app = create_app(cfg)

    click.echo(f"🚀 PIIFilter v{__version__} serving at http://{host}:{port}")
    click.echo(f"   Detection: ✅ | Replacement: ✅ | Risk: ✅ | Gateway: {'✅' if cfg.provider.endpoint else '⚠️ not configured'}")
    click.echo(f"   Mode: {cfg.replacement.mode} | Threshold: {cfg.risk.threshold}")

    import uvicorn
    uvicorn.run(app, host=host, port=port, reload=reload)


@cli_group.command()
@click.argument("prompt", required=False)
@click.option("--file", "-f", type=click.Path(exists=True), help="Read prompt from file")
@click.option("--mode", "-m", type=click.Choice(["mask", "semantic", "generalize"]), default=None, help="Replacement mode")
@click.option("--config", "-c", default=None, help="Path to config.yaml")
@click.option("--json", "-j", "json_output", is_flag=True, help="Output as JSON")
def scan(prompt, file, mode, config, json_output):
    """Scan a prompt for PII."""
    if file:
        prompt = Path(file).read_text()
    if not prompt:
        click.echo("Error: Provide a prompt argument or --file", err=True)
        sys.exit(1)

    cfg = FilterConfig.from_yaml(config or CONFIG_PATH) if config else FilterConfig()
    pipeline = FilterPipeline(cfg)

    async def run():
        req = FilterRequest(prompt=prompt, mode=ReplacementMode(mode) if mode else None)
        result = await pipeline.scan(req)
        return result

    result = asyncio.run(run())

    if json_output:
        console.print(json.dumps(result.model_dump(), indent=2))
    else:
        table = Table(title=f"🔍 PII Scan — {result.count} entities detected")
        table.add_column("Type", style="cyan")
        table.add_column("Text", style="yellow")
        table.add_column("Score", style="green")
        table.add_column("Source", style="blue")

        for e in result.entities:
            table.add_row(e.type.value, e.text, f"{e.score:.2f}", e.source_detector)

        console.print(table)

        risk = result.risk
        panel = Panel(
            f"[bold]Risk Score:[/] {risk.score:.0f}/100  [bold]Level:[/] [{_risk_color(risk.level)}]{risk.level.value}[/]\n"
            f"[bold]Recommendation:[/] {risk.recommendation}",
            title="⚡ Risk Assessment",
        )
        console.print(panel)


@cli_group.command()
@click.argument("prompt", required=False)
@click.option("--file", "-f", type=click.Path(exists=True), help="Read prompt from file")
@click.option("--mode", "-m", type=click.Choice(["mask", "semantic", "generalize"]), default=None, help="Replacement mode")
@click.option("--config", "-c", default=None, help="Path to config.yaml")
@click.option("--json", "-j", "json_output", is_flag=True, help="Output as JSON")
@click.option("--forward", is_flag=True, help="Forward filtered prompt to LLM")
def filter(prompt, file, mode, config, json_output, forward):
    """Filter PII from a prompt."""
    if file:
        prompt = Path(file).read_text()
    if not prompt:
        click.echo("Error: Provide a prompt argument or --file", err=True)
        sys.exit(1)

    cfg = FilterConfig.from_yaml(config or CONFIG_PATH) if config else FilterConfig()
    pipeline = FilterPipeline(cfg)

    async def run():
        req = FilterRequest(prompt=prompt, mode=ReplacementMode(mode) if mode else None)
        filtered = await pipeline.filter(req)
        llm_response = None
        if forward:
            llm_response = await pipeline.gateway.forward(filtered.filtered)
        return filtered, llm_response

    result, llm_response = asyncio.run(run())

    if json_output:
        data = result.model_dump()
        if forward and llm_response:
            data["llm_response"] = llm_response
        console.print(json.dumps(data, indent=2))
    else:
        console.print(Panel(result.filtered, title="✅ Filtered Prompt"))
        console.print(f"\n[dim]Risk: {result.risk.score:.0f}/100 ({result.risk.level.value}) | "
                      f"Entities: {len(result.entities)} | "
                      f"Latency: {result.latency_ms:.1f}ms[/]")

        if result.replacements:
            table = Table(title="Replacements")
            table.add_column("Original", style="red")
            table.add_column("Replacement", style="green")
            table.add_column("Type", style="cyan")
            table.add_column("Mode", style="blue")
            for r in result.replacements:
                table.add_row(r.original, r.replacement, r.entity_type.value, r.mode.value)
            console.print(table)

        if forward and llm_response:
            console.print(f"\n[bold]LLM Response:[/]\n{llm_response}")


@cli_group.command()
@click.option("--config", "-c", default=None, help="Path to config.yaml")
def doctor(config):
    """Check if PIIFilter is properly configured."""
    cfg_path = Path(config) if config else CONFIG_PATH
    cfg = FilterConfig.from_yaml(config or CONFIG_PATH) if config else FilterConfig()

    checks = []

    if cfg_path.exists():
        checks.append(("Config File", "✅", f"{cfg_path}"))
    else:
        checks.append(("Config File", "⚠️", "Not found — using defaults"))

    checks.append(("Detection", "✅", f"{len(cfg.detection_entities)} entity types loaded"))
    checks.append(("Replacement", "✅", f"Mode: {cfg.replacement.mode}"))
    checks.append(("Risk Engine", "✅", f"Threshold: {cfg.risk.threshold}"))

    from piifilter.gateway.proxy import LLMGateway
    pipeline = FilterPipeline(cfg)

    async def check_gateway():
        return await pipeline.gateway.check_health()

    try:
        healthy = asyncio.run(check_gateway())
        if healthy:
            checks.append(("Gateway", "✅", f"{cfg.provider.name} at {cfg.provider.endpoint}"))
        else:
            checks.append(("Gateway", "⚠️", f"{cfg.provider.name} at {cfg.provider.endpoint} — unreachable"))
    except Exception:
        checks.append(("Gateway", "❌", f"{cfg.provider.name} — connection failed"))

    table = Table(title=f"🔍 PIIFilter v{__version__} — System Check")
    table.add_column("Component", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Details", style="white")

    for comp, status, detail in checks:
        table.add_row(comp, status, detail)

    console.print(table)


@cli_group.command()
@click.option("--config", "-c", default=None, help="Path to config.yaml")
def config(config):
    """View or edit PIIFilter configuration."""
    cfg_path = Path(config) if config else CONFIG_PATH
    if cfg_path.exists():
        cfg = FilterConfig.from_yaml(config or CONFIG_PATH)
        console.print(f"[bold]Config loaded from:[/] {cfg_path}")
        console.print(f"  Replacement Mode: {cfg.replacement.mode}")
        console.print(f"  Risk Threshold: {cfg.risk.threshold}")
        console.print(f"  Store Logs: {cfg.logging.store_logs}")
        console.print(f"  Seed: {cfg.replacement.seed}")
        console.print(f"  Provider: {cfg.provider.name} ({cfg.provider.endpoint})")
        console.print(f"  Model: {cfg.provider.default_model}")
    else:
        console.print(f"[yellow]No config found at {cfg_path}[/]")
        console.print("Create one with default values? [y/N]", end=" ")
        if input().lower().startswith("y"):
            cfg = FilterConfig()
            cfg.to_yaml(cfg_path)
            console.print(f"[green]Config created at {cfg_path}[/]")


@cli_group.command()
@click.option("--iterations", "-n", default=100, help="Number of iterations")
@click.option("--prompt", "-p", default="Hi, I'm Susan from Acme Corp. My email is susan@acme.com and my phone is +1 555-123-4567.", help="Test prompt")
@click.option("--config", "-c", default=None, help="Path to config.yaml")
def benchmark(iterations, prompt, config):
    """Benchmark PIIFilter performance."""
    cfg = FilterConfig.from_yaml(config or CONFIG_PATH) if config else FilterConfig()
    pipeline = FilterPipeline(cfg)

    async def run():
        req = FilterRequest(prompt=prompt)
        times = []
        for i in range(iterations):
            start = time.perf_counter()
            await pipeline.filter(req)
            elapsed = (time.perf_counter() - start) * 1000
            times.append(elapsed)

        avg = sum(times) / len(times)
        max_t = max(times)
        min_t = min(times)
        p99 = sorted(times)[int(len(times) * 0.99)]

        return avg, min_t, max_t, p99, len(times)

    console.print(f"[bold]Running {iterations} iterations...[/]")
    avg, min_t, max_t, p99, count = asyncio.run(run())

    table = Table(title=f"⚡ PIIFilter Benchmark ({count} iterations)")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Average", f"{avg:.2f}ms")
    table.add_row("Min", f"{min_t:.2f}ms")
    table.add_row("Max", f"{max_t:.2f}ms")
    table.add_row("P99", f"{p99:.2f}ms")

    if avg < 20:
        status = "🚀 Excellent"
    elif avg < 50:
        status = "✅ Target met"
    else:
        status = "⚠️ Needs optimization"

    console.print(table)
    console.print(f"\n[bold]Status:[/] {status}")


def _risk_color(level: RiskLevel) -> str:
    return {"LOW": "green", "MEDIUM": "yellow", "HIGH": "orange1", "CRITICAL": "red"}.get(level.value, "white")


if __name__ == "__main__":
    cli_group()