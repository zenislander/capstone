"""
Rich terminal dashboard for the Bureau LLM Token Monitor.

Renders three sections from aggregator and gap analysis output:
  1. Usage Monitor    — spend vs. contract, % consumed, threshold flags
  2. Gap Analysis     — Claude-generated per-bureau risk assessment with color badges
  3. Intake Pipeline  — active requests, stage, renewal linkage
"""

import json
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.rule import Rule
from rich.padding import Padding
from rich import box

ROOT = Path(__file__).parent.parent
OUTPUT_DIR = ROOT / "output"

console = Console(force_terminal=True, highlight=False)

STATUS_STYLES = {
    "action_required": ("red",       "[!!] ACTION REQUIRED"),
    "monitor":         ("yellow",    "[!]  MONITOR"),
    "on_track":        ("green",     "[OK] ON TRACK"),
    "data_gap":        ("dim white", "[?]  DATA GAP"),
}

THRESHOLD_STYLE = {
    True:  ("bold red",   "[!] YES"),
    False: ("green",      "no"),
    None:  ("dim white",  "N/A"),
}

QUALITY_STYLE = {
    "success":    ("green",     "SUCCESS"),
    "incomplete": ("yellow",    "INCOMPLETE"),
    "failed":     ("bold red",  "FAILED"),
}


def _pct_style(pct_consumed) -> Text:
    if pct_consumed is None:
        return Text("N/A", style="dim white")
    pct = pct_consumed * 100
    label = f"{pct:.0f}%"
    if pct >= 80:
        return Text(f"[!] {label}", style="bold red")
    elif pct >= 75:
        return Text(f"[!] {label}", style="yellow")
    return Text(label, style="green")


def render_header(generated_at: str, overall_quality: str, error_count: int) -> None:
    quality_color = "green" if overall_quality == "success" else "yellow" if overall_quality == "incomplete" else "red"
    title = Text()
    title.append("Treasury TCloud  ·  LLM Token Monitor\n", style="bold white")
    title.append(f"{generated_at}  ·  ", style="dim white")
    title.append(overall_quality.upper(), style=f"bold {quality_color}")
    title.append(f"  ·  {error_count} error(s)", style="dim white")
    console.print(Panel(title, box=box.DOUBLE_EDGE, border_style="blue", padding=(0, 2)))


def render_data_source_warnings(failed_sources: list[str]) -> None:
    if not failed_sources:
        return
    SOURCE_LABELS = {
        "gcp": "GCP Cloud Logging  /  Vertex AI",
        "aws": "AWS Bedrock  /  Cost Explorer",
    }
    warning = Text()
    warning.append("[!!] DATA SOURCE FAILURE DETECTED\n", style="bold red")
    for src in failed_sources:
        label = SOURCE_LABELS.get(src, src.upper())
        warning.append(f"  {label} is UNAVAILABLE\n", style="red")
    warning.append(
        "  Spend figures are UNDERSTATED — threshold calculations are unreliable.\n",
        style="yellow",
    )
    warning.append(
        "  Gap analysis results below reflect partial data only. Human review required.",
        style="yellow",
    )
    console.print(Padding(
        Panel(warning, border_style="red", box=box.HEAVY, padding=(0, 1)),
        (0, 2)
    ))
    console.print()


def render_usage_monitor(rows: list[dict]) -> None:
    console.print(Rule("[bold cyan]Usage Monitor[/bold cyan]", style="cyan"))
    table = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold cyan",
                  border_style="dim", padding=(0, 1))
    table.add_column("Bureau",      style="bold white", min_width=10)
    table.add_column("Contract ID", style="dim white",  min_width=10)
    table.add_column("Contract $",  justify="right",    min_width=11)
    table.add_column("Spent",       justify="right",    min_width=11)
    table.add_column("Consumed",    justify="center",   min_width=9)
    table.add_column("Threshold",   justify="center",   min_width=10)
    table.add_column("Quality",     min_width=14)

    for row in rows:
        contract = f"${row['contract_value_usd']:,}" if row["contract_value_usd"] else "N/A"
        spent    = f"${row['total_spend_usd']:,.2f}" if row["total_spend_usd"] else "N/A"
        pct_text = _pct_style(row.get("pct_consumed"))

        tf = row.get("threshold_flag")
        t_style, t_label = THRESHOLD_STYLE.get(tf, ("dim white", "N/A"))
        threshold_text = Text(t_label, style=t_style)

        q = row.get("data_quality", "")
        q_style, q_label = QUALITY_STYLE.get(q, ("dim white", q.upper()))
        quality_text = Text(q_label, style=q_style)

        table.add_row(
            row["bureau"],
            row.get("request_id") or "—",
            contract, spent,
            pct_text, threshold_text, quality_text,
        )

    console.print(Padding(table, (0, 2)))


def render_gap_analysis(rows: list[dict], model: str) -> None:
    console.print(Rule(f"[bold magenta]Gap Analysis[/bold magenta]  [dim](via {model})[/dim]", style="magenta"))

    for row in rows:
        status = row.get("status", "data_gap")
        color, badge = STATUS_STYLES.get(status, ("dim white", status.upper()))

        header = Text()
        header.append(f"{badge}", style=f"bold {color}")
        header.append(f"  ·  {row['bureau']}", style="bold white")
        header.append(f"  ·  {row['request_id']}", style="white")
        pct = row.get("spend_pct")
        if pct is not None:
            pct_style = "bold red" if pct >= 80 else "yellow" if pct >= 75 else "green"
            header.append(f"  ·  ", style="dim white")
            header.append(f"{pct}% consumed", style=pct_style)

        renewal_id    = row.get("renewal_request_id")
        renewal_stage = row.get("renewal_stage")
        if renewal_id:
            header.append(f"  ·  renewal ", style="dim white")
            header.append(renewal_id, style="cyan")
            if renewal_stage:
                header.append(f" @ {renewal_stage}", style="dim cyan")

        body = Text(f"\n{row.get('message', '')}", style="white")

        content = Text()
        content.append_text(header)
        content.append_text(body)

        console.print(Padding(
            Panel(content, border_style=color, box=box.ROUNDED, padding=(0, 1)),
            (0, 2, 0, 2)
        ))


def render_intake_pipeline(rows: list[dict]) -> None:
    console.print(Rule("[bold cyan]Intake Pipeline[/bold cyan]", style="cyan"))
    table = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold cyan",
                  border_style="dim", padding=(0, 1))
    table.add_column("Bureau",  style="bold white", min_width=10)
    table.add_column("Request", style="cyan",       min_width=10)
    table.add_column("Stage",   min_width=30)
    table.add_column("Type",    min_width=18)

    for row in rows:
        req   = row.get("request_id") or "—"
        stage = row["stage"]
        renews = row.get("renews_for")

        if stage == "No request found":
            stage_text = Text(stage, style="dim white")
            type_text  = Text("—", style="dim white")
        else:
            stage_color = "green" if stage in ("Executive approval", "Customer estimate approval") else "white"
            stage_text  = Text(stage, style=stage_color)
            if renews:
                type_text = Text(f"renews {renews}", style="cyan")
            else:
                type_text = Text("new request", style="dim white")

        table.add_row(row["bureau"], req, stage_text, type_text)

    console.print(Padding(table, (0, 2)))


def render(aggregator_output: dict, gap_analysis: list[dict] | None, model: str) -> None:
    console.print()
    render_header(
        generated_at=aggregator_output.get("generated_at", "—"),
        overall_quality=aggregator_output.get("overall_data_quality", "—"),
        error_count=len(aggregator_output.get("errors", [])),
    )
    console.print()
    render_data_source_warnings(aggregator_output.get("failed_data_sources", []))
    render_usage_monitor(aggregator_output.get("usage_monitor", []))
    console.print()

    render_intake_pipeline(aggregator_output.get("intake_pipeline", []))
    console.print()

    if gap_analysis:
        render_gap_analysis(gap_analysis, model)
        console.print()


if __name__ == "__main__":
    agg_path = OUTPUT_DIR / "aggregator_output.json"
    gap_path = OUTPUT_DIR / "gap_analysis.json"

    if not agg_path.exists():
        print("aggregator_output.json not found. Run `python main.py run` first.")
        sys.exit(1)

    with open(agg_path) as f:
        agg = json.load(f)
    gap = json.load(open(gap_path)) if gap_path.exists() else None

    render(agg, gap, MODEL if gap else "—")
