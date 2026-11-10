"""
preflight.py - BrandPilot pre-flight engine (text path), deterministic layer.

Pipeline (plan section 6.2):
    1. Ingest & parse      -> text_ingest.py
    2. Review              -> deterministic reviewers in this file
    3. Aggregate           -> drop anything without a known rule, de-duplicate, sort
    4. Risk score + route  -> brand manager always, legal for HIGH/CRITICAL claim findings

Design invariants (plan sections 6.3 and 7.1):
    * "No source, no finding": every finding must cite a rule that exists in the brand kit.
      Hits with an unknown rule_id are dropped AND recorded in report.dropped_hits (never silent).
    * Deterministic checks are exact and explainable. They run with no external calls.
    * A reviewer that crashes is recorded; the report is marked incomplete (never silently skipped).
    * Humans decide: this module never approves or publishes anything.
    * Content is untrusted data and is never executed or followed as instructions.

The brand kit below mirrors the demo brand in Appendix B (Aranya Botanics). In the full system
the Brand Brain ingestion step will build a BrandKit from the uploaded guidelines.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from typing import Callable, Optional, Union

from app.services.text_ingest import IngestedText, IngestError, ingest_file, ingest_text

log = logging.getLogger("brandpilot.preflight")

SEVERITY_ORDER = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
SEVERITY_WEIGHT = {"LOW": 2, "MEDIUM": 8, "HIGH": 20, "CRITICAL": 40}

DISCLOSURE = (
    "Deterministic checks only; no AI model was used in this pass. "
    "Human approval is required before publication."
)


# --------------------------------------------------------------------------------------
# Brand kit (rules + approved facts)
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Rule:
    rule_id: str
    domain: str            # claim | term | fact | tone | a11y
    severity: str          # default severity; a reviewer may lower/raise it per finding
    title: str
    source_doc: str
    source_clause: str
    why: str

    @property
    def source(self) -> str:
        return f"{self.source_doc} §{self.source_clause}"


def default_rules() -> dict[str, Rule]:
    rules = [
        Rule("X-003", "claim", "CRITICAL", "Therapeutic language for a skin condition",
             "Claims library", "X-003",
             "Words such as cure, treat, erase or destroy applied to a skin condition create "
             "Drugs and Magic Remedies Act exposure."),
        Rule("X-007", "claim", "CRITICAL", "Unsubstantiated or absolute claim",
             "Claims library", "X-007",
             "'Clinically proven' needs a cited trial ID; absolute claims such as '100% safe' "
             "or 'guaranteed results' cannot be substantiated."),
        Rule("T-031", "term", "HIGH", "Banned superlative",
             "Terminology", "T-031",
             "Unqualified superlatives ('best-in-class', 'world-class', '#1') are banned; "
             "use approved, evidence-backed wording."),
        Rule("T-044", "term", "MEDIUM", "Non-approved terminology",
             "Terminology", "T-044",
             "Use 'consultants' (not 'gurus' or 'experts-for-hire') and 'customers' "
             "(not 'users'; product docs may use 'users')."),
        Rule("F-001", "fact", "MEDIUM", "Founding year conflicts with approved fact",
             "Facts", "F-001",
             "Approved fact: founded in 2016 in Bengaluru by the Rao sisters."),
        Rule("F-003", "fact", "MEDIUM", "Outdated founding year",
             "Facts", "F-003",
             "'Since 2019' is outdated; the correct year is 2016 (v3.2 guideline correction)."),
        Rule("V-002", "tone", "LOW", "Voice: warm, grounded, honest-expert",
             "Voice", "V-002",
             "Sentences of 22 words or fewer are preferred. Fear-based urgency is not allowed "
             "except in sanctioned sale windows (flag and require a reason)."),
        Rule("A-003", "a11y", "LOW", "Reading grade above target",
             "Accessibility", "A-003",
             "Consumer copy should read at grade 8 or lower."),
    ]
    return {r.rule_id: r for r in rules}


def default_claims() -> dict[str, str]:
    return {
        "C-014": "Dermatologist-tested for sensitive skin; visible improvement in 4 weeks* "
                 "- *individual results may vary",
        "C-021": "98% naturally derived ingredients (ISO 16128)",
    }


@dataclass
class BrandKit:
    name: str = "Aranya Botanics (demo kit)"
    version: str = "3.2"
    rules: dict[str, Rule] = field(default_factory=default_rules)
    approved_claims: dict[str, str] = field(default_factory=default_claims)
    founded_year: int = 2016
    outdated_since_years: tuple[int, ...] = (2019,)
    max_sentence_words: int = 22
    max_reading_grade: float = 8.0
    min_words_for_readability: int = 40


@dataclass
class ReviewContext:
    kit: BrandKit
    channel: str = "social"   # social | email | blog | landing | ad | product_docs


# --------------------------------------------------------------------------------------
# Data structures
# --------------------------------------------------------------------------------------
@dataclass
class Hit:
    """What a reviewer returns. The aggregator turns it into a Finding using the rule registry."""
    rule_id: str
    start: int
    end: int
    suggestion: Optional[str] = None
    replacement: Optional[str] = None     # exact text for [start, end) when one safe swap exists
    severity: Optional[str] = None        # overrides the rule default when set
    confidence: float = 1.0
    requires_reason: bool = False         # human must type a reason to waive/override
    scope: str = "span"                   # "span" or "document"


@dataclass
class Finding:
    finding_id: str
    rule_id: str
    domain: str
    severity: str
    confidence: float
    span_start: int
    span_end: int
    quote: str
    title: str
    why: str
    source: str
    reviewer: str
    suggestion: Optional[str] = None
    replacement: Optional[str] = None
    requires_reason: bool = False
    scope: str = "span"
    deterministic: bool = True


@dataclass
class PreflightReport:
    source: str
    text_sha256: str
    kit_name: str
    kit_version: str
    channel: str
    word_count: int
    findings: list[Finding]
    dropped_hits: list[dict]
    reviewers_run: list[str]
    reviewer_errors: dict[str, str]
    complete: bool
    risk_level: str
    risk_score: int
    routing: list[str]
    routing_reasons: list[str]
    quarantined: bool
    injection_flags: list[str]
    warnings: list[str]
    review_mode: str = "deterministic_only"
    disclosure: str = DISCLOSURE
    elapsed_ms: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


Reviewer = Callable[[IngestedText, ReviewContext], "list[Hit]"]


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------
def _sentence_at(doc: IngestedText, pos: int):
    for s in doc.sentences:
        if s.start <= pos < s.end:
            return s
    return None


def _match_case(src: str, repl: str) -> str:
    if len(src) > 1 and src.isupper():
        return repl.upper()
    if src[:1].isupper():
        return repl[:1].upper() + repl[1:]
    return repl


def _plural_aware(src: str, singular: str) -> str:
    plural = src.lower().endswith("s")
    return _match_case(src, singular + ("s" if plural else ""))


# --------------------------------------------------------------------------------------
# Reviewer 1: claims (X-003, X-007)
# --------------------------------------------------------------------------------------
_THERAPEUTIC_VERB = re.compile(
    r"\b(?:cur(?:e|es|ed|ing)|treat(?:s|ed|ing|ment)?|eras(?:e|es|ed|ing)|destroy(?:s|ed|ing)?)\b",
    re.I,
)
_SKIN_CONDITION = re.compile(
    r"\b(?:acne(?!-prone)|pimples?|breakouts?|eczema|psoriasis|dermatitis|rosacea|wrinkles?|"
    r"scars?|pigmentation|melasma|vitiligo|rashes?|dark\s+spots?|"
    r"skin\s+(?:conditions?|diseases?|infections?|disorders?))\b",
    re.I,
)
_CLINICALLY_PROVEN = re.compile(r"\bclinically\s+proven\b", re.I)
_TRIAL_ID = re.compile(r"\b[A-Z]{2,}-RCT-\d{4}-\d{2}\b")

_ABSOLUTES = [
    (re.compile(r"\b100\s?%\s*(?:safe|safety)\b", re.I), "CRITICAL", "safe"),
    (re.compile(r"\bguarantee[sd]?\s+(?:results?|outcomes?|cures?)\b", re.I), "CRITICAL", "guarantee"),
    (re.compile(r"\b(?:results?|outcomes?)\s+(?:are\s+|is\s+)?guaranteed\b", re.I), "CRITICAL", "guarantee"),
    (re.compile(r"\b100\s?%\s*(?:chemical[-\s]free|natural|pure|organic)\b", re.I), "HIGH", "natural"),
]


def claims_reviewer(doc: IngestedText, ctx: ReviewContext) -> list[Hit]:
    hits: list[Hit] = []
    c014 = ctx.kit.approved_claims.get("C-014")
    c021 = ctx.kit.approved_claims.get("C-021")

    # X-003: therapeutic verb close to a skin condition, inside one sentence.
    for sent in doc.sentences:
        for v in _THERAPEUTIC_VERB.finditer(sent.text):
            best = None
            for c in _SKIN_CONDITION.finditer(sent.text):
                gap = max(v.start(), c.start()) - min(v.end(), c.end())
                if gap <= 60 and (best is None or gap < best[0]):
                    best = (gap, c)
            if best is None:
                continue
            c = best[1]
            start = sent.start + min(v.start(), c.start())
            end = sent.start + max(v.end(), c.end())
            tip = "Remove the therapeutic wording."
            if c014:
                tip += f' Approved alternative (C-014): "{c014}".'
            hits.append(Hit("X-003", start, end, suggestion=tip, confidence=0.95))

    # X-007a: "clinically proven" without a cited trial ID in the same sentence.
    for m in _CLINICALLY_PROVEN.finditer(doc.text):
        sent = _sentence_at(doc, m.start())
        if sent is not None and _TRIAL_ID.search(sent.text):
            continue
        tip = 'Cite a trial ID (for example AB-RCT-2025-02) or remove "clinically proven".'
        if c014:
            tip += f' Approved alternative (C-014): "{c014}".'
        hits.append(Hit("X-007", m.start(), m.end(), suggestion=tip, confidence=0.95))

    # X-007b: absolute claims.
    for pattern, sev, kind in _ABSOLUTES:
        for m in pattern.finditer(doc.text):
            if kind == "natural" and c021:
                tip = f'Absolute claim cannot be substantiated. Use approved claim C-021: "{c021}".'
            elif kind == "safe":
                tip = "No product is 100% safe. Remove the absolute and use only approved claims."
            else:
                tip = "Results cannot be guaranteed. Use approved wording such as C-014, including 'individual results may vary'."
            hits.append(Hit("X-007", m.start(), m.end(), suggestion=tip, severity=sev, confidence=0.9))
    return hits


# --------------------------------------------------------------------------------------
# Reviewer 2: terminology (T-031, T-044)
# --------------------------------------------------------------------------------------
_T031 = [
    (re.compile(r"\bbest[\s-]in[\s-]class\b", re.I), 1.0),
    (re.compile(r"\bworld[\s-]class\b", re.I), 1.0),
    (re.compile(r"(?<![\w#])#\s?1\b"), 1.0),
    (re.compile(r"\bnumber\s+(?:one|1)\b", re.I), 0.8),
    (re.compile(r"\bno\.\s?1\b", re.I), 0.8),
]
_GURU = re.compile(r"\bgurus?\b", re.I)
_EXPERT_FOR_HIRE = re.compile(r"\bexperts?[\s-]for[\s-]hire\b", re.I)
_USERS = re.compile(r"\busers?\b", re.I)


def terminology_reviewer(doc: IngestedText, ctx: ReviewContext) -> list[Hit]:
    hits: list[Hit] = []
    for pattern, conf in _T031:
        for m in pattern.finditer(doc.text):
            hits.append(Hit(
                "T-031", m.start(), m.end(), confidence=conf,
                suggestion='Banned superlative. Approved alternatives: "best-selling" or '
                           '"most-loved (4.8 stars, 31k reviews)".',
            ))
    for m in _GURU.finditer(doc.text):
        hits.append(Hit("T-044", m.start(), m.end(),
                        replacement=_plural_aware(m.group(), "consultant"),
                        suggestion='Use "consultants" in service contexts.', confidence=0.7))
    for m in _EXPERT_FOR_HIRE.finditer(doc.text):
        hits.append(Hit("T-044", m.start(), m.end(),
                        replacement=_match_case(m.group(), "consultants"),
                        suggestion='Use "consultants" in service contexts.', confidence=0.7))
    if ctx.channel != "product_docs":
        for m in _USERS.finditer(doc.text):
            hits.append(Hit("T-044", m.start(), m.end(), severity="LOW",
                            replacement=_plural_aware(m.group(), "customer"),
                            suggestion='Use "customers" outside product documentation.',
                            confidence=0.6))
    return hits


# --------------------------------------------------------------------------------------
# Reviewer 3: facts (F-001, F-003)
# --------------------------------------------------------------------------------------
_FOUNDED = re.compile(r"\b(?:founded|established)\s+(?:in\s+)?(\d{4})\b", re.I)


def fact_reviewer(doc: IngestedText, ctx: ReviewContext) -> list[Hit]:
    hits: list[Hit] = []
    kit = ctx.kit
    year = kit.founded_year
    if kit.outdated_since_years:
        alt = "|".join(str(y) for y in kit.outdated_since_years)
        for m in re.finditer(rf"\bsince\s+(?:{alt})\b", doc.text, re.I):
            hits.append(Hit(
                "F-003", m.start(), m.end(),
                replacement=_match_case(m.group(), f"since {year}"),
                suggestion=f'Outdated. Approved fact: founded in {year}.', confidence=0.95))
    for m in _FOUNDED.finditer(doc.text):
        if int(m.group(1)) == year:
            continue
        new_text = m.group()[: m.start(1) - m.start()] + str(year)
        hits.append(Hit("F-001", m.start(), m.end(), replacement=new_text,
                        suggestion=f"Approved fact: founded in {year}.", confidence=0.9))
    return hits


# --------------------------------------------------------------------------------------
# Reviewer 4: tone (deterministic part of V-002)
# --------------------------------------------------------------------------------------
_URGENCY = re.compile(
    r"\b(?:act\s+now|hurry|last\s+chance|before\s+it(?:'|’)?s\s+too\s+late|"
    r"don(?:'|’)?t\s+miss\s+out|only\s+\d+\s+left|limited\s+time|"
    r"you(?:'|’)?ll\s+regret)\b",
    re.I,
)


def tone_reviewer(doc: IngestedText, ctx: ReviewContext) -> list[Hit]:
    hits: list[Hit] = []
    limit = ctx.kit.max_sentence_words
    for s in doc.sentences:
        n = len(re.findall(r"\S+", s.text))
        if n > limit:
            hits.append(Hit(
                "V-002", s.start, s.end, severity="LOW", confidence=1.0,
                suggestion=f"This sentence has {n} words; the preferred maximum is {limit}. "
                           f"Consider splitting it."))
    for m in _URGENCY.finditer(doc.text):
        hits.append(Hit(
            "V-002", m.start(), m.end(), severity="MEDIUM", confidence=0.8, requires_reason=True,
            suggestion="Fear-based or pressure urgency is only allowed in sanctioned sale "
                       "windows. Soften it, or keep it and record the reason."))
    return hits


# --------------------------------------------------------------------------------------
# Reviewer 5: readability (A-003) - Flesch-Kincaid grade, English text only
# --------------------------------------------------------------------------------------
def _syllables(word: str) -> int:
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w:
        return 0
    if len(w) <= 3:
        return 1
    w = re.sub(r"(?:[^laeiouy]es|ed|[^laeiouy]e)$", "", w)
    w = re.sub(r"^y", "", w)
    return max(1, len(re.findall(r"[aeiouy]{1,2}", w)))


def flesch_kincaid_grade(text: str, sentence_count: int) -> Optional[float]:
    words = re.findall(r"[A-Za-z']+", text)
    if not words or sentence_count == 0:
        return None
    syll = sum(_syllables(w) for w in words)
    return 0.39 * (len(words) / sentence_count) + 11.8 * (syll / len(words)) - 15.59


def readability_reviewer(doc: IngestedText, ctx: ReviewContext) -> list[Hit]:
    latin_words = re.findall(r"[A-Za-z']+", doc.text)
    if len(latin_words) < ctx.kit.min_words_for_readability:
        return []                      # too short (or not English) for a reliable grade
    grade = flesch_kincaid_grade(doc.text, len(doc.sentences))
    if grade is None or grade <= ctx.kit.max_reading_grade:
        return []
    return [Hit(
        "A-003", 0, len(doc.text), scope="document", severity="LOW", confidence=0.7,
        suggestion=f"Estimated reading grade is {grade:.1f}; the target is "
                   f"{ctx.kit.max_reading_grade:.0f} or lower. Use shorter sentences and "
                   f"simpler words.")]


DEFAULT_REVIEWERS: dict[str, Reviewer] = {
    "claims": claims_reviewer,
    "terminology": terminology_reviewer,
    "facts": fact_reviewer,
    "tone": tone_reviewer,
    "readability": readability_reviewer,
}


# --------------------------------------------------------------------------------------
# Aggregation, risk score, routing
# --------------------------------------------------------------------------------------
def aggregate(
    doc: IngestedText,
    hits_by_reviewer: dict[str, list[Hit]],
    kit: BrandKit,
) -> tuple[list[Finding], list[dict]]:
    findings: list[Finding] = []
    dropped: list[dict] = []
    seen: set[tuple[str, int, int]] = set()
    n = len(doc.text)

    for reviewer, hits in hits_by_reviewer.items():
        for h in hits:
            rule = kit.rules.get(h.rule_id)
            if rule is None:                                   # "no source, no finding"
                log.warning("Dropped hit from %s: unknown rule_id %r", reviewer, h.rule_id)
                dropped.append({"reviewer": reviewer, "rule_id": h.rule_id,
                                "reason": "unknown rule_id (no source clause)"})
                continue
            sev = h.severity or rule.severity
            if sev not in SEVERITY_ORDER:
                dropped.append({"reviewer": reviewer, "rule_id": h.rule_id,
                                "reason": f"invalid severity {sev!r}"})
                continue
            if h.scope == "document":
                start, end, quote = 0, n, ""
            else:
                if not (0 <= h.start < h.end <= n):
                    log.warning("Dropped hit from %s: bad span (%s, %s)", reviewer, h.start, h.end)
                    dropped.append({"reviewer": reviewer, "rule_id": h.rule_id,
                                    "reason": f"span out of range ({h.start}, {h.end})"})
                    continue
                start, end, quote = h.start, h.end, doc.text[h.start:h.end]
            key = (h.rule_id, start, end)
            if key in seen:
                continue
            seen.add(key)
            fid = hashlib.sha256(f"{doc.sha256}:{h.rule_id}:{start}:{end}".encode()).hexdigest()[:12]
            findings.append(Finding(
                finding_id=fid, rule_id=rule.rule_id, domain=rule.domain, severity=sev,
                confidence=round(float(h.confidence), 2), span_start=start, span_end=end,
                quote=quote, title=rule.title, why=rule.why, source=rule.source,
                reviewer=reviewer, suggestion=h.suggestion, replacement=h.replacement,
                requires_reason=h.requires_reason, scope=h.scope,
            ))

    findings.sort(key=lambda f: (f.span_start, -SEVERITY_ORDER[f.severity], f.rule_id))
    return findings, dropped


def score_risk(findings: list[Finding]) -> tuple[str, int]:
    if not findings:
        return "NONE", 0
    level = max((f.severity for f in findings), key=lambda s: SEVERITY_ORDER[s])
    score = min(100, sum(SEVERITY_WEIGHT[f.severity] for f in findings))
    return level, score


def route(findings: list[Finding], quarantined: bool, complete: bool) -> tuple[list[str], list[str]]:
    roles = ["brand_manager"]
    reasons = ["Human sign-off is always required before publication."]
    legal = [f for f in findings if f.domain == "claim" and f.severity in ("HIGH", "CRITICAL")]
    if legal:
        roles.append("legal")
        reasons.append(f"{len(legal)} HIGH/CRITICAL claim finding(s) require compliance sign-off.")
    if quarantined:
        reasons.append("Possible prompt-injection text detected; manual review required.")
    if not complete:
        reasons.append("One or more reviewers failed; this review is incomplete.")
    return roles, reasons


# --------------------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------------------
def run_preflight(
    content: Union[str, bytes, IngestedText],
    *,
    source: str = "paste",
    channel: str = "social",
    kit: Optional[BrandKit] = None,
    reviewers: Optional[dict[str, Reviewer]] = None,
) -> PreflightReport:
    """Ingest -> review -> aggregate -> score -> route. Raises IngestError on unusable input."""
    t0 = time.perf_counter()
    kit = kit or BrandKit()
    reviewers = reviewers if reviewers is not None else DEFAULT_REVIEWERS
    doc = content if isinstance(content, IngestedText) else ingest_text(content, source=source)
    ctx = ReviewContext(kit=kit, channel=channel)

    hits_by_reviewer: dict[str, list[Hit]] = {}
    errors: dict[str, str] = {}
    for name, fn in reviewers.items():
        try:
            hits_by_reviewer[name] = list(fn(doc, ctx))
        except Exception as exc:                                # never silently skip a check
            log.exception("Reviewer %s failed", name)
            errors[name] = f"{type(exc).__name__}: {exc}"

    findings, dropped = aggregate(doc, hits_by_reviewer, kit)
    complete = not errors
    level, score = score_risk(findings)
    if not complete and level == "NONE":
        level = "UNKNOWN"
    quarantined = bool(doc.injection_flags)
    roles, reasons = route(findings, quarantined, complete)

    return PreflightReport(
        source=doc.source, text_sha256=doc.sha256, kit_name=kit.name, kit_version=kit.version,
        channel=channel, word_count=doc.word_count, findings=findings, dropped_hits=dropped,
        reviewers_run=list(hits_by_reviewer), reviewer_errors=errors, complete=complete,
        risk_level=level, risk_score=score, routing=roles, routing_reasons=reasons,
        quarantined=quarantined, injection_flags=list(doc.injection_flags),
        warnings=list(doc.warnings), elapsed_ms=round((time.perf_counter() - t0) * 1000, 2),
    )


# --------------------------------------------------------------------------------------
# Human-readable output + CLI
# --------------------------------------------------------------------------------------
def format_report(r: PreflightReport) -> str:
    out = [
        f"PRE-FLIGHT REPORT | {r.source} | {len(r.findings)} findings | "
        f"risk: {r.risk_level} (score {r.risk_score}/100)",
        f"Mode: {r.review_mode} | reviewers: {', '.join(r.reviewers_run) or 'none'} | "
        f"{r.elapsed_ms} ms",
        f"Routing: {', '.join(r.routing)}",
    ]
    out += [f"  - {x}" for x in r.routing_reasons]
    if not r.complete:
        out.append("WARNING: incomplete review. Failed reviewers: " + ", ".join(r.reviewer_errors))
    if r.quarantined:
        out.append("WARNING: possible prompt injection: " + "; ".join(r.injection_flags))
    out.append("")
    for i, f in enumerate(r.findings, 1):
        where = "whole document" if f.scope == "document" else f'"{f.quote}" (chars {f.span_start}-{f.span_end})'
        out.append(f"{i}. [{f.domain.upper()} - {f.severity}] {where}")
        out.append(f"   Rule {f.rule_id} ({f.source}) | confidence {f.confidence}")
        out.append(f"   Why: {f.why}")
        if f.suggestion:
            out.append(f"   Fix: {f.suggestion}")
        if f.replacement:
            out.append(f"   One-click replacement: \"{f.replacement}\"")
        if f.requires_reason:
            out.append("   Waiving this finding requires a typed reason.")
        out.append("")
    if not r.findings:
        out.append("No findings from the deterministic checks.")
    out.append(r.disclosure)
    return "\n".join(out)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="BrandPilot pre-flight check (text, deterministic layer).")
    ap.add_argument("file", nargs="?", help=".txt/.md file; reads stdin when omitted")
    ap.add_argument("--channel", default="social",
                    choices=["social", "email", "blog", "landing", "ad", "product_docs"])
    ap.add_argument("--json", action="store_true", help="print the full report as JSON")
    args = ap.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    try:
        doc = ingest_file(args.file) if args.file else ingest_text(sys.stdin.read())
    except IngestError as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        return 2
    report = run_preflight(doc, channel=args.channel)
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2) if args.json else format_report(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
