from __future__ import annotations

from ze_personal.accountability.types import ActivitySummary


def build_narrative(summary: ActivitySummary) -> str:
    """Return a plain-text Ze accountability narrative for the given summary."""
    period_label = "last 24 hours" if summary.period_days == 1 else f"last {summary.period_days} days"
    lines: list[str] = [f"Ze activity report ({period_label})", ""]

    # Cost section
    if summary.agent_costs:
        lines.append(f"💸 Cost: ${summary.total_cost_usd:.4f} across {sum(a.run_count for a in summary.agent_costs)} runs")
        for ac in summary.agent_costs:
            lines.append(f"   • {ac.agent}: {ac.run_count} runs, ${ac.cost_usd:.4f}")
    else:
        lines.append("💸 Cost: No activity recorded yet.")

    # Goals section
    lines.append("")
    lines.append("🎯 Goals")
    if summary.goals_advanced:
        for title in summary.goals_advanced:
            lines.append(f"   • Advanced: \"{title}\"")
    if summary.goals_stalled:
        for title in summary.goals_stalled:
            lines.append(f"   • Stalled: \"{title}\"")
    if not summary.goals_advanced and not summary.goals_stalled:
        lines.append("   • No goal changes this period.")

    # Workflow failures
    lines.append("")
    if summary.workflow_failures:
        lines.append("⚙️  Workflows")
        for name in summary.workflow_failures:
            lines.append(f"   • Failed: {name}")
    else:
        lines.append("⚙️  Workflows: no failures")

    # Anomalies
    if summary.anomalies:
        lines.append("")
        lines.append("⚠️  Anomalies")
        for desc in summary.anomalies:
            lines.append(f"   • {desc}")

    return "\n".join(lines)
