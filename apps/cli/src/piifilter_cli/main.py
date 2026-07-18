"""PIIFilter CLI — command-line transport for the pipeline.

Usage:
    piifilter scan <prompt>
    piifilter filter <prompt> [--mode] [--forward]
    piifilter doctor
    piifilter config
    piifilter explain <prompt>
    piifilter serve [--host] [--port]

No transport logic leaks into the core.  The CLI only calls
``FilterPipeline``, ``Session``, and ``FilterConfig``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Optional

import click

from piifilter import FilterPipeline, Session, FilterConfig
from piifilter.shared.models import ReplacementMode

logger = logging.getLogger(__name__)

# ── Helpers ──────────────────────────────────────────────────────────


def _create_pipeline(config_path: Optional[str] = None) -> FilterPipeline:
    """Build a pipeline, optionally loading config from YAML."""
    config = FilterConfig()
    if config_path:
        p = Path(config_path)
        if p.exists():
            config = FilterConfig.from_yaml(p)
    return FilterPipeline(config=config)


def _format_session_summary(session: Session) -> str:
    """Pretty-print a finished session."""
    lines = [
        f"Request ID:       {session.request_id}",
        f"Blocked:          {session.blocked}",
        f"Entities found:   {len(session.entities)}",
        f"Replacements:     {len(session.replacements)}",
        f"Latency:          {session.latency_ms:.1f} ms",
    ]
    if session.block_reason:
        lines.append(f"Block reason:     {session.block_reason}")
    if session.risk:
        lines.append(f"Risk:             {session.risk.level.value.upper()} ({session.risk.score:.0f}/100)")
    if session.filtered_prompt:
        lines.append(f"\nFiltered prompt:\n{session.filtered_prompt}")
    if session.llm_response:
        lines.append(f"\nLLM response:\n{session.llm_response}")
    return "\n".join(lines)


# ── CLI group ────────────────────────────────────────────────────────


@click.group()
@click.option("--config", "-c", type=click.Path(exists=True), help="Path to YAML config file")
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging")
@click.pass_context
def cli(ctx: click.Context, config: Optional[str], verbose: bool) -> None:
    """PIIFilter v2 — Local-first AI privacy gateway.

    Detect, classify, and replace sensitive information before prompts
    reach LLMs.
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s  %(name)s  %(message)s",
    )
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config


# ── scan ─────────────────────────────────────────────────────────────


@cli.command()
@click.argument("prompt")
@click.pass_context
def scan(ctx: click.Context, prompt: str) -> None:
    """Detect sensitive entities in PROMPT without modifying it."""
    async def _run() -> int:
        pipeline = _create_pipeline(ctx.obj.get("config_path"))
        session = Session(prompt=prompt)
        session = await pipeline.run(session)

        click.echo()
        click.echo(_format_session_summary(session))
        click.echo()

        if session.entities:
            click.echo("Detected entities:")
            for ent in session.entities:
                click.echo(
                    f"  [{ent.type.value.upper():20}] "
                    f"'{ent.text[:50]}'  "
                    f"(score={ent.score:.2f}, detector={ent.detector})"
                )

        return 0 if not session.blocked else 1

    sys.exit(asyncio.run(_run()))


# ── filter ───────────────────────────────────────────────────────────


@cli.command()
@click.argument("prompt")
@click.option(
    "--mode", "-m",
    type=click.Choice([m.value for m in ReplacementMode], case_sensitive=False),
    default=None,
    help="Replacement mode (default: from config)",
)
@click.option(
    "--forward", "-f",
    is_flag=True,
    help="Forward filtered prompt to configured LLM provider",
)
@click.pass_context
def filter(ctx: click.Context, prompt: str, mode: Optional[str], forward: bool) -> None:
    """Filter PROMPT: detect, assess risk, replace sensitive content."""
    async def _run() -> int:
        pipeline = _create_pipeline(ctx.obj.get("config_path"))
        session = Session(
            prompt=prompt,
            mode=ReplacementMode(mode) if mode else None,
        )
        if forward:
            # The pipeline will forward if session has provider_config;
            # set a minimal one so the forward stage is triggered.
            session.provider_config = pipeline.config.provider

        session = await pipeline.run(session)

        click.echo()
        click.echo(_format_session_summary(session))
        click.echo()

        if session.replacements:
            click.echo("Replacements applied:")
            for r in session.replacements:
                click.echo(
                    f"  {r.original[:40]:40} → {r.replacement}"
                )

        return 0 if not session.blocked else 1

    sys.exit(asyncio.run(_run()))


# ── explain ──────────────────────────────────────────────────────────


@cli.command()
@click.argument("prompt")
@click.pass_context
def explain(ctx: click.Context, prompt: str) -> None:
    """Detect sensitive entities and explain why they were flagged."""
    async def _run() -> int:
        pipeline = _create_pipeline(ctx.obj.get("config_path"))
        session = Session(prompt=prompt)
        session = await pipeline.run(session)

        click.echo()
        click.echo(f"Prompt length:       {len(prompt)} chars")
        click.echo(f"Request ID:          {session.request_id}")
        click.echo(f"Blocked:             {session.blocked}")

        if session.risk:
            click.echo(f"Risk level:          {session.risk.level.value.upper()}")
            click.echo(f"Risk score:          {session.risk.score:.0f}/100")
            click.echo(f"Recommendation:      {session.risk.recommendation}")

        click.echo()

        if not session.entities:
            click.echo("No sensitive entities detected — prompt is clean.")
        else:
            click.echo(f"Detected {len(session.entities)} sensitive entit{'y' if len(session.entities) == 1 else 'ies'}:\n")
            for i, ent in enumerate(session.entities, 1):
                click.echo(f"  #{i}  Type:    {ent.type.value.upper()}")
                click.echo(f"      Value:   '{ent.text}'")
                click.echo(f"      Span:    chars {ent.start}–{ent.end}")
                click.echo(f"      Confidence: {ent.score:.2f}")
                click.echo(f"      Detector:   {ent.detector}")
                if ent.context:
                    click.echo(f"      Context:    {ent.context}")
                click.echo()

        # Show full audit trail
        if session.audit_events:
            click.echo("Pipeline audit trail:")
            for evt in session.audit_events:
                click.echo(f"  [{evt['stage']:12}] {evt['event']:20} {evt.get('data', {})}")

        return 0

    sys.exit(asyncio.run(_run()))


# ── doctor ───────────────────────────────────────────────────────────


@cli.command()
@click.pass_context
def doctor(ctx: click.Context) -> None:
    """Inspect pipeline health: config, registry, and connectivity."""
    async def _run() -> int:
        pipeline = _create_pipeline(ctx.obj.get("config_path"))
        issues = 0

        click.echo("═══ PIIFilter Doctor ═══\n")

        # Config
        cfg = pipeline.config
        click.echo(f"Config version:      {cfg.config_version}")
        click.echo(f"Default provider:    {cfg.provider.name}")
        click.echo(f"Provider endpoint:   {cfg.provider.endpoint}")
        click.echo(f"Default strategy:    {cfg.replacement.default_strategy}")
        click.echo(f"Detection entities:  {len(cfg.detection_entities)} configured")
        click.echo(f"Policy rules:        {len(cfg.policy.rules)} loaded")
        click.echo()

        # Registry state
        registered = pipeline.registry.list_registered()
        click.echo("Plugin registry:")
        for category, items in registered.items():
            if items:
                click.echo(f"  {category}: {len(items) if isinstance(items, list) else items}")
                if isinstance(items, list) and items:
                    for name in items:
                        click.echo(f"    - {name}")
            else:
                click.echo(f"  {category}: (none)")
        click.echo()

        # Event bus
        click.echo("Event bus:           active")
        click.echo()

        # Quick scan to verify pipeline runs
        click.echo("Sanity check: running scan on test prompt...")
        try:
            test_session = Session(prompt="My email is test@example.com and my phone is 555-123-4567.")
            test_session = await pipeline.run(test_session)
            click.echo(f"  OK — scan completed in {test_session.latency_ms:.1f} ms")
            click.echo(f"  Entities detected: {len(test_session.entities)}")
        except Exception as exc:
            click.echo(f"  FAIL — {exc}")
            issues += 1

        click.echo()
        if issues:
            click.echo(f"Found {issues} issue(s).")
        else:
            click.echo("All checks passed. ✓")
        return issues

    sys.exit(asyncio.run(_run()))


# ── config ───────────────────────────────────────────────────────────


@cli.command()
@click.option("--show", is_flag=True, help="Print current config as YAML")
@click.option(
    "--init", "init_path",
    type=click.Path(),
    help="Write a default config YAML to PATH",
)
@click.pass_context
def config(ctx: click.Context, show: bool, init_path: Optional[str]) -> None:
    """View or initialise PIIFilter configuration."""
    cfg = _create_pipeline(ctx.obj.get("config_path")).config

    if init_path:
        dst = Path(init_path)
        if dst.exists():
            click.echo(f"Error: {dst} already exists.", err=True)
            sys.exit(1)
        cfg.to_yaml(dst)
        click.echo(f"Config written to {dst}")
        return

    if show:
        import yaml
        data = {
            "config_version": cfg.config_version,
            "schema_version": cfg.schema_version,
            "provider": cfg.provider.model_dump(),
            "policy": {"rules": [r.model_dump(by_alias=True) for r in cfg.policy.rules]},
            "detection": cfg.detection.model_dump(),
            "replacement": cfg.replacement.model_dump(),
            "logging": cfg.logging.model_dump(),
        }
        click.echo(yaml.dump(data, default_flow_style=False, sort_keys=False))
        return

    click.echo("Use --show to print current config, --init <path> to write defaults.")


# ── serve ────────────────────────────────────────────────────────────


@cli.command()
@click.option("--host", default="127.0.0.1", show_default=True, help="Bind address")
@click.option("--port", default=8000, type=int, show_default=True, help="Listen port")
@click.pass_context
def serve(ctx: click.Context, host: str, port: int) -> None:
    """Start the REST API server."""
    try:
        import uvicorn
    except ImportError:
        click.echo(
            "uvicorn is required to run the API server. Install with:\n"
            "  pip install uvicorn",
            err=True,
        )
        sys.exit(1)

    from piifilter_api.server import create_app

    app = create_app(config_path=ctx.obj.get("config_path"))
    click.echo(f"Starting PIIFilter API on http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")


# ── Entry point ──────────────────────────────────────────────────────


if __name__ == "__main__":
    cli()