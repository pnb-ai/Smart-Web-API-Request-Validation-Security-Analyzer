"""Security analysis algorithms and detection automata built on the Regex Lab engine.

Automata-based regular expression filters serve as a high-speed first line of
defense and request hygiene layer. They are NOT a replacement for parameterized
queries, proper output encoding, context-aware serialization, and least-privilege
security controls.
"""

from functools import lru_cache
import re
from typing import Any, Literal
from urllib.parse import unquote

from app.automata.engine import simulate
from app.automata.equivalence import check_equivalence
from app.automata.models import Automaton, State, Transition
from app.automata.regex import compile_regex
from app.automata.symbols import expand_symbol
from app.automata.transformations import run_pipeline
from app.models.trace import TraceStep

DEFENSE_DISCLAIMER: str = (
    "Automata-based regular expression filters serve as a high-speed first line of "
    "defense and request hygiene layer. They are NOT a replacement for parameterized "
    "queries, proper output encoding, context-aware serialization, and least-privilege "
    "security controls."
)

FindingCategory = Literal[
    "sql_injection",
    "xss",
    "path_traversal",
    "command_injection",
    "null_byte",
    "crlf_injection",
    "oversized_parameter",
    "suspicious_client",
]

SeverityLevel = Literal["low", "medium", "high", "critical"]
NormalizationStage = Literal["raw", "url_decode_1", "url_decode_2", "lowercase", "collapse_whitespace"]

# Preset security rules compiled through Regex Lab into minimal DFAs.
SECURITY_RULES: list[dict[str, Any]] = [
    {
        "id": "path-traversal-dotdot",
        "name": "Path Traversal (Directory Climbing)",
        "category": "path_traversal",
        "severity": "high",
        "pattern": r"(\.\./|\.\.\\)",
        "explanation": "Directory traversal sequence detected ('../' or '..\\'), which attempts to climb out of the web root to access sensitive files on the server.",
        "recommendedFix": "Validate paths against a strict allowlist. Use secure path resolution APIs (e.g. Path.resolve() in Python or path.normalize() in Node) and assert that the canonical target starts with the allowed root directory.",
    },
    {
        "id": "path-traversal-encoded",
        "name": "Path Traversal (Encoded & Double Encoded)",
        "category": "path_traversal",
        "severity": "high",
        "pattern": r"(%2[eE]%2[eE](%2[fF]|%5[cC]|/|\\)|%252[eE]%252[eE](%252[fF]|%255[cC]|/|\\)|%2[eE]%2[eE]/)",
        "explanation": "URL-encoded or double-URL-encoded directory traversal sequence detected (%2e%2e%2f), attempting to evade single-pass string filters.",
        "recommendedFix": "Decode inputs once, reject multiple-encoding sequences, and canonicalize paths before any filesystem operation.",
    },
    {
        "id": "sqli-or-tautology",
        "name": "SQL Injection (Boolean Tautology)",
        "category": "sql_injection",
        "severity": "critical",
        "pattern": r"('([ \t]*)OR([ \t]*)1=1|'([ \t]*)or([ \t]*)1=1|'([ \t]*)OR([ \t]*)'1'='1|'([ \t]*)or([ \t]*)'1'='1|'([ \t]*)OR([ \t]*)'a'='a|'([ \t]*)or([ \t]*)'a'='a)",
        "explanation": "SQL injection tautology detected (' OR 1=1), intended to force SQL WHERE predicates to evaluate to true, bypassing authentication or exfiltrating data.",
        "recommendedFix": "Use parameterized queries (prepared statements) with bound parameters in all database calls. Never concatenate user input into SQL statements.",
    },
    {
        "id": "sqli-union-select",
        "name": "SQL Injection (UNION SELECT)",
        "category": "sql_injection",
        "severity": "critical",
        "pattern": r"(UNION|union)[ \t]+(ALL[ \t]+|all[ \t]+)?(SELECT|select)",
        "explanation": "SQL injection UNION SELECT statement detected, used to append arbitrary unauthorized queries to database result sets.",
        "recommendedFix": "Use prepared statements with type-safe query parameters or a verified ORM. Disallow arbitrary raw SQL construction.",
    },
    {
        "id": "sqli-comment",
        "name": "SQL Injection (Query Truncation Comment)",
        "category": "sql_injection",
        "severity": "medium",
        "pattern": r"(-- |--\r|--\n|/\*)",
        "explanation": "SQL comment delimiter sequence detected (-- or /*), used to truncate the remainder of a legitimate database query.",
        "recommendedFix": "Enforce parameterized queries so comment symbols are treated as literal characters rather than query grammar.",
    },
    {
        "id": "sqli-drop",
        "name": "SQL Injection (Stacked Destructive Statement)",
        "category": "sql_injection",
        "severity": "critical",
        "pattern": r";[ \t]*(DROP|drop|DELETE|delete|UPDATE|update|INSERT|insert|EXEC|exec)[ \t]+",
        "explanation": "Stacked SQL query or destructive statement detected (; DROP / DELETE), attempting to execute administrative or mutating statements.",
        "recommendedFix": "Disable stacked/multi-query support on database drivers, enforce least privilege on database users, and bind all parameters.",
    },
    {
        "id": "xss-script-tag",
        "name": "Cross-Site Scripting (Script Tag Injection)",
        "category": "xss",
        "severity": "high",
        "pattern": r"(<script|<SCRIPT|<Script)",
        "explanation": "Cross-Site Scripting (XSS) script tag detected (<script), attempting to execute arbitrary client-side JavaScript in victims' browsers.",
        "recommendedFix": "Apply context-aware HTML entity encoding before rendering dynamic content into HTML, and enforce a strict Content-Security-Policy (CSP) HTTP header.",
    },
    {
        "id": "xss-event-handler",
        "name": "Cross-Site Scripting (Inline Event Handler)",
        "category": "xss",
        "severity": "high",
        "pattern": r"(onerror|ONERROR|onload|ONLOAD|onclick|ONCLICK)[ \t]*=",
        "explanation": "Inline HTML event handler attribute detected (e.g. onerror=, onload=), frequently used as an XSS vector on HTML elements.",
        "recommendedFix": "Sanitize all untrusted HTML markup using DOMPurify or sanitize-html, or render content strictly as plain text (innerText).",
    },
    {
        "id": "xss-javascript-scheme",
        "name": "Cross-Site Scripting (JavaScript URL Scheme)",
        "category": "xss",
        "severity": "high",
        "pattern": r"(javascript:|JAVASCRIPT:|javascript%3[aA])",
        "explanation": "JavaScript pseudo-protocol URL detected (javascript:), enabling arbitrary script execution when set as href or src attributes.",
        "recommendedFix": "Validate user-supplied URLs against an allowlist of safe protocols (https:, http:, mailto:), rejecting javascript: and data: schemes.",
    },
    {
        "id": "cmd-injection-operators",
        "name": "Command Injection (Shell Metacharacters)",
        "category": "command_injection",
        "severity": "critical",
        "pattern": r"(;[ \t]*(cat|ls|id|whoami|sh|bash|curl|wget|rm|echo)|\|[ \t]*(cat|ls|id|whoami|sh|bash|curl|wget|rm|echo)|&&[ \t]*(cat|ls|id|whoami|sh|bash|curl|wget|rm|echo)|`[^`]+`|\$\([^\)]+\))",
        "explanation": "Operating system shell metacharacters and command chaining operators detected (; | && ` $(...)), used to execute unauthorized host commands.",
        "recommendedFix": "Never pass user input to system shells. Use structured process APIs (like Python subprocess.run(['cmd', arg], shell=False)) with separate argument arrays.",
    },
    {
        "id": "null-byte",
        "name": "Null Byte Injection (%00 / \\x00)",
        "category": "null_byte",
        "severity": "high",
        "pattern": r"(%00|%2500|\x00|\0)",
        "explanation": "Null byte injection detected (%00), traditionally leveraged to truncate filenames in C-based runtimes or bypass file extension filters.",
        "recommendedFix": "Strip or strictly reject null bytes in request input before passing values to filesystem or database APIs.",
    },
    {
        "id": "crlf-injection",
        "name": "CRLF Injection (Header Splitting / Log Forging)",
        "category": "crlf_injection",
        "severity": "medium",
        "pattern": r"(%0[dD]%0[aA]|%250[dD]%250[aA])",
        "explanation": "URL-encoded Carriage Return and Line Feed sequence detected (%0d%0a), potentially enabling HTTP header splitting, response smuggling, or log injection.",
        "recommendedFix": "Reject or strip CR and LF characters in header values and query parameters before relaying them into response headers or log files.",
    },
    {
        "id": "suspicious-user-agent",
        "name": "Suspicious Client (Security Scanner / Tool User-Agent)",
        "category": "suspicious_client",
        "severity": "medium",
        "pattern": r"(sqlmap|nikto|nessus|gobuster|masscan|nmap|dirbuster|wpscan|acunetix|havij)",
        "explanation": "User-Agent string matches signature of an automated vulnerability scanner or exploitation framework.",
        "recommendedFix": "Block or rate-limit known vulnerability scanners at the edge / WAF, and investigate origin IP addresses for potential reconnaissance.",
    },
]


@lru_cache(maxsize=64)
def compile_security_dfa(rule_id: str, pattern: str) -> tuple[Automaton, dict[tuple[str, str], str], set[str], str]:
    """Compile a security pattern to a minimized DFA and cached transition table."""
    nfa, _ = compile_regex(pattern)
    pipeline = run_pipeline(nfa, minimizer="hopcroft")
    dfa = pipeline["result"]
    assert isinstance(dfa, Automaton)

    delta: dict[tuple[str, str], str] = {}
    for edge in dfa.transitions:
        for sym in edge.symbols:
            for token in expand_symbol(sym):
                delta[(edge.from_, token)] = edge.to

    accepting = {state.id for state in dfa.states if state.isAccepting}
    start = dfa.start_state().id
    return dfa, delta, accepting, start


def scan_dfa_matches(dfa: Automaton, text: str, delta: dict[tuple[str, str], str], accepting: set[str], start: str) -> list[tuple[int, int, str]]:
    """Scan text for all non-overlapping substring matches recognized by dfa."""
    matches: list[tuple[int, int, str]] = []
    i = 0
    text_len = len(text)
    while i < text_len:
        state = start
        longest_match: tuple[int, int, str] | None = None
        for j in range(i, text_len):
            char = text[j]
            next_state = delta.get((state, char))
            if next_state is None:
                break
            state = next_state
            if state in accepting:
                longest_match = (i, j + 1, text[i : j + 1])
        if longest_match is not None:
            matches.append(longest_match)
            i = longest_match[1]
        else:
            i += 1
    return matches


def compute_normalizations(raw_value: str) -> list[tuple[NormalizationStage, str, str]]:
    """Compute the multi-level normalization chain and human-readable descriptions.
    
    Returns list of (stage_id, stage_label, transformed_value).
    """
    stages: list[tuple[NormalizationStage, str, str]] = [
        ("raw", "Raw Input", raw_value)
    ]

    dec1 = unquote(raw_value)
    stages.append(("url_decode_1", "URL Decode (Level 1)", dec1))

    dec2 = unquote(dec1)
    stages.append(("url_decode_2", "URL Decode (Level 2 - Double Encoded)", dec2))

    low = dec2.lower()
    stages.append(("lowercase", "Lowercase (Case Obfuscation)", low))

    collapsed = re.sub(r"[ \t\r\n]+", " ", low).strip()
    stages.append(("collapse_whitespace", "Whitespace Collapsed", collapsed))

    return stages


def _normalization_offset_map(raw_value: str, stage: NormalizationStage) -> tuple[str, list[int]]:
    """Return a normalized value and the raw offset that produced each character.

    URL unquoting can shrink multiple source characters into one. Keeping this map
    lets findings point at the actual encoded bytes shown in the request editor.
    """
    value = raw_value
    offsets = list(range(len(raw_value)))
    if stage in ("url_decode_1", "url_decode_2", "lowercase", "collapse_whitespace"):
        for _ in range(1 if stage == "url_decode_1" else 2 if stage in ("url_decode_2", "lowercase", "collapse_whitespace") else 0):
            pieces: list[str] = []
            mapped: list[int] = []
            i = 0
            while i < len(value):
                if value[i] == "%" and i + 2 < len(value):
                    try:
                        decoded = bytes.fromhex(value[i + 1:i + 3]).decode("latin-1")
                    except ValueError:
                        decoded = ""
                    if decoded:
                        pieces.append(decoded)
                        mapped.append(offsets[i])
                        i += 3
                        continue
                pieces.append(value[i])
                mapped.append(offsets[i])
                i += 1
            value, offsets = "".join(pieces), mapped
    if stage in ("lowercase", "collapse_whitespace"):
        value = value.lower()
    if stage == "collapse_whitespace":
        pieces = []
        mapped = []
        for match in re.finditer(r"[ \t\r\n]+|[^ \t\r\n]+", value):
            if match.group(0)[0] in " \t\r\n":
                if pieces:
                    pieces.append(" ")
                    mapped.append(offsets[match.start()])
            else:
                pieces.extend(match.group(0))
                mapped.extend(offsets[match.start():match.end()])
        value, offsets = "".join(pieces), mapped
    return value, offsets


def _calc_line_col(text: str, offset: int) -> tuple[int, int]:
    bounded = min(max(offset, 0), len(text))
    prefix = text[:bounded]
    line = prefix.count("\n") + 1
    last_nl = prefix.rfind("\n")
    col = (bounded - last_nl) if last_nl >= 0 else (bounded + 1)
    return line, col


def _calculate_risk_score(findings: list[dict[str, Any]]) -> tuple[int, str]:
    """Calculate 0-100 risk score and qualitative status from security findings."""
    if not findings:
        return 0, "CLEAN"

    counts: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for f in findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1

    # Base score calculation
    score = 0
    if counts["critical"] > 0:
        score += 70 + min(30, (counts["critical"] - 1) * 15 + counts["high"] * 5)
    elif counts["high"] > 0:
        score += 45 + min(40, (counts["high"] - 1) * 12 + counts["medium"] * 5)
    elif counts["medium"] > 0:
        score += 20 + min(35, (counts["medium"] - 1) * 10 + counts["low"] * 5)
    else:
        score += min(30, counts["low"] * 8)

    score = max(0, min(100, score))

    if score == 0:
        status = "CLEAN"
    elif score < 40:
        status = "LOW_RISK"
    elif score < 70:
        status = "SUSPICIOUS"
    else:
        status = "MALICIOUS"

    return score, status


def analyze_request_security(raw_request: str, custom_rules: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Perform comprehensive automata-based security analysis of an HTTP request.
    
    Normalizes input across 5 stages, scans for attack patterns with compiled DFAs,
    flags oversized parameters, and produces actionable security findings with an overall
    risk score and animation-ready trace.
    """
    trace: list[TraceStep] = []
    trace.append(TraceStep(
        title="Start Security Analysis",
        explanation="Parsing HTTP request segments and preparing detection automata from Regex Lab.",
        data={"requestLength": len(raw_request), "customRulesCount": len(custom_rules or [])}
    ))

    # Parse request structure
    first_break = raw_request.find("\n")
    req_line = raw_request[:first_break].strip("\r") if first_break >= 0 else raw_request
    parts = req_line.split(" ")
    method = parts[0] if parts else ""
    target = parts[1] if len(parts) == 3 else " ".join(parts[1:-1]) if len(parts) > 3 else (parts[1] if len(parts) > 1 else "")
    version = parts[-1] if len(parts) > 2 else ""

    headers_dict: dict[str, str] = {}
    header_lines: list[tuple[str, str, int]] = []
    head_end = raw_request.find("\r\n\r\n")
    if head_end == -1:
        head_end = raw_request.find("\n\n")
        body_start = head_end + 2 if head_end >= 0 else len(raw_request)
    else:
        body_start = head_end + 4

    headers_raw = raw_request[first_break + 1:head_end] if (first_break >= 0 and head_end >= 0) else ""
    body_raw = raw_request[body_start:] if body_start < len(raw_request) else ""

    cursor = first_break + 1 if first_break >= 0 else 0
    for line in headers_raw.splitlines():
        line_clean = line.strip("\r")
        if ":" in line_clean:
            h_name, h_val = line_clean.split(":", 1)
            h_name_clean = h_name.strip()
            h_val_clean = h_val.strip()
            headers_dict[h_name_clean.lower()] = h_val_clean
            header_lines.append((h_name_clean, h_val_clean, cursor))
        cursor += len(line) + (2 if "\r\n" in raw_request else 1)

    # Parse query parameters from target without destructive premature decoding
    path_only = target
    raw_query = ""
    query_parts: list[str] = []
    if "?" in target:
        path_only, raw_query = target.split("?", 1)
        query_parts = [p for p in raw_query.split("&") if p]

    # Build active rule set
    rules = list(SECURITY_RULES)
    if custom_rules:
        rules.extend(custom_rules)

    compiled_dfas: dict[str, Any] = {}
    findings: list[dict[str, Any]] = []
    finding_id_seq = 0
    normalization_trace_events: list[dict[str, Any]] = []

    # Segments to test for injection / malicious patterns:
    # (section_name, raw_content, base_offset_in_request)
    test_segments: list[tuple[str, str, int]] = []
    if target:
        test_segments.append(("target", target, raw_request.find(target)))
    for h_name, h_val, h_off in header_lines:
        test_segments.append(("header", f"{h_name}: {h_val}", h_off))
    if body_raw:
        test_segments.append(("body", body_raw, body_start))

    # Pre-compile DFAs
    for r in rules:
        try:
            dfa, delta, accepting, start = compile_security_dfa(r["id"], r["pattern"])
            compiled_dfas[r["id"]] = {
                "automaton": dfa.model_dump(by_alias=True, mode="json"),
                "delta": delta,
                "accepting": accepting,
                "start": start,
                "rule": r,
            }
        except Exception as err:
            trace.append(TraceStep(
                title=f"Rule Compilation Failed: {r['id']}",
                explanation=f"Regex Lab failed to compile pattern {r['pattern']}: {err}",
                data={"ruleId": r["id"], "error": str(err)}
            ))

    trace.append(TraceStep(
        title="Compiled Detection Automata",
        explanation=f"Compiled {len(compiled_dfas)} security rules to minimal DFAs using Hopcroft minimization.",
        data={"rules": list(compiled_dfas.keys())}
    ))

    # Check for oversized parameters / query length
    for q_part in query_parts:
        if len(q_part) > 1024:
            pos_offset = raw_request.find(q_part) if q_part else 0
            line_no, col_no = _calc_line_col(raw_request, pos_offset)
            finding_id_seq += 1
            findings.append({
                "id": f"sec-{finding_id_seq}",
                "ruleId": "oversized-parameter",
                "ruleName": "Oversized Parameter Value",
                "category": "oversized_parameter",
                "severity": "medium",
                "matchedText": q_part[:100] + "... (truncated)",
                "position": {
                    "offset": pos_offset,
                    "length": len(q_part),
                    "line": line_no,
                    "column": col_no,
                    "section": "parameter",
                },
                "explanation": f"Query parameter length ({len(q_part)} octets) exceeds normal limit (1024 octets).",
                "recommendedFix": "Enforce strict length limits on request parameters and reject oversized inputs.",
                "normalizationStep": "raw",
                "automatonId": None,
            })

    if len(target) > 2048:
        line_no, col_no = _calc_line_col(raw_request, raw_request.find(target))
        finding_id_seq += 1
        findings.append({
            "id": f"sec-{finding_id_seq}",
            "ruleId": "oversized-parameter",
            "ruleName": "Oversized Request URI Target",
            "category": "oversized_parameter",
            "severity": "medium",
            "matchedText": target[:100] + "...",
            "position": {
                "offset": raw_request.find(target),
                "length": len(target),
                "line": line_no,
                "column": col_no,
                "section": "target",
            },
            "explanation": f"Request URI target length ({len(target)} octets) exceeds standard 2048-octet operational limit.",
            "recommendedFix": "Limit URI target length to standard thresholds at the reverse proxy.",
            "normalizationStep": "raw",
            "automatonId": None,
        })

    # Execute multi-stage normalization and DFA scanning
    matched_fingerprints: set[tuple[str, int]] = set()

    for sec_name, sec_text, sec_offset in test_segments:
        if not sec_text:
            continue

        stages = compute_normalizations(sec_text)

        for rule_id, rule_info in compiled_dfas.items():
            rule = rule_info["rule"]
            dfa = rule_info["automaton"]
            delta = rule_info["delta"]
            accepting = rule_info["accepting"]
            start = rule_info["start"]

            # Filter User-Agent rule to only header section
            if rule["category"] == "suspicious_client" and sec_name != "header":
                continue

            exposed_stage: NormalizationStage | None = None
            detected_matches: list[tuple[int, int, str]] = []

            # Test each normalization step in order to pinpoint which step first exposed the attack
            for stage_id, stage_label, stage_value in stages:
                m = scan_dfa_matches(rule_info["automaton"], stage_value, delta, accepting, start)
                if m:
                    exposed_stage = stage_id
                    detected_matches = m
                    normalization_trace_events.append({
                        "ruleId": rule_id,
                        "section": sec_name,
                        "stage": stage_id,
                        "stageLabel": stage_label,
                        "match": m[0][2],
                    })
                    break

            if exposed_stage and detected_matches:
                for start_idx, end_idx, matched_val in detected_matches:
                    # Map the normalized match back to the original request. For
                    # decoded sequences, the raw span includes their %xx encoding.
                    _, offset_map = _normalization_offset_map(sec_text, exposed_stage)
                    raw_pos = sec_offset + (offset_map[start_idx] if start_idx < len(offset_map) else 0)
                    raw_end = sec_offset + (
                        offset_map[end_idx] if end_idx < len(offset_map) else len(sec_text)
                    )
                    raw_match_len = max(1, raw_end - raw_pos)

                    fp = (rule_id, raw_pos)
                    if fp in matched_fingerprints:
                        continue
                    matched_fingerprints.add(fp)

                    line_no, col_no = _calc_line_col(raw_request, raw_pos)
                    match_len = raw_match_len

                    finding_id_seq += 1
                    findings.append({
                        "id": f"sec-{finding_id_seq}",
                        "ruleId": rule_id,
                        "ruleName": rule["name"],
                        "category": rule["category"],
                        "severity": rule["severity"],
                        "matchedText": matched_val,
                        "position": {
                            "offset": raw_pos,
                            "length": match_len,
                            "line": line_no,
                            "column": col_no,
                            "section": sec_name,
                        },
                        "explanation": rule["explanation"],
                        "recommendedFix": rule["recommendedFix"],
                        "normalizationStep": exposed_stage,
                        "automatonId": rule_id,
                    })

                    trace.append(TraceStep(
                        title=f"Attack Pattern Matched: {rule['name']}",
                        explanation=f"Exposed by normalization '{exposed_stage}' in section '{sec_name}': matched {matched_val!r}.",
                        data={
                            "ruleId": rule_id,
                            "category": rule["category"],
                            "severity": rule["severity"],
                            "matchedText": matched_val,
                            "normalizationStep": exposed_stage,
                            "section": sec_name,
                            "position": {"line": line_no, "column": col_no, "offset": raw_pos},
                        }
                    ))

    # Calculate overall risk score
    risk_score, status = _calculate_risk_score(findings)

    # Sort findings by severity priority (critical -> high -> medium -> low)
    sev_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    findings.sort(key=lambda item: (sev_rank.get(item["severity"], 4), item["position"]["offset"] if item["position"] else 0))

    findings_summary = {
        "critical": sum(1 for f in findings if f["severity"] == "critical"),
        "high": sum(1 for f in findings if f["severity"] == "high"),
        "medium": sum(1 for f in findings if f["severity"] == "medium"),
        "low": sum(1 for f in findings if f["severity"] == "low"),
        "total": len(findings),
    }

    categories_detected = sorted(list({f["category"] for f in findings}))

    trace.append(TraceStep(
        title="Security Analysis Complete",
        explanation=f"Evaluated request: Status is {status} with risk score {risk_score}/100. Total findings: {len(findings)}.",
        data={
            "status": status,
            "riskScore": risk_score,
            "findingsSummary": findings_summary,
            "categories": categories_detected,
        }
    ))

    # Normalization steps summary for display
    norm_steps_summary = [
        {"step": "raw", "label": "Raw Request", "description": "Original unencoded text as received over the wire."},
        {"step": "url_decode_1", "label": "URL Decode (Level 1)", "description": "Standard single-pass URL unquoting."},
        {"step": "url_decode_2", "label": "URL Decode (Level 2)", "description": "Second-pass unquoting, exposing double-encoding filter bypasses."},
        {"step": "lowercase", "label": "Lowercase Folding", "description": "Case folding, exposing mixed-case keyword obfuscation."},
        {"step": "collapse_whitespace", "label": "Whitespace Collapsing", "description": "Collapsing multiple spaces, tabs, and newlines into single spaces."},
    ]

    return {
        "status": status,
        "riskScore": risk_score,
        "findings": findings,
        "findingsSummary": findings_summary,
        "categoriesDetected": categories_detected,
        "normalizationSteps": norm_steps_summary,
        "normalizationTrace": normalization_trace_events,
        "automata": {k: v["automaton"] for k, v in compiled_dfas.items()},
        "trace": [step.model_dump(mode="json") for step in trace],
        "defenseDisclaimer": DEFENSE_DISCLAIMER,
        "requestParts": {
            "method": method,
            "target": target,
            "version": version,
            "headers": headers_dict,
            "hasBody": bool(body_raw),
            "bodyLength": len(body_raw),
        },
    }


def diff_security_rules(old_pattern: str, new_pattern: str, test_payloads: list[str] | None = None) -> dict[str, Any]:
    """Compare two security regex patterns using the Equivalence Checker.
    
    Determines whether they recognize the exact same formal language, provides the shortest
    counterexample if distinguishable, and reports which test payloads are allowed or blocked
    by each rule version.
    """
    trace: list[TraceStep] = []
    trace.append(TraceStep(
        title="Compile Rule DFAs for Equivalence",
        explanation="Compiling both regular expressions into minimized DFAs with Regex Lab.",
        data={"oldPattern": old_pattern, "newPattern": new_pattern}
    ))

    nfa_old, _ = compile_regex(old_pattern)
    dfa_old = run_pipeline(nfa_old, minimizer="hopcroft")["result"]
    assert isinstance(dfa_old, Automaton)

    nfa_new, _ = compile_regex(new_pattern)
    dfa_new = run_pipeline(nfa_new, minimizer="hopcroft")["result"]
    assert isinstance(dfa_new, Automaton)

    trace.append(TraceStep(
        title="Check Language Equivalence",
        explanation="Running product BFS equivalence and inclusion check.",
        data={"oldStates": len(dfa_old.states), "newStates": len(dfa_new.states)}
    ))

    equiv_check = check_equivalence(dfa_old, dfa_new)
    trace.extend(equiv_check.trace)

    equiv_result = equiv_check.result
    is_equivalent = bool(equiv_result.get("equivalent", False))
    counterexample = equiv_result.get("counterexampleString")

    # Evaluate test payloads
    payload_evaluations: list[dict[str, Any]] = []
    samples = test_payloads or [
        "../",
        "..\\",
        "%2e%2e%2f",
        "' OR 1=1",
        "O'Brien",
        "UNION SELECT",
        "<script",
        "onerror=",
        "; cat /etc/passwd",
        "%00",
        "%0d%0a",
        "sqlmap/1.0",
        "valid_username_123",
    ]

    _, delta_old, accepting_old, start_old = compile_security_dfa("_diff_old", old_pattern)
    _, delta_new, accepting_new, start_new = compile_security_dfa("_diff_new", new_pattern)

    def evaluate_payload(dfa: Automaton, delta: dict[tuple[str, str], str], accepting: set[str], start: str, text: str) -> bool:
        sim = simulate(dfa, text)
        if sim.accepted:
            return True
        matches = scan_dfa_matches(dfa, text, delta, accepting, start)
        return len(matches) > 0

    for sample in samples:
        blocked_old = evaluate_payload(dfa_old, delta_old, accepting_old, start_old, sample)
        blocked_new = evaluate_payload(dfa_new, delta_new, accepting_new, start_new, sample)

        if blocked_old and blocked_new:
            behavior = "blocked_by_both"
        elif not blocked_old and not blocked_new:
            behavior = "allowed_by_both"
        elif not blocked_old and blocked_new:
            behavior = "newly_blocked"
        else:
            behavior = "newly_allowed"

        payload_evaluations.append({
            "payload": sample,
            "blockedByOld": blocked_old,
            "blockedByNew": blocked_new,
            "behavior": behavior,
        })

    return {
        "equivalent": is_equivalent,
        "counterexample": counterexample,
        "oldPattern": old_pattern,
        "newPattern": new_pattern,
        "oldDfa": dfa_old.model_dump(by_alias=True, mode="json"),
        "newDfa": dfa_new.model_dump(by_alias=True, mode="json"),
        "leftSubsetRight": equiv_result.get("leftSubsetRight", False),
        "payloadEvaluations": payload_evaluations,
        "trace": [step.model_dump(mode="json") for step in trace],
    }


__all__ = [
    "DEFENSE_DISCLAIMER",
    "SECURITY_RULES",
    "analyze_request_security",
    "compile_security_dfa",
    "compute_normalizations",
    "diff_security_rules",
    "scan_dfa_matches",
]
