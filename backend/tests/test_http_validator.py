from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.automata.http_validator import validate_http_request

client = TestClient(app)
CRLF = "\r\n"


def request(method="GET", target="/", version="HTTP/1.1", headers="Host: example.com\r\n", body=""):
    return f"{method} {target} {version}\r\n{headers}\r\n{body}"


def status_for(raw, check_id):
    report = validate_http_request(raw)
    return report, [item for item in report["checks"] if item["id"] == check_id]


@pytest.mark.parametrize("method,target,version,headers,body", [
    ("GET", "/", "HTTP/1.1", "Host: example.com\r\n", ""),
    ("HEAD", "/health", "HTTP/1.1", "Host: api.example.com\r\n", ""),
    ("POST", "/api/v1/users", "HTTP/1.1", "Host: example.com\r\nContent-Length: 2\r\nContent-Type: application/json\r\n", "{}"),
    ("PUT", "/item/1", "HTTP/1.1", "Host: example.com\r\nContent-Length: 3\r\n", "abc"),
    ("PATCH", "/item/1", "HTTP/1.1", "Host: example.com\r\nContent-Length: 1\r\n", "x"),
    ("DELETE", "/item/1", "HTTP/1.1", "Host: example.com\r\n", ""),
    ("OPTIONS", "*", "HTTP/1.1", "Host: example.com\r\n", ""),
    ("CONNECT", "example.com:443", "HTTP/1.1", "Host: example.com:443\r\n", ""),
    ("TRACE", "/", "HTTP/1.1", "Host: example.com\r\n", ""),
    ("GET", "/path?x=1&y=a%20b", "HTTP/1.1", "Host: example.com\r\n", ""),
    ("GET", "http://example.com/path?q=now", "HTTP/1.1", "Host: example.com\r\n", ""),
    ("GET", "https://example.com", "HTTP/1.1", "Host: example.com\r\n", ""),
    ("GET", "HTTP://example.com/path", "HTTP/1.1", "Host: example.com\r\n", ""),
    ("GET", "/", "HTTP/1.1", "Host: [::1]:443\r\n", ""),
    ("GET", "/", "HTTP/1.1", "Host: [v1.future-host]\r\n", ""),
    ("GET", "/", "HTTP/1.1", "Host: %65xample.com\r\n", ""),
    ("GET", "/a:b@c!$&'()*+,;=~-._", "HTTP/1.1", "Host: example.com\r\n", ""),
    ("GET", "/percent%2Fencoded", "HTTP/1.1", "Host: example.com\r\n", ""),
    ("GET", "/", "HTTP/1.0", "", ""),
    ("GET", "/", "HTTP/1.1", "Host: example.com:8080\r\nX-Test: visible\r\n", ""),
    ("FOO", "/extension", "HTTP/1.1", "Host: example.com\r\n", ""),
    ("POST", "/chunked", "HTTP/1.1", "Host: example.com\r\nTransfer-Encoding: chunked\r\n", "0\r\n\r\n"),
    ("POST", "/chunked", "HTTP/1.1", "Host: example.com\r\nTransfer-Encoding: gzip; level=1, chunked\r\n", "0\r\n\r\n"),
    ("POST", "/chunked", "HTTP/1.1", "Host: example.com\r\nTransfer-Encoding: gzip; note=\"a,b\", chunked\r\n", "0\r\n\r\n"),
    ("GET", "/", "HTTP/1.1", "Host: example.com\r\nX-Obs: caf\u00e9\r\n", ""),
])
def test_valid_requests(method, target, version, headers, body):
    report = validate_http_request(request(method, target, version, headers, body))
    assert report["overall"] == "VALID"


@pytest.mark.parametrize("version", ["HTTP/2.0", "HTTP/1.2", "HTTP/9.9", "HTTP/0.9"])
def test_unsupported_versions_are_invalid_with_reason(version):
    report, found = status_for(request(version=version), "version-support-status")
    assert report["overall"] == "INVALID"
    assert found and found[0]["status"] == "fail"
    assert "unsupported" in found[0]["message"].lower()


@pytest.mark.parametrize("line", ["GET  / HTTP/1.1", "GET /  HTTP/1.1", "GET\t/ HTTP/1.1", "GET / HTTP/1.1 extra", "GET  HTTP/1.1"])
def test_request_line_requires_single_space_separators(line):
    report = validate_http_request(line + CRLF + "Host: example.com\r\n\r\n")
    assert report["overall"] == "INVALID"
    assert any(check["id"] in {"request-line-shape", "request-line"} and check["status"] == "fail" for check in report["checks"])


@pytest.mark.parametrize("target", ["/bad%zz", "/bad%2", "/bad%GG", "/bad#fragment", "/bad\\path", "/a\tb", "/a\x01b", "/é", "http://bad host/path", "ftp://example.com/", "https://example.com/%aa%Q0"])
def test_invalid_request_targets_are_rejected(target):
    method = "CONNECT" if target == "example.com:443" else "GET"
    report = validate_http_request(request(method=method, target=target))
    assert report["overall"] == "INVALID"
    assert any(check["id"] == "target-syntax" and check["status"] == "fail" for check in report["checks"])


@pytest.mark.parametrize("headers,expected", [
    ("Host : example.com\r\n", "whitespace-before-colon"),
    ("Bad Header : x\r\n", "whitespace-before-colon"),
    (" : empty\r\n", "obs-fold"),
    ("Host: bad host\r\n", "host-value-valid"),
    ("Host: example.com:99999\r\n", "host-value-valid"),
    ("Host: [not-ipv6]\r\n", "host-value-valid"),
    ("Host:\r\n", "host-value-valid"),
    ("Host: example.com\r\nX: a\x00b\r\n", "field-value"),
    ("Host: example.com\r\nX: a\x7fb\r\n", "field-value"),
    ("Host: example.com\r\n x-folded\r\n", "obs-fold"),
    ("Host: example.com\r\nContent-Length: +1\r\n", "content-length"),
    ("Host: example.com\r\nTransfer-Encoding:\r\n", "transfer-encoding"),
])
def test_invalid_header_and_value_syntax(headers, expected):
    report = validate_http_request(request(headers=headers))
    assert report["overall"] == "INVALID"
    assert any(check["id"].startswith(expected) and check["status"] == "fail" for check in report["checks"])


@pytest.mark.parametrize("headers", ["", "Host: example.com\r\nHost: example.com\r\n", "Host: a.example\r\nHost: b.example\r\n"])
def test_http11_requires_exactly_one_host(headers):
    report, found = status_for(request(headers=headers), "host-count")
    assert report["overall"] == "INVALID"
    assert found[0]["status"] == "fail"


@pytest.mark.parametrize("headers,body", [
    ("Host: example.com\r\nContent-Length: 4\r\nTransfer-Encoding: chunked\r\n", "0\r\n\r\n"),
    ("Transfer-Encoding: chunked\r\nHost: example.com\r\nContent-Length: 0\r\n", ""),
    ("Host: example.com\r\nContent-Length: 1\r\nTransfer-Encoding: gzip, chunked\r\n", "0\r\n\r\n"),
    ("Host: example.com\r\nTransfer-Encoding: chunked\r\nContent-Length: 0\r\n", ""),
    ("Host: example.com\r\nContent-Length: 0\r\nTransfer-Encoding: chunked\r\n", ""),
    ("Host: example.com\r\nTransfer-Encoding: gzip\r\nContent-Length: 0\r\n", ""),
    ("Host: example.com\r\nContent-Length: 3\r\nTransfer-Encoding: chunked\r\n", "abc"),
    ("Host: example.com\r\nTransfer-Encoding: chunked\r\nContent-Length: 3\r\n", "abc"),
    ("Host: example.com\r\nContent-Length: 0\r\nTransfer-Encoding: chunked\r\n", "0\r\n\r\n"),
    ("Host: example.com\r\nTransfer-Encoding: chunked\r\nContent-Length: 0\r\n", "0\r\n\r\n"),
])
def test_smuggling_samples_reject_content_length_and_transfer_encoding(headers, body):
    report, found = status_for(request(method="POST", headers=headers, body=body), "content-length-transfer-encoding")
    assert report["overall"] == "INVALID"
    assert found[0]["status"] == "fail"
    assert "smuggling" in found[0]["message"].lower()


@pytest.mark.parametrize("header", ["Content-Length: 0\r\nContent-Length: 0\r\n", "Content-Length: 1\r\nContent-Length: 2\r\n", "Content-Length: 0\r\nContent-Length: 0\r\nContent-Length: 0\r\n"])
def test_duplicate_content_length_is_rejected(header):
    report, found = status_for(request(headers="Host: example.com\r\n" + header), "content-length-duplicates")
    assert report["overall"] == "INVALID"
    assert found[0]["status"] == "fail"


@pytest.mark.parametrize("length,body", [("1", ""), ("0", "x"), ("4", "abc"), ("1", "é"), ("999999999999999999999999999999", "x")])
def test_content_length_must_match_utf8_body_octets(length, body):
    report, found = status_for(request(method="POST", headers=f"Host: example.com\r\nContent-Length: {length}\r\n", body=body), "body-length")
    assert report["overall"] == "INVALID"
    assert found[0]["status"] == "fail"


@pytest.mark.parametrize("method,target", [("GET", "example.com:443"), ("POST", "*"), ("GET", "*"), ("CONNECT", "/tunnel")])
def test_method_target_compatibility(method, target):
    report, found = status_for(request(method=method, target=target), "method-target-compatibility")
    assert report["overall"] == "INVALID"
    assert found[0]["status"] == "fail"


def test_absolute_form_authority_must_be_valid_and_match_host():
    mismatch = validate_http_request(request(target="http://other.example/a"))
    assert next(item for item in mismatch["checks"] if item["id"] == "host-authority-match")["status"] == "fail"
    malformed = validate_http_request(request(target="http://[:::]/a", headers="Host: [:::]\r\n"))
    assert next(item for item in malformed["checks"] if item["id"] == "target-authority")["status"] == "fail"


@pytest.mark.parametrize("raw,rule", [
    ("GET / HTTP/1.1\nHost: example.com\n\n", "crlf-endings"),
    ("GET / HTTP/1.1\rHost: example.com\r\n\r\n", "crlf-endings"),
    ("GET / HTTP/1.1\r\nHost: example.com\r\n", "header-terminator"),
])
def test_line_endings_and_terminator(raw, rule):
    report = validate_http_request(raw)
    assert any(check["id"] == rule and check["status"] == "fail" for check in report["checks"])
    if rule == "crlf-endings" and raw.startswith("GET / HTTP/1.1\rHost"):
        assert next(check for check in report["checks"] if check["id"] == "request-line-crlf")["status"] == "fail"


def test_request_size_limits_are_configurable():
    raw = request(target="/long")
    assert validate_http_request(raw, max_request_line=100)["overall"] == "VALID"
    report = validate_http_request(raw, max_request_line=8)
    assert any(check["id"] == "request-line-limit" and check["status"] == "fail" for check in report["checks"])


def test_header_size_limit_is_configurable():
    report = validate_http_request(request(headers="Host: example.com\r\nX: 123456789\r\n"), max_header_section=10)
    assert any(check["id"] == "header-size" and check["status"] == "fail" for check in report["checks"])


def test_get_body_is_warning_not_invalidity():
    report = validate_http_request(request(headers="Host: example.com\r\nContent-Length: 1\r\n", body="x"))
    assert report["overall"] == "VALID"
    assert next(item for item in report["checks"] if item["id"] == "get-head-body")["status"] == "warn"


def test_body_newlines_are_content_not_header_line_endings():
    body = "a\nb"
    report = validate_http_request(request("POST", "/", headers=f"Host: example.com\r\nContent-Length: {len(body)}\r\n", body=body))
    assert report["overall"] == "VALID"
    assert next(item for item in report["checks"] if item["id"] == "crlf-endings")["status"] == "pass"


@pytest.mark.parametrize("coding", ["gzip", "chunked, gzip", "chunked, chunked"])
def test_transfer_encoding_request_requires_one_final_chunked_coding(coding):
    report, found = status_for(request(headers=f"Host: example.com\r\nTransfer-Encoding: {coding}\r\n"), "transfer-encoding-framing")
    assert report["overall"] == "INVALID"
    assert found[0]["status"] == "fail"


def test_report_exposes_automata_and_exact_positions():
    raw = request(target="/bad%zz")
    report = validate_http_request(raw)
    check = next(item for item in report["checks"] if item["id"] == "target-syntax")
    assert check["automatonId"] == "origin-form"
    assert report["automata"]["origin-form"]["automaton"]["type"] == "DFA"
    assert check["trace"]
    assert check["position"]["offset"] == raw.index("%")


@pytest.mark.parametrize("raw,rule,expected_offset", [
    (request(method="G/ T"), "method-token", lambda raw: raw.index("G/") + 1),
    (request(headers="Host: example.com\r\nContent-Length: 1x\r\n"), "content-length", lambda raw: raw.index("1x") + 1),
    (request(headers="Host : example.com\r\n"), "whitespace-before-colon", lambda raw: raw.index("Host ") + 4),
    (request(version="HTTP/1.x"), "http-version", lambda raw: raw.index("HTTP/1.x") + len("HTTP/1.")),
])
def test_syntax_errors_point_at_the_offending_character(raw, rule, expected_offset):
    report = validate_http_request(raw)
    check = next(item for item in report["checks"] if item["id"] == rule)
    assert check["status"] == "fail"
    assert check["position"]["offset"] == expected_offset(raw)


def test_custom_api_rules_are_compiled_and_enforced():
    report = validate_http_request(request("GET", "/api/v1/users/123", headers="Host: example.com\r\nX-Token: ok\r\nContent-Type: application/json\r\n"), custom_rules={"allowedMethods": ["GET", "POST"], "pathRegex": "^/api/v1/users/[0-9]+$", "requiredHeaders": ["x-token"], "allowedContentTypes": ["application/json"]})
    assert report["overall"] == "VALID"
    assert "policy-path" in report["automata"]


def test_custom_policy_failures_appear_as_separate_checks():
    report = validate_http_request(request("DELETE", "/private"), custom_rules={"allowedMethods": ["GET"], "pathRegex": "^/api/.*", "requiredHeaders": ["authorization"], "allowedContentTypes": ["application/json"]})
    assert report["overall"] == "INVALID"
    assert {item["id"] for item in report["checks"] if item["status"] == "fail"} >= {"policy-method", "policy-header-authorization", "policy-content-type"}


def test_custom_invalid_regex_returns_friendly_check():
    report = validate_http_request(request(), custom_rules={"pathRegex": "("})
    assert any(item["id"] == "policy-path" and item["status"] == "fail" for item in report["checks"])


def test_endpoint_accepts_raw_text_and_json_settings():
    raw = request()
    plain = client.post("/api/http/validate", content=raw, headers={"Content-Type": "text/plain"})
    structured = client.post("/api/http/validate", json={"rawRequest": raw})
    assert plain.status_code == structured.status_code == 200
    assert plain.json()["overall"] == structured.json()["overall"] == "VALID"


def test_endpoint_rejects_bad_configuration_cleanly():
    response = client.post("/api/http/validate", json={"rawRequest": "GET / HTTP/1.1\r\n\r\n", "maxRequestLine": 0})
    assert response.status_code == 400
    assert "valid UTF-8" in response.json()["detail"]
