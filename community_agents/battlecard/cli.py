from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from community_agents.battlecard.runner import BattlecardRunner


def _ask(prompt: str, required: bool = False) -> str:
    while True:
        try:
            val = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[battlecard] Cancelled.")
            sys.exit(0)
        if val or not required:
            return val
        print("  (This field is required)")


def _ask_list(prompt: str) -> list[str]:
    raw = _ask(prompt)
    return [x.strip() for x in raw.split(",") if x.strip()]


def _print_banner() -> None:
    print()
    print("  +==================================================+")
    print("  |   Chakra47 -- Sales Battlecard Generator         |")
    print("  |   Public intelligence only. Code decides.        |")
    print("  +==================================================+")
    print()


def gather_user_context() -> dict[str, Any]:
    print("  ── Step 1: Tell us about YOUR business ──────────────")
    print()
    name = _ask("  Your company name          : ", required=True)
    what = _ask("  What you do (one line)     : ", required=True)
    icp  = _ask("  Your ideal customer (ICP)  : ")
    diffs = _ask_list("  Your top differentiators  : (comma-separated, e.g. 'transparent pricing, offline-first, SOC2')")
    print()
    return {"company_name": name, "what_you_do": what, "icp": icp, "differentiators": diffs}


def gather_competitor_url() -> str:
    print("  ── Step 2: Competitor to analyze ────────────────────")
    print()
    url = _ask("  Competitor URL             : ", required=True)
    print()
    return url


def _is_nd(value: Any) -> bool:
    return isinstance(value, dict) and "data" in value and value["data"] is None


def _val(v: Any) -> str | None:
    """Return string representation of a value, or None if ND/empty."""
    if v is None or _is_nd(v):
        return None
    if isinstance(v, list):
        return ", ".join(str(x) for x in v[:5]) if v else None
    s = str(v).strip()
    return s if s else None


def _field(label: str, value: Any, width: int = 20) -> None:
    s = _val(value)
    if s is None:
        return
    if len(s) > 120:
        s = s[:117] + "..."
    print(f"    {label:<{width}}: {s}")


def _sources(sources: Any) -> None:
    if isinstance(sources, list):
        filtered = [s for s in sources if s][:3]
        if filtered:
            print(f"    {'Sources':<20}  {' | '.join(filtered)}")


def _divider(title: str) -> None:
    pad = 50 - len(title)
    print(f"\n    ── {title} {'─' * max(pad, 2)}")


def print_battlecard(card: dict[str, Any]) -> None:
    print()
    print("  ======================================================")

    meta = card.get("meta", {})
    name = meta.get("company") or card.get("snapshot", {}).get("name", "Unknown")
    confidence = meta.get("confidence", "?")
    engine = meta.get("search_engine", "none")
    web_hits = meta.get("web_queries_answered", 0)

    print(f"  BATTLECARD: {name}")
    print(f"  Confidence: {confidence}  |  Web engine: {engine}  |  Queries answered: {web_hits}")
    print("  ======================================================")

    # ── Snapshot ──────────────────────────────────────────────
    snap = card.get("snapshot", {})
    _divider("Company Snapshot")
    _field("Tagline", snap.get("tagline"))
    _field("Founded", snap.get("founded"))
    _field("HQ", snap.get("hq"))
    _field("Revenue / Stage", snap.get("revenue_stage"))
    _field("Employees", snap.get("employee_count"))
    _field("Size Estimate", snap.get("size_estimate"))
    _field("Growth Signal", snap.get("growth_signal"))
    _sources(snap.get("sources"))

    # ── Product Intelligence ───────────────────────────────────
    prod = card.get("product_intel", {})
    _divider("Product Intelligence")
    _field("Core Offering", prod.get("core_offering"))
    _field("Key Features", prod.get("key_features"))
    _field("Tech Stack", prod.get("tech_stack"))
    _field("Marketing Tools", prod.get("marketing_tools"))
    _field("Marketing Strategy", prod.get("marketing_strategy"))
    _field("Pricing Model", prod.get("pricing_model"))
    _field("Pricing Detail", prod.get("pricing_detail"))
    _field("Free Tier", prod.get("free_tier"))
    _field("Contact Sales", prod.get("contact_sales"))
    _sources(prod.get("sources"))

    # ── Market Position ────────────────────────────────────────
    mkt = card.get("market_position", {})
    _divider("Market Position")
    _field("Positioning", mkt.get("positioning"))
    _field("Target Segments", mkt.get("target_segments"))
    _field("Known Clients", mkt.get("known_clients"))
    _field("Case Studies", mkt.get("case_study_count"))
    _field("Main Competitors", mkt.get("main_competitors"))
    _field("Leadership", mkt.get("leadership"))
    _sources(mkt.get("sources"))

    # ── Sentiment Map ──────────────────────────────────────────
    sent = card.get("sentiment_map", {})
    _divider("Sentiment Map")
    print(f"    {'Overall':<20}: {sent.get('overall', 'unknown')}")
    _field("Customer Praise", sent.get("customer_praise_web"))
    _field("Customer Complaints", sent.get("customer_complaints_web"))
    _field("Controversies", sent.get("recent_controversies"))

    reddit = sent.get("reddit", {})
    if isinstance(reddit, dict) and not _is_nd(reddit):
        print(f"\n    Reddit  ({reddit.get('mention_count', 0)} mentions, sentiment={reddit.get('sentiment', '?')})")
        if reddit.get("pain_points"):
            print(f"      Pain points     : {', '.join(reddit['pain_points'][:4])}")
        if reddit.get("switching_triggers"):
            print(f"      Switching       : {', '.join(reddit['switching_triggers'])}")
        if reddit.get("top_subreddits"):
            print(f"      Top subreddits  : r/{', r/'.join(reddit['top_subreddits'][:4])}")

    hn = sent.get("hackernews", {})
    if isinstance(hn, dict) and not _is_nd(hn):
        print(f"\n    HackerNews  ({hn.get('story_count', 0)} stories, sentiment={hn.get('sentiment', '?')})")
        if hn.get("key_themes"):
            print(f"      Themes          : {', '.join(hn['key_themes'][:4])}")

    reviews = sent.get("review_platforms", {})
    if isinstance(reviews, dict):
        visible = {k: v for k, v in reviews.items() if not _is_nd(v) and v}
        if visible:
            print(f"\n    Review Platforms:")
            for platform, data in visible.items():
                print(f"      {platform.upper():<12}: {data}")

    _sources(sent.get("sources"))

    # ── Hiring Signals ─────────────────────────────────────────
    hiring = card.get("hiring_signals", {})
    _divider("Hiring Signals")
    _field("Open Roles", hiring.get("open_roles"))
    _field("Departments", hiring.get("departments"))
    _field("Tech Signals", hiring.get("tech_signals"))

    # ── Social ─────────────────────────────────────────────────
    social = card.get("social")
    if social and not _is_nd(social):
        _divider("Social Presence")
        if isinstance(social, list):
            for link in social[:6]:
                print(f"    • {link}")
        else:
            print(f"    {social}")

    # ── Strategic Analysis (LLM) ───────────────────────────────
    strategy = card.get("strategic_analysis")
    if (
        strategy
        and not _is_nd(strategy)
        and isinstance(strategy, dict)
        and not strategy.get("note")
    ):
        _divider("Strategic Analysis  [LLM]")
        for key, val in strategy.items():
            label = key.replace("_", " ").title()
            if isinstance(val, list):
                print(f"\n    {label}:")
                for item in val:
                    if isinstance(item, dict):
                        angle = item.get("angle") or item.get("action") or str(item)
                        print(f"      * {angle}")
                        if item.get("evidence"):
                            print(f"        Evidence : {item['evidence'][:120]}")
                        if item.get("how_to_use"):
                            print(f"        Use in   : {item['how_to_use'][:120]}")
                    else:
                        print(f"      * {item}")
            elif val:
                print(f"\n    {label}: {val}")
    elif strategy and isinstance(strategy, dict) and strategy.get("note"):
        _divider("Strategic Analysis  [LLM]")
        print(f"    {strategy['note']}")

    # ── Our Angle vs Them ──────────────────────────────────────
    angles = card.get("our_angle", [])
    if angles:
        _divider("Our Angle vs Them")
        for a in angles:
            if isinstance(a, dict):
                print(f"\n      [{a.get('angle', 'Angle')}]")
                if a.get("evidence"):
                    print(f"      Evidence  : {a['evidence'][:120]}")
                if a.get("talk_track"):
                    print(f"      Talk Track: {a['talk_track'][:160]}")
            else:
                print(f"      • {a}")

    print()


def save_battlecard(card: dict[str, Any], url: str) -> None:
    slug = url.replace("https://", "").replace("http://", "").replace("/", "_").replace(".", "_")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = Path(f"battlecard_{slug}_{ts}.json")
    out.write_text(json.dumps(card, indent=2, default=str))
    print(f"  [saved] {out.resolve()}")


def main() -> None:
    _print_banner()
    user_ctx = gather_user_context()
    url = gather_competitor_url()

    runner = BattlecardRunner()
    card = runner.run(user_ctx, url)

    if "error" in card:
        print(f"\n  [error] {card['error']}")
        sys.exit(1)

    print_battlecard(card)
    save_battlecard(card, url)


if __name__ == "__main__":
    main()
