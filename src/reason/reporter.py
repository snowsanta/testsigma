import json
import os
import time
from typing import List, Dict, Any
from src.reason.blast_radius import BlastRadiusResult
import src.llm.client


def generate_report(result: BlastRadiusResult) -> tuple[str, dict]:
    if not result.ui_elements_at_risk and not result.affected_requirements:
        structured = {
            "direct_ui": [], "direct_reqs": [], "downstream_ui": [],
            "downstream_reqs": [], "low_confidence_count": 0,
            "total_edges": 0, "confidence_pct": 100, "severity": "Low",
        }
        return (
            "## Risk Summary\n\n"
            "**No user-facing flows or specification requirements are affected by this change.**\n\n"
            "The changed files do not map to any known UI elements or requirements in the knowledge graph.",
            structured,
        )

    structured = _build_structured_summary(result)
    narrative = _generate_narrative(structured)
    return _combine_report(structured, narrative), structured


def save_report(
    report_text: str,
    output_dir: str = "reports",
    repo: str = "",
    pr_number: int = 0,
    target_url: str = "",
) -> str:
    os.makedirs(output_dir, exist_ok=True)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    filename = f"report-{timestamp}.md"
    filepath = os.path.join(output_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"# Risk Assessment Report\n\n")
        f.write(f"**Generated:** {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        if target_url:
            f.write(f"**Target:** {target_url}\n")
        if repo:
            f.write(f"**PR:** {repo}#{pr_number}\n")
        f.write(f"\n---\n\n")
        f.write(report_text)

    return filepath


def save_report_json(
    structured: dict,
    output_dir: str = "reports",
    repo: str = "",
    pr_number: int = 0,
    target_url: str = "",
) -> str:
    os.makedirs(output_dir, exist_ok=True)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    filename = f"report-{timestamp}.json"
    filepath = os.path.join(output_dir, filename)

    payload = {
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "target_url": target_url or None,
        "repo": repo or None,
        "pr_number": pr_number or None,
        "severity": structured.get("severity"),
        "confidence_pct": structured.get("confidence_pct"),
        "low_confidence_count": structured.get("low_confidence_count"),
        "directly_affected": structured.get("direct_reqs", []),
        "directly_affected_ui": structured.get("direct_ui", []),
        "downstream_cascade": structured.get("downstream_reqs", []),
        "downstream_cascade_ui": structured.get("downstream_ui", []),
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    return filepath


def _build_structured_summary(result: BlastRadiusResult) -> dict:
    direct_ui = _normalize_items(result.ui_elements_at_risk)
    direct_reqs = _normalize_items(result.affected_requirements)
    downstream_ui = _normalize_items(result.downstream_ui_elements)
    downstream_reqs = _normalize_items(result.downstream_requirements)

    low_confidence_count = sum(
        1 for i in direct_ui + direct_reqs
        if float(i.get("confidence", 1.0)) < 0.7
    )
    total_edges = len(direct_ui) + len(direct_reqs)
    confidence_pct = 0.0
    if total_edges > 0:
        confidence_pct = round((total_edges - low_confidence_count) / total_edges * 100)

    severity = _classify_severity(direct_ui, direct_reqs, downstream_ui, downstream_reqs)

    return {
        "direct_ui": direct_ui,
        "direct_reqs": direct_reqs,
        "downstream_ui": downstream_ui,
        "downstream_reqs": downstream_reqs,
        "low_confidence_count": low_confidence_count,
        "total_edges": total_edges,
        "confidence_pct": confidence_pct,
        "severity": severity,
    }


def _normalize_items(items: list) -> List[Dict[str, Any]]:
    result = []
    for item in items:
        if item is None:
            continue
        entry = {}
        for key in ("id", "selector", "label", "title", "url", "source_section"):
            val = item.get(key, "") if isinstance(item, dict) else getattr(item, key, "")
            if val:
                entry[key] = val
        conf = item.get("confidence", 1.0) if isinstance(item, dict) else getattr(item, "confidence", 1.0)
        entry["confidence"] = float(conf) if conf is not None else 1.0
        if entry:
            result.append(entry)
    return result


def _classify_severity(direct_ui, direct_reqs, downstream_ui, downstream_reqs) -> str:
    if len(direct_reqs) >= 3 or len(direct_ui) >= 3:
        return "Critical"
    if len(direct_reqs) >= 1 or len(direct_ui) >= 1:
        return "High"
    if len(downstream_ui) >= 1 or len(downstream_reqs) >= 1:
        return "Medium"
    return "Low"


def _generate_narrative(structured: dict) -> str:
    direct_ui = structured["direct_ui"]
    direct_reqs = structured["direct_reqs"]
    downstream_ui = structured["downstream_ui"]
    downstream_reqs = structured["downstream_reqs"]

    summary_lines = [
        f"Directly affected: {len(direct_ui)} UI elements, {len(direct_reqs)} requirements.",
    ]
    if downstream_ui or downstream_reqs:
        summary_lines.append(
            f"Downstream cascade: {len(downstream_ui)} UI elements, "
            f"{len(downstream_reqs)} requirements."
        )
    if structured["low_confidence_count"] > 0:
        summary_lines.append(
            f"Low-confidence edges: {structured['low_confidence_count']} of "
            f"{structured['total_edges']} ({100 - structured['confidence_pct']}%) — "
            f"manual review recommended."
        )
    summary_text = " ".join(summary_lines)

    system_prompt = (
        "You are a senior QA risk analyst. Write a plain-English executive summary "
        "and actionable test case recommendations for a QA Lead."
    )

    user_prompt = (
        "Based on the blast radius data below, generate:\n\n"
        "1. **Executive Summary** — 2-3 sentences describing the impact and risk level.\n"
        "2. **Recommended Test Cases** — A numbered list of 3-6 specific, manual/automated "
        "test scenarios the QA team should run. Be specific about what to test and why.\n\n"
        "---\n"
        f"Severity: {structured['severity']}\n"
        f"{summary_text}\n"
        f"Confidence: {structured['confidence_pct']}%\n\n"
        f"Directly affected requirements: {direct_reqs}\n\n"
        f"Downstream requirements at risk: {downstream_reqs}\n"
    )

    return src.llm.client.complete(system=system_prompt, user=user_prompt)


def _combine_report(structured: dict, narrative: str) -> str:
    lines = []

    lines.append("## 1. Impact Summary\n")
    lines.append(f"**Severity:** {structured['severity']}\n")
    lines.append(f"**Confidence Coverage:** {structured['confidence_pct']}% of edges are high-confidence\n")
    if structured["low_confidence_count"] > 0:
        pct_low = 100 - structured["confidence_pct"]
        lines.append(
            f"**⚠ {structured['low_confidence_count']} edges ({pct_low}%) are low-confidence** "
            f"— manual review recommended.\n"
        )
    lines.append("")

    if structured["direct_ui"] or structured["direct_reqs"]:
        lines.append("## 2. Directly Affected\n")
        lines.append("| Feature | UI Element | Confidence |")
        lines.append("|---------|-----------|------------|")
        for ui in structured["direct_ui"]:
            label = ui.get("label") or ui.get("id") or ui.get("selector", "?")
            lines.append(
                f"| {label} | `{ui.get('selector', ui.get('id', '?'))}` "
                f"| {_fmt_conf(ui.get('confidence', 1.0))} |"
            )
        for req in structured["direct_reqs"]:
            title = req.get("title") or req.get("id", "?")
            lines.append(
                f"| {title} | — | {_fmt_conf(req.get('confidence', 1.0))} |"
            )
        lines.append("")

    if structured["downstream_ui"] or structured["downstream_reqs"]:
        lines.append("## 3. Downstream Cascade\n")
        lines.append("These features may be indirectly affected via UI transitions:\n")
        lines.append("| Feature | UI Element | Confidence |")
        lines.append("|---------|-----------|------------|")
        for ui in structured["downstream_ui"]:
            label = ui.get("label") or ui.get("id") or ui.get("selector", "?")
            lines.append(
                f"| {label} | `{ui.get('selector', ui.get('id', '?'))}` "
                f"| {_fmt_conf(ui.get('confidence', 1.0))} |"
            )
        for req in structured["downstream_reqs"]:
            title = req.get("title") or req.get("id", "?")
            lines.append(
                f"| {title} | — | {_fmt_conf(req.get('confidence', 1.0))} |"
            )
        lines.append("")

    lines.append("## 4. Narrative Assessment\n")
    lines.append(narrative.strip())
    lines.append("")

    return "\n".join(lines)


def _fmt_conf(val: float) -> str:
    pct = round(float(val) * 100)
    if pct >= 80:
        return f"🟢 {pct}%"
    if pct >= 60:
        return f"🟡 {pct}%"
    return f"🔴 {pct}%"
