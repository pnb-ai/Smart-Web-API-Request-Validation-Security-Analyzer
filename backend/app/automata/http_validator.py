"""HTTP/1.1 request validation: DFA syntax checks plus protocol rules.

Regular fragments are compiled through Regex Lab and its DFA pipeline. Rules
that depend on relationships between fields (framing, method/target pairing,
counts) remain explicit protocol checks.
"""

from functools import lru_cache
from ipaddress import IPv6Address
import re
from typing import Any
from urllib.parse import urlsplit

from app.automata.engine import simulate
from app.automata.models import Automaton
from app.automata.regex import RegexSyntaxError, compile_regex
from app.automata.transformations import run_pipeline
from app.models.trace import TraceStep

_TCHAR = "\\T"
_PCT = "(%[0-9A-Fa-f]{2}|[A-Za-z0-9._~!$&'()*+,;=:@/-])"
_QUERY = "(%[0-9A-Fa-f]{2}|[A-Za-z0-9._~!$&'()*+,;=:@/?-])"
_REG_NAME = "(\\g|%[0-9A-Fa-f]{2})+"
_IP_LITERAL = "\\[[0-9A-Fa-f:.]+\\]|\\[[vV][0-9A-Fa-f]+\\.[A-Za-z0-9._~!$&'()*+,;=:-]+\\]"
_HOST = f"({_REG_NAME}|{_IP_LITERAL})"
_AUTH = f"{_HOST}(:[0-9]+)?"
_HTTP_SCHEME = "[hH][tT][tT][pP]([sS])?://"
_TE_TOKEN = f"{_TCHAR}+"
_TE_QUOTED = '"' + '([!#-~]|\\\\[ \t-~])*' + '"'
_TE_PARAMETER = f"[ \t]*;[ \t]*{_TE_TOKEN}[ \t]*=[ \t]*({_TE_TOKEN}|{_TE_QUOTED})"
_METHODS = ("GET", "HEAD", "POST", "PUT", "DELETE", "CONNECT", "OPTIONS", "TRACE", "PATCH")

# Anchors are implicit: the automata simulator requires a full-string match.
RULE_PATTERNS: dict[str, str] = {
    "method-token": f"{_TCHAR}+",
    "known-method": "(" + "|".join(_METHODS) + ")",
    "http-version": "HTTP/[0-9]\\.[0-9]",
    "supported-version": "HTTP/1\\.[01]",
    "origin-form": f"/({_PCT})*(\\?{_QUERY}*)?",
    "absolute-form": f"{_HTTP_SCHEME}{_AUTH}(/({_PCT})*)?(\\?{_QUERY}*)?",
    "authority-form": f"{_HOST}:[0-9]+",
    "asterisk-form": "\\*",
    "request-line": f"{_TCHAR}+ [!-~]+ HTTP/[0-9]\\.[0-9]" + "\r\n",
    "header-field": f"{_TCHAR}+:[ \t]*[\t -~{chr(128)}-{chr(255)}]*",
    "host-value": f"{_AUTH}",
    "content-length": "[0-9]+",
    "transfer-encoding": f"{_TE_TOKEN}({_TE_PARAMETER})?([ \t]*,[ \t]*{_TE_TOKEN}({_TE_PARAMETER})?)*",
}


@lru_cache(maxsize=128)
def _compile_dfa(rule_id: str, pattern: str) -> tuple[Automaton, list[TraceStep]]:
    nfa, regex_trace = compile_regex(pattern)
    pipeline = run_pipeline(nfa, minimizer="hopcroft")
    dfa = pipeline["result"]
    assert isinstance(dfa, Automaton)
    trace = [*regex_trace, *pipeline["trace"]]
    trace.append(TraceStep(title=f"Ready: {rule_id}", explanation="This minimized DFA recognizes the complete syntax fragment.", data={"ruleId": rule_id, "stateCount": len(dfa.states)}))
    return dfa, trace


def _matches(rule_id: str, value: str, pattern: str | None = None) -> tuple[bool, list[dict[str, Any]], dict[str, Any]]:
    selected = pattern if pattern is not None else RULE_PATTERNS[rule_id]
    dfa, build_trace = _compile_dfa(rule_id, selected)
    simulated = simulate(dfa, value)
    return simulated.accepted, [step.model_dump(mode="json") for step in simulated.trace], {
        "automaton": dfa.model_dump(by_alias=True, mode="json"),
        "trace": [step.model_dump(mode="json") for step in build_trace],
    }


def _location(raw: str, offset: int | None) -> dict[str, int] | None:
    if offset is None:
        return None
    bounded = min(max(offset, 0), len(raw))
    before = raw[:bounded]
    return {"offset": bounded, "line": before.count("\n") + 1, "column": bounded - before.rfind("\n")}


def _check(checks: list[dict[str, Any]], raw: str, rule_id: str, title: str, passed: bool, message: str, rfc: str, position: int | None = None, *, severity: str = "fail", automaton_id: str | None = None, input_value: str | None = None, trace: list[dict[str, Any]] | None = None) -> None:
    checks.append({
        "id": rule_id, "title": title, "status": "pass" if passed else severity,
        "message": message, "rfc": rfc, "position": _location(raw, position),
        "automatonId": automaton_id, "input": input_value, "trace": trace or [],
    })


def _dfa_check(checks: list[dict[str, Any]], automata: dict[str, Any], raw: str, automaton_id: str, title: str, value: str, fail_message: str, rfc: str, position: int | None, *, pattern: str | None = None, severity: str = "fail") -> bool:
    accepted, trace, artifact = _matches(automaton_id, value, pattern)
    automata[automaton_id] = artifact
    failure = next((step["data"].get("index") for step in trace if step["title"].startswith("Read ") and step["data"].get("nextStates") == []), None)
    error_position = position + (failure if failure is not None else len(value)) if position is not None else None
    _check(checks, raw, automaton_id, title, accepted, f"{title} matches its regular syntax." if accepted else fail_message, rfc, error_position if not accepted else None, automaton_id=automaton_id, input_value=value, trace=trace, severity=severity)
    return accepted


def _tokenize_header_line(line: str) -> tuple[str, str] | None:
    colon = line.find(":")
    if colon <= 0:
        return None
    return line[:colon], line[colon + 1:].strip(" \t")


def _target_form(method: str, target: str) -> str | None:
    if target == "*":
        return "asterisk-form"
    if target.startswith("/"):
        return "origin-form"
    if target.lower().startswith(("http://", "https://")):
        return "absolute-form"
    if method.upper() == "CONNECT":
        return "authority-form"
    return None


def _target_error_offset(target: str) -> int | None:
    """Locate a malformed URI octet, especially the start of bad pct-encoding."""
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~!$&'()*+,;=:@/?[]%")
    index = 0
    while index < len(target):
        char = target[index]
        if char == "%":
            if index + 2 >= len(target) or any(digit not in "0123456789abcdefABCDEF" for digit in target[index + 1:index + 3]):
                return index
            index += 3
            continue
        if char not in allowed or ord(char) < 0x21 or ord(char) > 0x7e or char == "#":
            return index
        index += 1
    return None


def _valid_host(value: str) -> bool:
    if not value or value != value.strip(" \t"):
        return False
    if any(ord(char) < 33 or ord(char) > 126 or char in "/?#@" for char in value):
        return False
    try:
        parsed = urlsplit("//" + value)
        if not parsed.hostname or parsed.username is not None or parsed.password is not None:
            return False
        _ = parsed.port
        if value.startswith("["):
            if parsed.hostname.lower().startswith("v"):
                if not re.fullmatch(r"[vV][0-9A-Fa-f]+\.[A-Za-z0-9._~!$&'()*+,;=:-]+", parsed.hostname):
                    return False
            else:
                IPv6Address(parsed.hostname)
        return True
    except (ValueError, TypeError):
        return False


def _host_error_offset(value: str) -> int:
    if value.startswith("["):
        return 1
    port = value.rfind(":")
    if port >= 0 and value[port + 1:].isdigit():
        try:
            if int(value[port + 1:]) > 65535:
                return port + 1
        except ValueError:
            return port + 1
    return 0


def _custom_checks(raw: str, checks: list[dict[str, Any]], automata: dict[str, Any], rules: dict[str, Any], method: str, path: str, headers: dict[str, list[tuple[str, int]]]) -> None:
    allowed = [str(item).strip().upper() for item in rules.get("allowedMethods", []) if str(item).strip()]
    if allowed:
        pattern = "(" + "|".join(_escape_regex_literal(item) for item in allowed) + ")"
        _dfa_check(checks, automata, raw, "policy-method", "Allowed methods", method, f"Method {method} is not in the allowed method list.", "Custom policy", 0, pattern=pattern)
    path_pattern = str(rules.get("pathRegex", "")).strip()
    if path_pattern:
        pattern = path_pattern[1:] if path_pattern.startswith("^") else path_pattern
        pattern = pattern[:-1] if pattern.endswith("$") and not pattern.endswith("\\$") else pattern
        policy_id = "policy-path"
        try:
            _dfa_check(checks, automata, raw, policy_id, "API path pattern", path, "Path does not match the configured API pattern.", "Custom policy", raw.find(path), pattern=pattern)
        except (ValueError, RegexSyntaxError):
            _check(checks, raw, policy_id, "API path pattern", False, "The configured path pattern is not supported by Regex Lab.", "Custom policy", None)
    for required in [str(item).lower() for item in rules.get("requiredHeaders", []) if str(item)]:
        present = required in headers
        _check(checks, raw, f"policy-header-{required}", f"Required header: {required}", present, f"Header {required} is present." if present else f"Required header {required} is missing.", "Custom policy", None)
    content_types = [str(item).lower() for item in rules.get("allowedContentTypes", []) if str(item)]
    if content_types:
        values = headers.get("content-type", [])
        base = values[0][0].split(";", 1)[0].strip().lower() if values else ""
        pattern = "(" + "|".join(_escape_regex_literal(value) for value in content_types) + ")"
        _dfa_check(checks, automata, raw, "policy-content-type", "Allowed content type", base, f"Content type {base or '(missing)'} is not allowed by policy.", "Custom policy", values[0][1] if values and base not in content_types else None, pattern=pattern)


def _escape_regex_literal(value: str) -> str:
    return re.sub(r"([\\.^$*+?{}\[\]()|])", r"\\\1", value)


def _validate_custom_rules(rules: dict[str, Any] | None) -> None:
    if not rules:
        return
    for key, maximum, max_length in (("allowedMethods", 32, 32), ("requiredHeaders", 32, 128), ("allowedContentTypes", 32, 128)):
        values = rules.get(key, [])
        if not isinstance(values, list) or len(values) > maximum or any(not isinstance(value, str) or len(value) > max_length for value in values):
            raise ValueError(f"Custom policy field {key} must be a short list of at most {maximum} values.")
    path_pattern = rules.get("pathRegex", "")
    if not isinstance(path_pattern, str) or len(path_pattern) > 258:
        raise ValueError("Custom path regex is limited to 258 characters including anchors.")
    methods = [item.strip() for item in rules.get("allowedMethods", []) if item.strip()]
    if any(not re.fullmatch(r"[!#$%&'*+.^_`|~A-Za-z0-9-]+", item) for item in methods):
        raise ValueError("Allowed methods must use HTTP token characters only.")
    for header in rules.get("requiredHeaders", []):
        if not re.fullmatch(r"[!#$%&'*+.^_`|~A-Za-z0-9-]+", header):
            raise ValueError("Required header names must use HTTP token characters only.")
    method_pattern = "(" + "|".join(_escape_regex_literal(item.upper()) for item in methods) + ")"
    media = [item.strip().lower() for item in rules.get("allowedContentTypes", []) if item.strip()]
    content_pattern = "(" + "|".join(_escape_regex_literal(item) for item in media) + ")"
    if len(method_pattern) > 256 or len(content_pattern) > 256:
        raise ValueError("Custom method and media type lists must compile to regexes of at most 256 characters.")


def validate_http_request(raw: str, *, max_request_line: int = 8000, max_header_section: int = 65536, custom_rules: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a structured syntax/protocol report for one raw HTTP request."""
    if len(raw.encode("utf-8")) > 2_000_000:
        raise ValueError("Request text exceeds the 2 MB limit.")
    if not 1 <= max_request_line <= 65536 or not 1 <= max_header_section <= 1_000_000:
        raise ValueError("Line and header limits are outside their supported ranges.")
    _validate_custom_rules(custom_rules)
    checks: list[dict[str, Any]] = []
    automata: dict[str, Any] = {}

    # Strict CRLF scanning prevents tolerant splitlines parsing from hiding ambiguity.
    first_header_delimiter = raw.find("\r\n\r\n")
    head_end = first_header_delimiter + 4 if first_header_delimiter >= 0 else len(raw)
    message_head = raw[:head_end]
    newline_error = next((i for i, char in enumerate(message_head) if (char == "\n" and (i == 0 or message_head[i - 1] != "\r")) or (char == "\r" and (i + 1 == len(message_head) or message_head[i + 1] != "\n"))), None)
    _check(checks, raw, "crlf-endings", "CRLF line endings", newline_error is None, "Every line uses CRLF." if newline_error is None else "Bare LF or CR is not allowed; HTTP/1.1 lines end with CRLF.", "RFC 9112 §2.2", newline_error)

    cr_index = raw.find("\r")
    lf_index = raw.find("\n")
    break_positions = [index for index in (cr_index, lf_index) if index >= 0]
    request_break = min(break_positions) if break_positions else -1
    has_request_ending = request_break >= 0
    line_end = request_break if has_request_ending else len(raw)
    request_line = raw[:line_end]
    request_ending_position = request_break
    crlf_ok = has_request_ending and raw[request_break:request_break + 2] == "\r\n"
    first_line_end = request_break + (2 if crlf_ok else 1) if has_request_ending else len(raw)
    parts = request_line.split(" ")
    parsed_line = len(parts) == 3 and all(parts)
    method = parts[0] if parts else ""
    version = parts[-1] if len(parts) > 2 else ""
    target = parts[1] if len(parts) == 3 else " ".join(parts[1:-1]) if len(parts) > 3 else (parts[1] if len(parts) > 1 else "")
    request_line_with_ending = request_line + ("\r\n" if crlf_ok else "")
    _dfa_check(checks, automata, raw, "request-line", "Request-line syntax", request_line_with_ending, "Expected `method SP request-target SP HTTP-version CRLF` with exactly one SP between fields.", "RFC 9112 §3", 0)
    _check(checks, raw, "request-line-crlf", "Request-line terminator", crlf_ok, "Request line ends with CRLF." if crlf_ok else "Request line must end with CRLF.", "RFC 9112 §2.2", request_ending_position if not crlf_ok and request_ending_position >= 0 else len(raw) if not crlf_ok else None, automaton_id="request-line")
    repeated_separator = re.search(r" {2,}|\t", request_line)
    if parsed_line:
        shape_position = None
    elif repeated_separator:
        shape_position = repeated_separator.start() + (1 if request_line[repeated_separator.start()] == " " else 0)
    elif len(parts) > 3:
        shape_position = request_line.find(" ", request_line.find(" ", request_line.find(" ") + 1) + 1)
    else:
        shape_position = len(request_line)
    _check(checks, raw, "request-line-shape", "Request-line fields", parsed_line, "Request line has method, target, and version fields." if parsed_line else "Request line must contain exactly three non-empty fields separated by single spaces.", "RFC 9112 §3", shape_position)
    _check(checks, raw, "request-line-limit", "Request-line size", len(request_line.encode("utf-8")) <= max_request_line, f"Request line is within {max_request_line} octets." if len(request_line.encode("utf-8")) <= max_request_line else f"Request line exceeds the configured {max_request_line}-octet limit.", "RFC 9112 §3 (local limit)", max_request_line if len(request_line.encode("utf-8")) > max_request_line else None)

    _dfa_check(checks, automata, raw, "method-token", "Method token", method, "Method contains a character outside HTTP tchar.", "RFC 9112 §3.1", 0)
    _dfa_check(checks, automata, raw, "known-method", "Known method", method, "Method is a valid extension token but is not in the common-method set.", "RFC 9110 §9", 0, severity="warn")
    version_valid = _dfa_check(checks, automata, raw, "http-version", "HTTP-version syntax", version, "Expected HTTP/DIGIT.DIGIT.", "RFC 9112 §2.3", raw.find(version) if version else None)
    version_supported = _dfa_check(checks, automata, raw, "supported-version", "Supported HTTP version", version, "Only HTTP/1.0 and HTTP/1.1 are supported by this validator.", "RFC 9112 §2.3", raw.find(version) if version else None, severity="fail")
    _check(checks, raw, "version-support-status", "Version support", version_valid and version_supported, "HTTP version is supported." if version_supported else "Version is syntactically valid but unsupported." if version_valid else "Version could not be parsed.", "RFC 9112 §2.3", raw.find(version) if not version_supported else None)

    form = _target_form(method, target)
    target_id = form or "origin-form"
    target_patterns = {"origin-form": RULE_PATTERNS["origin-form"], "absolute-form": RULE_PATTERNS["absolute-form"], "authority-form": RULE_PATTERNS["authority-form"], "asterisk-form": RULE_PATTERNS["asterisk-form"]}
    target_start = raw.find(target) if target else None
    target_error = _target_error_offset(target)
    target_position = target_start + target_error if target_start is not None and target_error is not None else target_start
    target_ok = _dfa_check(checks, automata, raw, target_id, f"Request-target ({form or 'unknown form'})", target, "Target does not match a supported RFC 9112 request-target form or contains a forbidden character/percent escape.", "RFC 9112 §3.2; RFC 3986 §§2.1–2.3", target_start, pattern=target_patterns[target_id])
    compatible = form is not None and (form != "authority-form" or method.upper() == "CONNECT") and (form != "asterisk-form" or method.upper() == "OPTIONS") and (method.upper() != "CONNECT" or form == "authority-form")
    _check(checks, raw, "method-target-compatibility", "Method and target compatibility", compatible, "Method and target form are compatible." if compatible else "CONNECT requires authority-form and asterisk-form is reserved for OPTIONS.", "RFC 9112 §§3.2.3–3.2.4", raw.find(target) if not compatible else None)
    target_check = next((check for check in reversed(checks) if check["id"] == target_id), {})
    target_trace = target_check.get("trace", [])
    _check(checks, raw, "target-syntax", "Request-target syntax", target_ok, "Request target matches its form." if target_ok else "Request target is malformed.", "RFC 9112 §3.2; RFC 3986 §§2.1–2.3", target_position if not target_ok and target_error is not None else target_check.get("position", {}).get("offset") if not target_ok and target_check.get("position") else target_position if not target_ok else None, automaton_id=target_id, input_value=target, trace=target_trace)

    headers: dict[str, list[tuple[str, int]]] = {}
    separator = raw.find("\r\n\r\n", max(0, first_line_end - 2))
    has_header_terminator = separator >= 0
    header_region_end = separator if separator >= 0 else len(raw)
    header_text = raw[first_line_end:header_region_end]
    body_start = separator + 4 if separator >= 0 else len(raw)
    body = raw[body_start:] if separator >= 0 else ""
    header_bytes = len(header_text.encode("utf-8")) + (2 * (len(header_text.split("\r\n")) if header_text else 0))
    _check(checks, raw, "header-terminator", "Header terminator", has_header_terminator, "Header section ends with an empty CRLF line." if has_header_terminator else "Missing empty line (CRLF) terminating the header section.", "RFC 9112 §2.1", separator if not has_header_terminator and separator >= 0 else len(raw) if not has_header_terminator else None)
    _check(checks, raw, "header-size", "Header section size", header_bytes <= max_header_section, f"Header section is within {max_header_section} octets." if header_bytes <= max_header_section else f"Header section exceeds the configured {max_header_section}-octet limit.", "RFC 9112 §2 (local limit)", first_line_end if header_bytes > max_header_section else None)

    cursor = first_line_end
    for line in header_text.split("\r\n") if header_text else []:
        line_offset = cursor
        if line.startswith((" ", "\t")):
            _check(checks, raw, "obs-fold", "Obsolete line folding", False, "Leading whitespace is obsolete line folding (obs-fold) and is rejected.", "RFC 9112 §5.2", line_offset)
            _dfa_check(checks, automata, raw, "header-field", "Header field syntax", line, "Header line does not match field syntax.", "RFC 9112 §5", line_offset)
            cursor += len(line) + 2
            continue
        ws_colon = re.search(r"[ \t]+:", line)
        if ws_colon:
            _check(checks, raw, "whitespace-before-colon", "No whitespace before colon", False, "Whitespace between a field name and colon is forbidden.", "RFC 9112 §5.1", line_offset + ws_colon.start())
        parsed = _tokenize_header_line(line)
        if parsed is None:
            _dfa_check(checks, automata, raw, "header-field", "Header field syntax", line, "Expected a token field-name followed by a colon.", "RFC 9112 §5", line_offset)
            cursor += len(line) + 2
            continue
        name, value = parsed
        lowered = name.lower()
        colon = line.find(":")
        raw_value = line[colon + 1:]
        value_offset = line_offset + colon + 1 + len(raw_value) - len(raw_value.lstrip(" \t"))
        headers.setdefault(lowered, []).append((value, value_offset))
        field_ok = _dfa_check(checks, automata, raw, "header-field", f"Header field: {name}", line, "Header field must be a token name, colon, OWS, and a field value without control characters.", "RFC 9112 §§5.1–5.2", line_offset)
        _check(checks, raw, f"header-field-{line_offset}", f"Header field: {name}", field_ok and not ws_colon, "Header field is syntactically valid." if field_ok and not ws_colon else "Malformed header field.", "RFC 9112 §§5.1–5.2", line_offset + (ws_colon.start() if ws_colon else 0) if not (field_ok and not ws_colon) else None, automaton_id="header-field", input_value=line)
        bad_control = next((i for i, char in enumerate(value) if (ord(char) < 32 and char != "\t") or ord(char) == 127), None)
        _check(checks, raw, f"field-value-{line_offset}", f"Field value characters: {name}", bad_control is None, "Field value contains no forbidden controls." if bad_control is None else "Field value contains a forbidden control character.", "RFC 9110 §5.5", value_offset + bad_control if bad_control is not None else None)
        cursor += len(line) + 2

    host_values = headers.get("host", [])
    if version == "HTTP/1.1":
        host_count_ok = len(host_values) == 1
        _check(checks, raw, "host-count", "Host header count", host_count_ok, "Exactly one Host header is present." if host_count_ok else f"HTTP/1.1 requires exactly one Host header; found {len(host_values)}.", "RFC 9112 §3.2", host_values[1][1] if len(host_values) > 1 else (separator if not host_values and separator >= 0 else len(raw) if not host_values else None))
    else:
        _check(checks, raw, "host-count", "Host header count", len(host_values) <= 1, "At most one Host header is present." if len(host_values) <= 1 else "Multiple Host fields are invalid.", "RFC 9112 §3.2", host_values[1][1] if len(host_values) > 1 else None)
    for value, offset in host_values:
        host_auto_ok = _dfa_check(checks, automata, raw, "host-value", "Host value syntax", value, "Host must be a host name or IP literal with an optional numeric port.", "RFC 9112 §5; RFC 3986 §3.2.2", offset)
        host_ok = _valid_host(value)
        _check(checks, raw, f"host-value-valid-{offset}", "Host value validity", host_auto_ok and host_ok, "Host value is valid." if host_auto_ok and host_ok else "Host value is malformed or has an invalid port/IP literal.", "RFC 9112 §3.2; RFC 3986 §3.2.2", offset + _host_error_offset(value) if not (host_auto_ok and host_ok) else None)
    authority = ""
    if form == "absolute-form":
        try:
            authority = urlsplit(target).netloc
        except ValueError:
            authority = target
    elif form == "authority-form":
        authority = target
    authority_syntax_ok = not authority or _valid_host(authority)
    _check(checks, raw, "target-authority", "Request-target authority", authority_syntax_ok, "Target authority is syntactically valid." if authority_syntax_ok else "Target authority contains an invalid host or port.", "RFC 3986 §3.2", raw.find(authority) if authority and not authority_syntax_ok else None)
    if authority and host_values:
        authority_matches_host = authority.lower() == host_values[0][0].lower()
        _check(checks, raw, "host-authority-match", "Host matches target authority", authority_matches_host, "Host agrees with the request-target authority." if authority_matches_host else "Host must match the target authority, excluding any userinfo.", "RFC 9112 §§3.2.2–3.2.3", host_values[0][1] if not authority_matches_host else None)
    else:
        _check(checks, raw, "host-authority-match", "Host matches target authority", True, "No explicit target authority comparison is needed.", "RFC 9112 §§3.2.2–3.2.3")

    cls = headers.get("content-length", [])
    tes = headers.get("transfer-encoding", [])
    for value, offset in cls:
        _dfa_check(checks, automata, raw, "content-length", "Content-Length syntax", value, "Content-Length must contain one or more decimal digits.", "RFC 9112 §6.2; RFC 9110 §8.6", offset)
    cl_dupe_ok = len(cls) <= 1
    _check(checks, raw, "content-length-duplicates", "Content-Length count", cl_dupe_ok, "Content-Length occurs once." if cl_dupe_ok else "Duplicate Content-Length fields are rejected to avoid framing ambiguity.", "RFC 9112 §6.3; RFC 9110 §8.6", cls[1][1] if len(cls) > 1 else None)
    for value, offset in tes:
        _dfa_check(checks, automata, raw, "transfer-encoding", "Transfer-Encoding syntax", value, "Transfer-Encoding must be a comma-separated list of coding tokens.", "RFC 9112 §6.1; RFC 9112 §7", offset)
    codings = [coding.strip().split(";", 1)[0].strip().lower() for value, _ in tes for coding in value.split(",")]
    chunked_ok = not tes or (codings[-1:] == ["chunked"] and codings.count("chunked") == 1)
    _check(checks, raw, "transfer-encoding-framing", "Transfer-Encoding request framing", chunked_ok, "Transfer-Encoding ends with one final chunked coding." if chunked_ok else "A request Transfer-Encoding must end with exactly one chunked coding to determine its message length.", "RFC 9112 §§6.3, 7.1", tes[0][1] if tes and not chunked_ok else None)
    framing_ok = not (cls and tes)
    _check(checks, raw, "content-length-transfer-encoding", "No Content-Length with Transfer-Encoding", framing_ok, "Request framing uses a single mechanism." if framing_ok else "Content-Length and Transfer-Encoding together create request-smuggling risk and are rejected.", "RFC 9112 §§6.1, 6.3, 11.2; RFC 9110 §8.6", tes[0][1] if cls and tes else None)
    cl_value = cls[0][0] if cls else None
    cl_numeric = cl_value is not None and cl_value.isascii() and cl_value.isdigit()
    actual_length = str(len(body.encode("utf-8")))
    normalized_length = (cl_value or "").lstrip("0") or "0"
    body_length_ok = not cls or (cl_numeric and normalized_length == actual_length)
    _check(checks, raw, "body-length", "Body length", body_length_ok, "Body octet length matches Content-Length." if body_length_ok else f"Content-Length is {cl_value}; body contains {len(body.encode('utf-8'))} octets.", "RFC 9112 §6.3; RFC 9110 §8.6", (cls[0][1] if cls else body_start) if not body_length_ok else None)
    if method.upper() in {"GET", "HEAD"} and body:
        _check(checks, raw, "get-head-body", "GET/HEAD request content", False, f"{method.upper()} content has no generally defined semantics and can be rejected by recipients.", "RFC 9110 §§9.3.1–9.3.2", body_start, severity="warn")
    else:
        _check(checks, raw, "get-head-body", "GET/HEAD request content", True, "No GET/HEAD body warning applies.", "RFC 9110 §§9.3.1–9.3.2")

    if custom_rules:
        path_for_policy = target.split("?", 1)[0] if target.startswith("/") else target
        _custom_checks(raw, checks, automata, custom_rules, method, path_for_policy, headers)

    overall = "INVALID" if any(check["status"] == "fail" for check in checks) else "VALID"
    segments = [{"type": "request-line", "start": 0, "end": first_line_end}]
    method_start = raw.find(method) if method else 0
    target_start = raw.find(target, method_start + len(method)) if target else method_start + len(method) + 1
    version_start = raw.find(version, target_start + len(target)) if version else target_start + len(target) + 1
    if method:
        segments.append({"type": "method", "start": method_start, "end": method_start + len(method)})
    if target:
        segments.append({"type": "target", "start": target_start, "end": target_start + len(target)})
    if version:
        segments.append({"type": "version", "start": version_start, "end": version_start + len(version)})
    header_cursor = first_line_end
    for header_line in header_text.split("\r\n") if header_text else []:
        segments.append({"type": "header", "start": header_cursor, "end": header_cursor + len(header_line)})
        header_cursor += len(header_line) + 2
    if body:
        segments.append({"type": "body", "start": body_start, "end": len(raw)})

    trace_steps = [TraceStep(title="Validate HTTP request", explanation="Regular syntax checks use RFC-specific DFAs; protocol relationships are evaluated separately.", data={"overall": overall, "checkCount": len(checks), "failures": [check["id"] for check in checks if check["status"] == "fail"], "warnings": [check["id"] for check in checks if check["status"] == "warn"]})]
    trace_steps.extend(TraceStep(title=f"{check['status'].title()}: {check['title']}", explanation=check["message"], data={"checkId": check["id"], "status": check["status"], "rfc": check["rfc"], "position": check["position"], "automatonId": check["automatonId"]}) for check in checks)
    return {
        "overall": overall,
        "checks": checks,
        "parts": {"requestLine": {"start": 0, "end": first_line_end}, "method": method, "target": target, "version": version, "headers": header_text, "body": body, "bodyStart": body_start, "segments": segments},
        "automata": automata,
        "limits": {"maxRequestLine": max_request_line, "maxHeaderSection": max_header_section},
        "trace": [step.model_dump(mode="json") for step in trace_steps],
    }


__all__ = ["RULE_PATTERNS", "validate_http_request"]
