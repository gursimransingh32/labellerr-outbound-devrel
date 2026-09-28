#!/usr/bin/env python3
"""Labellerr outbound helper.

Pipeline (each step can also run on its own):
  1. refresh  - pull Labellerr's public customer pages and cache their text
  2. check    - flag any target that is (or might be) an existing Labellerr customer
  3. score    - rank targets by fit + timing with a transparent, weighted score
  4. draft    - generate first-draft openers per contact from each data row

Standard library only (Python 3.8+). No API keys, no third-party packages.

Usage:
  python3 src/outbound.py all [--offline] [--as-of YYYY-MM-DD]
  python3 src/outbound.py check
"""

import argparse
import csv
import datetime as dt
import difflib
import html
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CACHE = DATA / "cache"
OUT = ROOT / "output"

# Public pages that disclose Labellerr customers. The snapshot in
# data/dnc_snapshot.csv was built from these; a live refresh catches new ones.
LABELLERR_PAGES = {
    "case-studies": "https://www.labellerr.com/case-studies",
    "robotics-data": "https://www.labellerr.com/robotics-data",
}

# Words that appear in many company names and should never, alone, trigger a
# "possible subsidiary" match (e.g. "Deep Sentinel" vs "DeepX Robotics").
GENERIC_TOKENS = {
    "ai", "the", "and", "inc", "llc", "ltd", "gmbh", "corp", "co", "group", "labs", "lab",
    "robotics", "robot", "robots", "technologies", "technology", "tech", "systems",
    "solutions", "health", "university", "institute", "research", "deep", "data",
    "global", "international", "motors", "automation", "intelligence", "cars",
    "trucks", "truck", "bus", "buses", "public", "office", "record", "analytical",
    "engineering", "industries", "material", "handling",
}
LEGAL_SUFFIXES = {"inc", "llc", "ltd", "gmbh", "corp", "co", "plc", "pvt", "pte", "limited",
                  "ab", "ag", "sa", "sas", "bv", "nv", "oy", "kg", "srl", "spa"}

# ---------------------------------------------------------------------------
# Scoring weights (max total = 100). Kept in one place so they are easy to argue with.
# ---------------------------------------------------------------------------
SIGNAL_WEIGHTS = {"data_infra": 16, "funding": 13, "launch": 10, "m&a": 8, "hiring": 7}
NEED_WEIGHTS = {"egocentric": 16, "teleop": 15, "manipulation": 13, "world_model": 13,
                "vision": 7, "navigation": 4}
SIZE_WEIGHTS = {"startup": 15, "scaleup": 12, "public": 6, "mega": 4}  # "winnability"
PROOF_POINT = 10
WARM_PATH = 5
INDIA_LINK = 5
TIERS = [(75, "A"), (60, "B"), (0, "C")]

MAX_WORDS = 150
DNC_STATS = {"customers": 0, "brands": 0}


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def normalize(name):
    """Lower-case, strip punctuation and legal suffixes: 'Coupang, Inc.' -> 'coupang'."""
    s = name.lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    tokens = [t for t in s.split() if t not in LEGAL_SUFFIXES]
    return " ".join(tokens)


def core_tokens(name):
    """Distinctive words in a company name, used to catch parent/subsidiary overlaps."""
    return {t for t in normalize(name).split() if len(t) >= 4 and t not in GENERIC_TOKENS}


def parse_date(value):
    """Accept YYYY-MM-DD or YYYY-MM (treated as the 1st of the month)."""
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%Y-%m"):
        try:
            return dt.datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unrecognised date '{value}' (use YYYY-MM-DD or YYYY-MM)")


def split_list(value):
    return [v.strip() for v in value.split(";") if v.strip()]


def word_count(text):
    return len(re.findall(r"[A-Za-z0-9$%'.,+-]+", text))


# ---------------------------------------------------------------------------
# 1. Refresh: fetch Labellerr's public pages
# ---------------------------------------------------------------------------
def html_to_text(raw):
    raw = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", html.unescape(raw)).strip()


def fetch(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (outbound-dnc-check)"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def refresh(offline=False):
    """Return {page_key: text}. Falls back to cached copies when offline or blocked."""
    CACHE.mkdir(parents=True, exist_ok=True)
    texts, log = {}, []
    for key, url in LABELLERR_PAGES.items():
        cache_file = CACHE / f"{key}.txt"
        if not offline:
            try:
                raw = fetch(url)
                text = html_to_text(raw)
                slugs = sorted(set(re.findall(r"/case-study/([a-z0-9-]+)", raw)))
                cache_file.write_text(text, encoding="utf-8")
                (CACHE / f"{key}.slugs.json").write_text(json.dumps(slugs, indent=1), encoding="utf-8")
                texts[key] = text
                log.append(f"  live   {url}  ({len(text):,} chars, {len(slugs)} case-study links)")
                continue
            except (urllib.error.URLError, OSError, ValueError) as exc:
                log.append(f"  failed {url}  ({exc.__class__.__name__}); trying cache")
        if cache_file.exists():
            texts[key] = cache_file.read_text(encoding="utf-8")
            log.append(f"  cache  {cache_file.relative_to(ROOT)}")
        else:
            texts[key] = ""
            log.append(f"  none   {key}: no live page and no cache; relying on snapshot only")
    return texts, log


# ---------------------------------------------------------------------------
# 2. Check: is this target already a (publicly disclosed) Labellerr customer?
# ---------------------------------------------------------------------------
def check_company(name, dnc_rows, page_texts):
    """Return (status, reasons). status is BLOCK, REVIEW or CLEAR.

    dnc_rows with level "block" are publicly disclosed customers/partners: an exact or
    near-exact name match blocks, and a shared distinctive word (e.g. "toyota") flags
    a possible subsidiary for review. Rows with level "review" are brands owned by a
    customer (e.g. Zenseact, owned by Volvo Cars): a name match holds them for review.
    """
    target = normalize(name)
    status, reasons = "CLEAR", []
    for row in dnc_rows:
        level = row.get("level", "block") or "block"
        names = ([row["name"]] if level == "block" else []) + \
                [a for a in row.get("aliases", "").split("|") if a]
        for alias in names:
            a = normalize(alias)
            if not a:
                continue
            ratio = difflib.SequenceMatcher(None, target, a).ratio()
            if target == a or ratio >= 0.88:
                if level == "block":
                    return "BLOCK", [f"matches '{row['name']}' ({row['source_type']}), similarity {ratio:.2f}"]
                status = "REVIEW"
                reasons.append(f"'{alias}': {row['source_type']}; hold unless the team clears it")
                continue
            if level == "block":
                shared = core_tokens(name) & core_tokens(alias)
                if shared:
                    status = "REVIEW"
                    reasons.append(f"shares '{', '.join(sorted(shared))}' with '{row['name']}' "
                                   f"({row['source_type']}): possible parent/subsidiary")
    # Live-page mention catches customers added after the snapshot was built.
    pattern = re.compile(r"\b" + re.escape(name.lower()) + r"\b")
    for key, text in page_texts.items():
        if text and pattern.search(text.lower()):
            status = "REVIEW"
            reasons.append(f"name appears on labellerr.com/{key}: open the page and confirm")
    return status, sorted(set(reasons))


def run_check(targets, dnc_rows, page_texts):
    results = []
    for t in targets:
        status, reasons = check_company(t["company"], dnc_rows, page_texts)
        results.append({"company": t["company"], "status": status, "reasons": "; ".join(reasons)})
    return results


# ---------------------------------------------------------------------------
# 3. Score: fit + timing, fully explainable
# ---------------------------------------------------------------------------
def recency_points(months):
    if months <= 3:
        return 25
    if months <= 6:
        return 20
    if months <= 12:
        return 12
    if months <= 18:
        return 6
    return 2


def stacked(values, weights, extra, cap):
    pts = sorted((weights.get(v, 0) for v in values), reverse=True)
    if not pts:
        return 0
    return min(cap, pts[0] + extra * sum(1 for p in pts[1:] if p > 0))


def score_row(row, as_of):
    months = (as_of - parse_date(row["signal_date"])).days / 30.44
    parts = {
        "recency": recency_points(months),
        "signal": stacked(split_list(row["signal_types"]), SIGNAL_WEIGHTS, 2, 20),
        "data_fit": stacked(split_list(row["data_needs"]), NEED_WEIGHTS, 2, 20),
        "winnability": SIZE_WEIGHTS.get(row["size_band"], 0),
        "proof_point": PROOF_POINT if row["proof_point"].strip() else 0,
        "warm_path": WARM_PATH if row["warm_path"].strip() else 0,
        "india": INDIA_LINK if row["india_link"].strip() == "1" else 0,
    }
    total = sum(parts.values())
    tier = next(label for floor, label in TIERS if total >= floor)
    return total, tier, parts, round(months, 1)


def run_score(targets, check_results, as_of):
    status = {c["company"]: c["status"] for c in check_results}
    ranked = []
    for t in targets:
        total, tier, parts, months = score_row(t, as_of)
        if status.get(t["company"]) == "BLOCK":
            tier = "EXCLUDED"
        ranked.append({**t, "score": total, "tier": tier, "months_since_signal": months,
                       "dnc_status": status.get(t["company"], "UNCHECKED"),
                       "breakdown": " ".join(f"{k}={v}" for k, v in parts.items())})
    ranked.sort(key=lambda r: (r["tier"] == "EXCLUDED", -r["score"], r["company"]))
    for i, r in enumerate(ranked, 1):
        r["rank"] = i
    return ranked


# ---------------------------------------------------------------------------
# 4. Draft: first-draft openers from a data row (a human still edits every one)
# ---------------------------------------------------------------------------
BRIDGE = {
    "technical": "When {pain}, the slow part is rarely capture; it's getting consistent labels "
                 "(action segments, hand keypoints, object states) at the pace your team iterates.",
    "exec": "At your stage, labeled data tends to set the pace of new-task rollout more than "
            "hardware does, because {pain}.",
    "intro": "I'd value a pointer to whoever owns training data at {company}; {pain}, and that's "
             "the part we take off a robotics team's plate.",
}
ASK = {
    "technical": "Worth 20 minutes to compare notes on your label spec? I can bring a labeled sample "
                 "from a similar task so you can judge quality first.",
    "exec": "Open to a short call with our robotics lead, or a pointer to whoever owns training data?",
    "intro": "Would a two-line intro be possible?",
}
GENERIC_PROOF = ("Labellerr collects and labels egocentric and multimodal robotics data (RGB-D, "
                 "hand pose, action segments) with human-in-the-loop QA.")


def draft_for(target, contact):
    persona = contact["persona"] if contact["persona"] in BRIDGE else "exec"
    first = contact["name"].split()[0]
    proof = GENERIC_PROOF
    if target["proof_point"].strip():
        # "Coupang (warehouse automation)" -> customer="Coupang", use_case="warehouse automation"
        m = re.match(r"\s*(.+?)\s*\((.+)\)\s*$", target["proof_point"])
        customer, use_case = (m.group(1), m.group(2)) if m else (target["proof_point"], "a similar project")
        proof = f"{customer} used Labellerr for {use_case}. {GENERIC_PROOF}"
    body = "\n\n".join([
        f"Hi {first},",
        target["hook"],
        BRIDGE[persona].format(pain=target["pain"], company=target["company"]),
        proof,
        ASK[persona],
        "Gursimran Singh\nLabellerr AI",
    ])
    subject = f"{target['company']}: {target['focus']}"
    return subject, body


def run_draft(ranked, contacts):
    by_company = {}
    for c in contacts:
        by_company.setdefault(c["company"], []).append(c)
    drafts = []
    for t in ranked:
        if t["dnc_status"] == "BLOCK":
            continue
        for c in by_company.get(t["company"], []):
            if not c["name"].strip():
                continue
            subject, body = draft_for(t, c)
            words = word_count(body)
            flags = []
            if words > MAX_WORDS:
                flags.append(f"OVER {MAX_WORDS} WORDS")
            if t["dnc_status"] == "REVIEW":
                flags.append("HOLD: DNC review pending")
            if "confirm" in c["verification"].lower():
                flags.append("confirm contact before sending")
            drafts.append({"company": t["company"], "tier": t["tier"], "name": c["name"],
                           "role": c["role"], "persona": c["persona"], "subject": subject,
                           "body": body, "words": words, "flags": ", ".join(flags)})
    return drafts


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------
def write_reports(check_results, ranked, drafts, as_of, log):
    OUT.mkdir(parents=True, exist_ok=True)
    write_csv(OUT / "dnc_report.csv", check_results, ["company", "status", "reasons"])
    write_csv(OUT / "ranked_leads.csv", ranked,
              ["rank", "company", "segment", "tier", "score", "breakdown", "months_since_signal",
               "dnc_status", "signal", "why_now", "fit_risk"])

    lines = [f"# Ranked leads (as of {as_of.isoformat()})", "",
             "| # | Company | Segment | Tier | Score | DNC | Breakdown |",
             "|---|---|---|---|---|---|---|"]
    for r in ranked:
        lines.append(f"| {r['rank']} | {r['company']} | {r['segment']} | {r['tier']} | "
                     f"{r['score']} | {r['dnc_status']} | {r['breakdown']} |")
    (OUT / "ranked_leads.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    md = [f"# First-draft openers (auto-generated {as_of.isoformat()})", "",
          "> Machine first drafts. Every one is edited by hand before sending; "
          "the three final messages live in docs/03_outreach_messages.md.", ""]
    for d in drafts:
        md += [f"## {d['company']} (Tier {d['tier']}) to {d['name']}, {d['role']}",
               f"*Persona: {d['persona']} | {d['words']} words"
               + (f" | {d['flags']}" if d['flags'] else "") + "*", "",
               f"**Subject:** {d['subject']}", "", d["body"], "", "---", ""]
    (OUT / "drafts.md").write_text("\n".join(md), encoding="utf-8")

    (OUT / "run_log.txt").write_text("\n".join(log) + "\n", encoding="utf-8")


def print_summary(check_results, ranked, drafts, log):
    print("Labellerr pages:")
    print("\n".join(log))
    counts = {s: sum(1 for c in check_results if c["status"] == s) for s in ("CLEAR", "REVIEW", "BLOCK")}
    print(f"\nDNC check: {counts['CLEAR']} clear, {counts['REVIEW']} review, {counts['BLOCK']} blocked "
          f"(against {DNC_STATS['customers']} customers/partners and {DNC_STATS['brands']} owned brands)")
    for c in check_results:
        if c["status"] != "CLEAR":
            print(f"  {c['status']:<6} {c['company']}: {c['reasons']}")
    print("\nRanked leads:")
    print(f"  {'#':>2}  {'Company':<28} {'Tier':<8} {'Score':>5}  Segment")
    for r in ranked:
        print(f"  {r['rank']:>2}  {r['company']:<28} {r['tier']:<8} {r['score']:>5}  {r['segment']}")
    over = sum(1 for d in drafts if "OVER" in d["flags"])
    print(f"\nDrafts: {len(drafts)} generated ({over} over {MAX_WORDS} words)")
    print(f"Outputs written to {OUT.relative_to(ROOT)}/")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    p = argparse.ArgumentParser(description="Labellerr outbound helper")
    p.add_argument("step", nargs="?", default="all", choices=["all", "refresh", "check", "score", "draft"])
    p.add_argument("--offline", action="store_true", help="skip network; use cached pages + snapshot")
    p.add_argument("--as-of", default=None, help="date for recency scoring (YYYY-MM-DD), default today")
    p.add_argument("--targets", default=str(DATA / "targets.csv"))
    p.add_argument("--contacts", default=str(DATA / "contacts.csv"))
    p.add_argument("--dnc", default=str(DATA / "dnc_snapshot.csv"))
    args = p.parse_args(argv)

    as_of = parse_date(args.as_of) if args.as_of else dt.date.today()
    targets, contacts, dnc_rows = read_csv(args.targets), read_csv(args.contacts), read_csv(args.dnc)
    DNC_STATS["customers"] = sum(1 for r in dnc_rows if (r.get("level") or "block") == "block")
    DNC_STATS["brands"] = sum(len([a for a in r.get("aliases", "").split("|") if a])
                              for r in dnc_rows if r.get("level") == "review")

    page_texts, log = refresh(offline=args.offline)
    if args.step == "refresh":
        print("\n".join(log))
        return 0

    check_results = run_check(targets, dnc_rows, page_texts)
    ranked = run_score(targets, check_results, as_of)
    drafts = run_draft(ranked, contacts)
    write_reports(check_results, ranked, drafts, as_of, log)

    if args.step == "check":
        for c in check_results:
            print(f"{c['status']:<6} {c['company']}" + (f"  ({c['reasons']})" if c["reasons"] else ""))
    elif args.step == "score":
        for r in ranked:
            print(f"{r['rank']:>2}. {r['company']:<28} {r['tier']:<8} {r['score']:>3}  {r['breakdown']}")
    elif args.step == "draft":
        print(f"{len(drafts)} drafts written to {OUT.relative_to(ROOT)}/drafts.md")
    else:
        print_summary(check_results, ranked, drafts, log)
    return 0


if __name__ == "__main__":
    sys.exit(main())
