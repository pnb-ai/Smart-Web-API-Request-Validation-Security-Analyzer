import json

from fastapi.testclient import TestClient

from app.automata.openapi_contract import validate_openapi_contract
from app.main import app

client = TestClient(app)

SPEC = {
    "openapi": "3.1.0",
    "info": {"title": "Users API", "version": "1.0.0"},
    "paths": {
        "/api/users/{userId}": {
            "get": {
                "operationId": "getUser",
                "parameters": [
                    {"name": "userId", "in": "path", "required": True, "schema": {"type": "integer", "minimum": 1}},
                    {"name": "limit", "in": "query", "required": True, "schema": {"type": "integer", "minimum": 1, "maximum": 100}},
                    {"name": "x-tenant", "in": "header", "required": True, "schema": {"type": "string", "minLength": 3}},
                ],
            }
        },
        "/api/users": {
            "post": {
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["name"],
                                "properties": {"name": {"type": "string", "minLength": 2}, "age": {"type": "integer", "minimum": 0}},
                                "additionalProperties": False,
                            }
                        }
                    },
                }
            }
        },
    },
}


def req(method="GET", target="/api/users/42?limit=10", headers="Host: api.example.com\r\nX-Tenant: north\r\n", body=""):
    return f"{method} {target} HTTP/1.1\r\n{headers}\r\n{body}"


def contract_checks(report):
    return {check["id"]: check for check in report["contract"]["checks"]}


def test_valid_path_query_and_required_header_match_operation():
    report = validate_openapi_contract(req(), SPEC)
    assert report["overall"] == "VALID"
    assert report["contract"]["path"] == "/api/users/{userId}"
    assert report["contract"]["method"] == "GET"
    assert all(item["status"] == "pass" for item in report["contract"]["checks"])


def test_path_and_query_values_are_deserialized_before_schema_validation():
    report = validate_openapi_contract(req(target="/api/users/nope?limit=0"), SPEC)
    checks = contract_checks(report)
    assert report["overall"] == "INVALID"
    assert "not of type 'integer'" in checks["contract-parameter-path-userId"]["message"]
    assert checks["contract-parameter-query-limit"]["status"] == "fail"
    assert checks["contract-parameter-query-limit"]["position"]["offset"] is not None


def test_missing_required_query_parameter_is_reported():
    report = validate_openapi_contract(req(target="/api/users/42?"), SPEC)
    assert contract_checks(report)["contract-parameter-query-limit"]["status"] == "fail"


def test_missing_required_header_is_reported():
    report = validate_openapi_contract(req(headers="Host: api.example.com\r\n"), SPEC)
    assert contract_checks(report)["contract-parameter-header-x-tenant"]["status"] == "fail"


def test_unmatched_path_and_unsupported_method_are_reported():
    path_report = validate_openapi_contract(req(target="/private"), SPEC)
    assert contract_checks(path_report)["contract-path"]["status"] == "fail"
    method_report = validate_openapi_contract(req(method="DELETE"), SPEC)
    assert contract_checks(method_report)["contract-method"]["status"] == "fail"


def test_request_json_schema_checks_required_fields_types_and_extra_fields():
    body = json.dumps({"name": "A", "age": "young", "unknown": True})
    headers = f"Host: api.example.com\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\n"
    report = validate_openapi_contract(req(method="POST", target="/api/users", headers=headers, body=body), SPEC)
    assert report["overall"] == "INVALID"
    schema_failures = [item for item in report["contract"]["checks"] if item["id"].startswith("contract-body-schema-")]
    assert len(schema_failures) >= 2
    assert all(item["position"]["offset"] >= len("POST /api/users HTTP/1.1\r\n" + headers + "\r\n") for item in schema_failures)


def test_request_body_required_and_content_type_are_enforced():
    missing = validate_openapi_contract(req(method="POST", target="/api/users"), SPEC)
    assert contract_checks(missing)["contract-request-body-required"]["status"] == "fail"
    body = '{"name":"Ada"}'
    headers = f"Host: api.example.com\r\nContent-Type: text/plain\r\nContent-Length: {len(body)}\r\n"
    wrong_type = validate_openapi_contract(req(method="POST", target="/api/users", headers=headers, body=body), SPEC)
    assert contract_checks(wrong_type)["contract-content-type"]["status"] == "fail"


def test_malformed_json_body_reports_body_offset():
    body = '{"name":'
    headers = f"Host: api.example.com\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\n"
    report = validate_openapi_contract(req(method="POST", target="/api/users", headers=headers, body=body), SPEC)
    check = contract_checks(report)["contract-body-json"]
    assert check["status"] == "fail"
    assert check["position"]["offset"] >= 0


def test_local_component_schema_references_are_resolved():
    spec = {**SPEC, "components": {"schemas": {"NewUser": {"type": "object", "required": ["name"], "properties": {"name": {"type": "string"}}}}}}
    spec["paths"]["/api/users"]["post"]["requestBody"]["content"]["application/json"]["schema"] = {"$ref": "#/components/schemas/NewUser"}
    body = '{"name":"Ada"}'
    headers = f"Host: api.example.com\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\n"
    report = validate_openapi_contract(req(method="POST", target="/api/users", headers=headers, body=body), spec)
    assert report["overall"] == "VALID"


def test_oas30_nullable_accepts_null():
    spec = {"openapi": "3.0.3", "info": {"title": "Nullable", "version": "1"}, "paths": {"/x": {"post": {"requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object", "required": ["value"], "properties": {"value": {"type": "string", "nullable": True}}}}}}}}}}
    body = '{"value":null}'
    headers = f"Host: api.example.com\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\n"
    report = validate_openapi_contract(req(method="POST", target="/x", headers=headers, body=body), spec)
    assert report["overall"] == "VALID"


def test_yaml_spec_and_endpoint_are_supported():
    yaml_spec = """
openapi: 3.1.0
info: {title: Tiny API, version: '1'}
paths:
  /ping:
    get: {}
"""
    response = client.post("/api/http/validate-contract", json={"rawRequest": "GET /ping HTTP/1.1\r\nHost: api.example.com\r\n\r\n", "openApiSpec": yaml_spec})
    assert response.status_code == 200
    assert response.json()["overall"] == "VALID"
    assert response.json()["contract"]["title"] == "Tiny API"


def test_rejects_unsupported_openapi_versions_and_external_refs():
    unsupported = {"openapi": "2.0", "info": {"title": "old", "version": "1"}, "paths": {"/": {}}}
    try:
        validate_openapi_contract(req(), unsupported)
        assert False, "expected version rejection"
    except ValueError as error:
        assert "Only OpenAPI 3.0 and 3.1" in str(error)
    external = {**SPEC, "paths": {"/x": {"get": {"parameters": [{"$ref": "https://example.com/params.json"}]}}}}
    try:
        validate_openapi_contract("GET /x HTTP/1.1\r\nHost: api.example.com\r\n\r\n", external)
        assert False, "expected remote reference rejection"
    except ValueError as error:
        assert "External OpenAPI references" in str(error)


def test_contract_failure_keeps_http_protocol_checks_and_trace():
    report = validate_openapi_contract("GET /missing HTTP/1.1\nHost: api.example.com\n\n", SPEC)
    assert any(item["id"] == "crlf-endings" and item["status"] == "fail" for item in report["checks"])
    assert any(item["title"].startswith("Fail: API path") for item in report["trace"])


def test_openapi_http_bearer_requirement_checks_presence_not_token_validity():
    spec = {**SPEC, "components": {"securitySchemes": {"bearer": {"type": "http", "scheme": "bearer"}}}}
    spec["paths"]["/api/users/{userId}"]["get"]["security"] = [{"bearer": []}]
    missing = validate_openapi_contract(req(), spec)
    assert contract_checks(missing)["contract-security"]["status"] == "fail"
    present = validate_openapi_contract(req(headers="Host: api.example.com\r\nX-Tenant: north\r\nAuthorization: Bearer example-token\r\n"), spec)
    assert contract_checks(present)["contract-security"]["status"] == "pass"
    assert "do not verify" not in contract_checks(present)["contract-security"]["message"].lower()


def test_openapi_server_base_path_and_host_are_checked():
    spec = {**SPEC, "servers": [{"url": "https://api.example.com/v1"}]}
    report = validate_openapi_contract(req(target="/v1/api/users/42?limit=10"), spec)
    checks = contract_checks(report)
    assert report["contract"]["path"] == "/api/users/{userId}"
    assert checks["contract-server-host"]["status"] == "pass"
    wrong_host = validate_openapi_contract(req(headers="Host: other.example.com\r\nX-Tenant: north\r\n"), spec)
    assert contract_checks(wrong_host)["contract-server-host"]["status"] == "fail"


def test_contract_endpoint_enforces_configured_http_limits():
    response = client.post("/api/http/validate-contract", json={
        "rawRequest": "GET /api/users/42?limit=10 HTTP/1.1\r\nHost: api.example.com\r\nX-Tenant: north\r\n\r\n",
        "openApiSpec": SPEC,
        "maxRequestLine": 10,
    })
    assert response.status_code == 200
    assert any(check["id"] == "request-line-limit" and check["status"] == "fail" for check in response.json()["checks"])

