"""Comprehensive test suite for automata-based security analyzer.

Covers 40+ test scenarios including SQLi, XSS, Path Traversal, Command Injection,
Null Byte, CRLF Injection, Scanner Detection, Normalization Exposure Levels,
False Positives (e.g. O'Brien), and Rule Diff Equivalence.
"""

import pytest
from fastapi.testclient import TestClient

from app.automata.security import (
    DEFENSE_DISCLAIMER,
    SECURITY_RULES,
    analyze_request_security,
    diff_security_rules,
)
from app.main import app

client = TestClient(app)


# --- 1-4: Path Traversal Tests ---

def test_path_traversal_dotdot():
    req = "GET /download?file=../../../../etc/passwd HTTP/1.1\r\nHost: example.com\r\n\r\n"
    res = analyze_request_security(req)
    assert any(f["category"] == "path_traversal" for f in res["findings"])
    assert res["riskScore"] >= 45


def test_path_traversal_windows_backslashes():
    req = "GET /read?file=..\\..\\windows\\system32\\config\\SAM HTTP/1.1\r\nHost: example.com\r\n\r\n"
    res = analyze_request_security(req)
    assert any(f["category"] == "path_traversal" for f in res["findings"])


def test_path_traversal_encoded():
    req = "GET /download?path=%2e%2e%2f%2e%2e%2fetc%2fshadow HTTP/1.1\r\nHost: example.com\r\n\r\n"
    res = analyze_request_security(req)
    pt_findings = [f for f in res["findings"] if f["category"] == "path_traversal"]
    assert len(pt_findings) >= 1
    assert any(f["normalizationStep"] in ("raw", "url_decode_1") for f in pt_findings)


def test_path_traversal_double_encoded():
    req = "GET /view?doc=%252e%252e%252f%252e%252e%252fboot.ini HTTP/1.1\r\nHost: example.com\r\n\r\n"
    res = analyze_request_security(req)
    pt_findings = [f for f in res["findings"] if f["category"] == "path_traversal"]
    assert len(pt_findings) >= 1
    # Double encoding exposed at url_decode_2 or raw by encoded rule
    assert any(f["normalizationStep"] in ("url_decode_2", "raw") for f in pt_findings)


# --- 5-13: SQL Injection Tests ---

def test_sqli_or_tautology_raw():
    req = "POST /login HTTP/1.1\r\nHost: example.com\r\nContent-Type: application/x-www-form-urlencoded\r\n\r\nuser=admin' OR 1=1--"
    res = analyze_request_security(req)
    sqli = [f for f in res["findings"] if f["category"] == "sql_injection"]
    assert len(sqli) >= 1
    assert any(f["severity"] == "critical" for f in sqli)
    assert res["status"] == "MALICIOUS"
    assert res["riskScore"] >= 70


def test_sqli_or_tautology_url_encoded():
    req = "GET /items?id=10%27%20OR%201=1 HTTP/1.1\r\nHost: example.com\r\n\r\n"
    res = analyze_request_security(req)
    sqli = [f for f in res["findings"] if f["category"] == "sql_injection" and f["ruleId"] == "sqli-or-tautology"]
    assert len(sqli) == 1
    assert sqli[0]["normalizationStep"] == "url_decode_1"


def test_sqli_or_tautology_quoted_literals():
    req = "GET /search?q=foo%27%20OR%20%271%27=%271 HTTP/1.1\r\nHost: example.com\r\n\r\n"
    res = analyze_request_security(req)
    assert any(f["ruleId"] == "sqli-or-tautology" for f in res["findings"])


def test_sqli_union_select():
    req = "GET /products?cat=books%20UNION%20SELECT%20username,%20password%20FROM%20users HTTP/1.1\r\nHost: example.com\r\n\r\n"
    res = analyze_request_security(req)
    assert any(f["ruleId"] == "sqli-union-select" for f in res["findings"])
    assert res["riskScore"] >= 70


def test_sqli_union_all_select():
    req = "POST /query HTTP/1.1\r\nHost: example.com\r\n\r\nq=1 UNION ALL SELECT 1,2,3"
    res = analyze_request_security(req)
    assert any(f["ruleId"] == "sqli-union-select" for f in res["findings"])


def test_sqli_comment_delimiter():
    req = "GET /users?id=12--%20 HTTP/1.1\r\nHost: example.com\r\n\r\n"
    res = analyze_request_security(req)
    assert any(f["ruleId"] == "sqli-comment" for f in res["findings"])


def test_sqli_comment_c_style():
    req = "GET /users?id=12/*comment*/ HTTP/1.1\r\nHost: example.com\r\n\r\n"
    res = analyze_request_security(req)
    assert any(f["ruleId"] == "sqli-comment" for f in res["findings"])


def test_sqli_stacked_drop_table():
    req = "POST /api/user HTTP/1.1\r\nHost: example.com\r\n\r\nid=5; DROP TABLE accounts;"
    res = analyze_request_security(req)
    assert any(f["ruleId"] == "sqli-drop" for f in res["findings"])
    assert res["status"] == "MALICIOUS"


def test_sqli_stacked_delete():
    req = "POST /api/user HTTP/1.1\r\nHost: example.com\r\n\r\nid=5; DELETE FROM sessions"
    res = analyze_request_security(req)
    assert any(f["ruleId"] == "sqli-drop" for f in res["findings"])


# --- 14-20: Cross-Site Scripting (XSS) Tests ---

def test_xss_script_tag_basic():
    req = "GET /search?q=<script>alert(1)</script> HTTP/1.1\r\nHost: example.com\r\n\r\n"
    res = analyze_request_security(req)
    assert any(f["ruleId"] == "xss-script-tag" for f in res["findings"])


def test_xss_script_tag_case_obfuscated():
    req = "GET /search?q=<sCrIpt>alert(document.domain)</script> HTTP/1.1\r\nHost: example.com\r\n\r\n"
    res = analyze_request_security(req)
    xss = [f for f in res["findings"] if f["ruleId"] == "xss-script-tag"]
    assert len(xss) >= 1
    assert any(f["normalizationStep"] in ("raw", "lowercase") for f in xss)


def test_xss_onerror_event_handler():
    req = 'GET /profile?pic="><img src=x onerror=alert(1)> HTTP/1.1\r\nHost: example.com\r\n\r\n'
    res = analyze_request_security(req)
    assert any(f["ruleId"] == "xss-event-handler" for f in res["findings"])


def test_xss_onload_event_handler():
    req = 'POST /upload HTTP/1.1\r\nHost: example.com\r\n\r\n<svg onload=alert(1)>'
    res = analyze_request_security(req)
    assert any(f["ruleId"] == "xss-event-handler" for f in res["findings"])


def test_xss_onclick_event_handler():
    req = 'GET /render?html=<button onclick=run()>Click</button> HTTP/1.1\r\nHost: example.com\r\n\r\n'
    res = analyze_request_security(req)
    assert any(f["ruleId"] == "xss-event-handler" for f in res["findings"])


def test_xss_javascript_pseudo_protocol():
    req = "GET /redirect?url=javascript:alert(1) HTTP/1.1\r\nHost: example.com\r\n\r\n"
    res = analyze_request_security(req)
    assert any(f["ruleId"] == "xss-javascript-scheme" for f in res["findings"])


def test_xss_javascript_pseudo_protocol_encoded():
    req = "GET /redirect?url=javascript%3aalert(1) HTTP/1.1\r\nHost: example.com\r\n\r\n"
    res = analyze_request_security(req)
    assert any(f["ruleId"] == "xss-javascript-scheme" for f in res["findings"])


# --- 21-25: Command Injection Tests ---

def test_command_injection_semicolon_command():
    req = "POST /api/ping HTTP/1.1\r\nHost: example.com\r\n\r\nip=127.0.0.1; cat /etc/passwd"
    res = analyze_request_security(req)
    assert any(f["category"] == "command_injection" for f in res["findings"])
    assert res["status"] == "MALICIOUS"


def test_command_injection_pipe():
    req = "GET /diagnostics?host=127.0.0.1|whoami HTTP/1.1\r\nHost: example.com\r\n\r\n"
    res = analyze_request_security(req)
    assert any(f["category"] == "command_injection" for f in res["findings"])


def test_command_injection_double_ampersand():
    req = "GET /status?cmd=true&&id HTTP/1.1\r\nHost: example.com\r\n\r\n"
    res = analyze_request_security(req)
    assert any(f["category"] == "command_injection" for f in res["findings"])


def test_command_injection_backticks():
    req = "POST /tools HTTP/1.1\r\nHost: example.com\r\n\r\nparam=`id`"
    res = analyze_request_security(req)
    assert any(f["category"] == "command_injection" for f in res["findings"])


def test_command_injection_dollar_parentheses():
    req = "POST /tools HTTP/1.1\r\nHost: example.com\r\n\r\nparam=$(whoami)"
    res = analyze_request_security(req)
    assert any(f["category"] == "command_injection" for f in res["findings"])


# --- 26-28: Null Byte Injection Tests ---

def test_null_byte_encoded():
    req = "GET /download?file=secret.pdf%00.jpg HTTP/1.1\r\nHost: example.com\r\n\r\n"
    res = analyze_request_security(req)
    assert any(f["category"] == "null_byte" for f in res["findings"])


def test_null_byte_double_encoded():
    req = "GET /download?file=secret.pdf%2500.jpg HTTP/1.1\r\nHost: example.com\r\n\r\n"
    res = analyze_request_security(req)
    assert any(f["category"] == "null_byte" for f in res["findings"])


def test_null_byte_literal():
    req = "GET /download?file=secret.pdf\x00.jpg HTTP/1.1\r\nHost: example.com\r\n\r\n"
    res = analyze_request_security(req)
    assert any(f["category"] == "null_byte" for f in res["findings"])


# --- 29-30: CRLF Injection / Header Splitting Tests ---

def test_crlf_injection_in_query():
    req = "GET /login?next=home%0d%0aSet-Cookie:%20admin=true HTTP/1.1\r\nHost: example.com\r\n\r\n"
    res = analyze_request_security(req)
    assert any(f["category"] == "crlf_injection" for f in res["findings"])


def test_crlf_injection_in_header():
    req = "GET /home HTTP/1.1\r\nHost: example.com\r\nX-Forwarded-For: 127.0.0.1%0D%0AInjected-Header:%20evil\r\n\r\n"
    res = analyze_request_security(req)
    assert any(f["category"] == "crlf_injection" for f in res["findings"])


# --- 31-34: Suspicious User-Agent Tests ---

def test_suspicious_user_agent_sqlmap():
    req = "GET /api HTTP/1.1\r\nHost: example.com\r\nUser-Agent: sqlmap/1.5.11#stable\r\n\r\n"
    res = analyze_request_security(req)
    assert any(f["ruleId"] == "suspicious-user-agent" for f in res["findings"])


def test_suspicious_user_agent_nikto():
    req = "GET / HTTP/1.1\r\nHost: example.com\r\nUser-Agent: Mozilla/5.00 (Nikto/2.1.6) (Evasions:None) (Test:Port Check)\r\n\r\n"
    res = analyze_request_security(req)
    assert any(f["ruleId"] == "suspicious-user-agent" for f in res["findings"])


def test_suspicious_user_agent_nessus():
    req = "GET / HTTP/1.1\r\nHost: example.com\r\nUser-Agent: Nessus SOAP Client\r\n\r\n"
    res = analyze_request_security(req)
    assert any(f["ruleId"] == "suspicious-user-agent" for f in res["findings"])


def test_suspicious_user_agent_gobuster():
    req = "GET /admin HTTP/1.1\r\nHost: example.com\r\nUser-Agent: gobuster/3.1.0\r\n\r\n"
    res = analyze_request_security(req)
    assert any(f["ruleId"] == "suspicious-user-agent" for f in res["findings"])


# --- 35-36: Oversized Parameter & Target Tests ---

def test_oversized_query_parameter():
    long_val = "A" * 1500
    req = f"GET /api/test?data={long_val} HTTP/1.1\r\nHost: example.com\r\n\r\n"
    res = analyze_request_security(req)
    assert any(f["ruleId"] == "oversized-parameter" for f in res["findings"])


def test_oversized_uri_target():
    long_path = "/search?" + ("x=1&" * 900)
    req = f"GET {long_path} HTTP/1.1\r\nHost: example.com\r\n\r\n"
    res = analyze_request_security(req)
    assert any(f["category"] == "oversized_parameter" for f in res["findings"])


# --- 37-43: False Positive Checks ---

def test_false_positive_obrien_in_query():
    """A name like 'O'Brien' must NOT be a critical finding or SQL injection."""
    req = "GET /api/users?name=O'Brien HTTP/1.1\r\nHost: example.com\r\nUser-Agent: Mozilla/5.0\r\n\r\n"
    res = analyze_request_security(req)
    assert res["status"] == "CLEAN"
    assert res["riskScore"] == 0
    assert len(res["findings"]) == 0


def test_false_positive_obrien_in_json_body():
    """A JSON body containing O'Brien or contractions is benign."""
    body = '{"author": "Conan O\'Brien", "title": "It\'s a wonderful night"}'
    req = f"POST /articles HTTP/1.1\r\nHost: example.com\r\nContent-Type: application/json\r\n\r\n{body}"
    res = analyze_request_security(req)
    assert not any(f["severity"] in ("critical", "high") for f in res["findings"])
    assert res["riskScore"] == 0


def test_false_positive_english_contractions():
    req = "POST /feedback HTTP/1.1\r\nHost: example.com\r\n\r\nmessage=I couldn't find the link and it's not working."
    res = analyze_request_security(req)
    assert res["status"] == "CLEAN"
    assert res["riskScore"] == 0


def test_false_positive_standard_math_query():
    req = "GET /items?price_min=10&price_max=50&filter=score>5 HTTP/1.1\r\nHost: example.com\r\n\r\n"
    res = analyze_request_security(req)
    assert res["status"] == "CLEAN"
    assert res["riskScore"] == 0


def test_false_positive_static_assets_path():
    req = "GET /static/css/styles.min.css HTTP/1.1\r\nHost: example.com\r\n\r\n"
    res = analyze_request_security(req)
    assert not any(f["category"] == "path_traversal" for f in res["findings"])
    assert res["riskScore"] == 0


def test_false_positive_normal_headers_with_semicolon():
    req = "POST /api HTTP/1.1\r\nHost: example.com\r\nContent-Type: application/json; charset=utf-8\r\nAccept: text/html; q=0.9\r\n\r\n{}"
    res = analyze_request_security(req)
    assert not any(f["category"] == "command_injection" for f in res["findings"])
    assert res["riskScore"] == 0


def test_false_positive_legitimate_browser_user_agents():
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/121.0",
        "curl/7.88.1",
    ]
    for ua in user_agents:
        req = f"GET / HTTP/1.1\r\nHost: example.com\r\nUser-Agent: {ua}\r\n\r\n"
        res = analyze_request_security(req)
        assert not any(f["category"] == "suspicious_client" for f in res["findings"])


# --- 44-50: Normalization, Equivalence, and API Endpoint Tests ---

def test_normalization_exposure_reporting():
    # Case obfuscated XSS in URL-encoded query: exposed only after URL decode + lowercase!
    req = "GET /test?p=%3CsCrIpt%3E HTTP/1.1\r\nHost: example.com\r\n\r\n"
    res = analyze_request_security(req)
    xss = next(f for f in res["findings"] if f["ruleId"] == "xss-script-tag")
    assert xss["normalizationStep"] in ("url_decode_1", "lowercase")


def test_risk_score_aggregation_and_status():
    # Multi-vector attack: SQLi + XSS + Path Traversal
    req = "POST /profile?file=../../secret HTTP/1.1\r\nHost: example.com\r\n\r\nuser=admin' OR 1=1--&bio=<script>alert(1)</script>"
    res = analyze_request_security(req)
    assert res["riskScore"] >= 80
    assert res["status"] == "MALICIOUS"
    assert len(res["findings"]) >= 3


def test_api_analyze_json_endpoint():
    payload = {
        "rawRequest": "GET /api/view?path=../../etc/passwd HTTP/1.1\r\nHost: example.com\r\n\r\n"
    }
    resp = client.post("/api/security/analyze", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("SUSPICIOUS", "MALICIOUS")
    assert "findings" in data
    assert "riskScore" in data
    assert "trace" in data


def test_api_analyze_raw_text_endpoint():
    raw_req = "POST /login HTTP/1.1\r\nHost: example.com\r\n\r\nuser=admin' OR 1=1"
    resp = client.post("/api/security/analyze", content=raw_req.encode("utf-8"), headers={"Content-Type": "text/plain"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "MALICIOUS"
    assert data["riskScore"] >= 70


def test_api_rules_endpoint():
    resp = client.get("/api/security/rules")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["rules"]) >= 10
    assert "defenseDisclaimer" in data
    assert "first line of defense" in data["defenseDisclaimer"]


def test_rule_diff_equivalent():
    # Comparing (a|b) vs (b|a) -> equivalent
    diff = diff_security_rules("(a|b)", "(b|a)", ["a", "b", "c"])
    assert diff["equivalent"] is True
    assert diff["counterexample"] is None


def test_rule_diff_distinguishable_and_behavior():
    # Comparing strict path traversal vs wider one
    old_rule = r"(\.\./)"
    new_rule = r"(\.\./|\.\.\\)"
    diff = diff_security_rules(old_rule, new_rule, ["../", "..\\", "normal"])
    assert diff["equivalent"] is False
    assert diff["counterexample"] == "..\\"
    assert any(p["payload"] == "..\\" and p["behavior"] == "newly_blocked" for p in diff["payloadEvaluations"])


def test_defense_disclaimer_in_results():
    req = "GET / HTTP/1.1\r\nHost: example.com\r\n\r\n"
    res = analyze_request_security(req)
    assert "defenseDisclaimer" in res
    assert "NOT a replacement for parameterized queries" in res["defenseDisclaimer"]


def test_encoded_finding_highlights_original_request_bytes():
    request = "GET /search?q=%3Cscript%3E HTTP/1.1\r\nHost: example.com\r\n\r\n"
    finding = next(f for f in analyze_request_security(request)["findings"] if f["ruleId"] == "xss-script-tag")
    start = finding["position"]["offset"]
    length = finding["position"]["length"]
    assert request[start:start + length] == "%3Cscript"
    assert finding["normalizationStep"] == "url_decode_1"


def test_double_encoded_traversal_maps_to_original_payload():
    request = "GET /?p=%252e%252e%252f HTTP/1.1\r\nHost: example.com\r\n\r\n"
    finding = next(f for f in analyze_request_security(request)["findings"] if f["category"] == "path_traversal")
    start = finding["position"]["offset"]
    length = finding["position"]["length"]
    assert request[start:start + length].lower() == "%252e%252e%252f"


def test_analyze_endpoint_accepts_plain_request_text():
    request = "GET /?x=1 HTTP/1.1\r\nHost: example.com\r\n\r\n"
    response = client.post("/api/security/analyze", content=request, headers={"content-type": "text/plain"})
    assert response.status_code == 200
    assert response.json()["riskScore"] == 0
