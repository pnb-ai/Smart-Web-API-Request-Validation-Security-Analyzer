"""Validate a raw HTTP request against a local OpenAPI 3.x contract."""

from __future__ import annotations

from copy import deepcopy
import json
import re
from typing import Any
from urllib.parse import parse_qsl, unquote, unquote_plus, urlsplit

import yaml
from jsonschema import Draft4Validator, Draft202012Validator, FormatChecker, RefResolver
from jsonschema.exceptions import SchemaError

from app.automata.http_validator import validate_http_request
from app.models.trace import TraceStep

_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
_PARAMETER_LOCATIONS = {"path", "query", "header", "cookie"}
_MAX_SCHEMA_ERRORS = 30


def _load_spec(value: str | dict[str, Any]) -> dict[str, Any]:
    try:
        spec = yaml.safe_load(value) if isinstance(value, str) else value
    except yaml.YAMLError as error:
        raise ValueError("OpenAPI file is not valid JSON or YAML.") from error
    if not isinstance(spec, dict):
        raise ValueError("OpenAPI document must be an object.")
    version = spec.get("openapi")
    if not isinstance(version, str) or not (version.startswith("3.0.") or version.startswith("3.1.")):
        raise ValueError("Only OpenAPI 3.0 and 3.1 documents are supported.")
    if not isinstance(spec.get("info"), dict) or not isinstance(spec.get("paths"), dict):
        raise ValueError("OpenAPI document must contain info and paths objects.")
    if not spec["paths"]:
        raise ValueError("OpenAPI document has no paths to validate.")
    return spec


def _pointer(spec: dict[str, Any], reference: str) -> Any:
    if not reference.startswith("#/"):
        raise ValueError("External OpenAPI references are not loaded. Bundle the referenced file into the contract.")
    current: Any = spec
    for part in reference[2:].split("/"):
        key = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict) or key not in current:
            raise ValueError(f"OpenAPI reference {reference} does not resolve.")
        current = current[key]
    return current


def _resolve_object(spec: dict[str, Any], value: Any, trail: frozenset[str] = frozenset()) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("OpenAPI operation objects must be mappings.")
    reference = value.get("$ref")
    if not reference:
        return value
    if reference in trail:
        raise ValueError(f"Circular reference while resolving {reference}.")
    target = _pointer(spec, reference)
    resolved = _resolve_object(spec, target, trail | {reference})
    return {**resolved, **{key: item for key, item in value.items() if key != "$ref"}}


def _convert_oas30_schema(value: Any) -> Any:
    """Translate the OpenAPI 3.0 nullable extension to JSON Schema types."""
    if isinstance(value, list):
        return [_convert_oas30_schema(item) for item in value]
    if not isinstance(value, dict):
        return value
    schema = {key: _convert_oas30_schema(item) for key, item in value.items() if key != "nullable"}
    if value.get("nullable") is True:
        if "$ref" in schema:
            return {"anyOf": [schema, {"type": "null"}]}
        schema_type = schema.get("type")
        if isinstance(schema_type, str):
            schema["type"] = [schema_type, "null"]
        elif isinstance(schema_type, list) and "null" not in schema_type:
            schema["type"] = [*schema_type, "null"]
    return schema


def _validator(spec: dict[str, Any], schema: dict[str, Any]):
    if not isinstance(schema, dict):
        raise ValueError("OpenAPI schema must be an object.")
    schema = deepcopy(schema)
    resolution_spec = _convert_oas30_schema(spec) if spec["openapi"].startswith("3.0.") else spec
    if spec["openapi"].startswith("3.0."):
        schema = _convert_oas30_schema(schema)
        validator_type = Draft4Validator
    else:
        validator_type = Draft202012Validator
    try:
        validator_type.check_schema(schema)
    except SchemaError as error:
        raise ValueError(f"OpenAPI contains an invalid JSON Schema: {error.message}") from error

    def deny_remote(uri: str) -> Any:
        raise ValueError(f"External schema reference {uri} is disabled. Bundle references locally.")

    resolver = RefResolver.from_schema(resolution_spec, handlers={"http": deny_remote, "https": deny_remote})
    return validator_type(schema, resolver=resolver, format_checker=FormatChecker())


def _route_match(template: str, path: str) -> tuple[dict[str, str], int] | None:
    names: list[str] = []
    chunks: list[str] = []
    cursor = 0
    for match in re.finditer(r"\{([^{}]+)\}", template):
        chunks.append(re.escape(template[cursor:match.start()]))
        names.append(match.group(1))
        chunks.append("([^/]+)")
        cursor = match.end()
    chunks.append(re.escape(template[cursor:]))
    found = re.fullmatch("".join(chunks), path)
    if not found:
        return None
    return {name: unquote(value) for name, value in zip(names, found.groups())}, len(names)


def _server_url(server: dict[str, Any]) -> str:
    url = str(server.get("url", "/"))
    for name, definition in server.get("variables", {}).items():
        if isinstance(definition, dict) and "default" in definition:
            url = url.replace("{" + name + "}", str(definition["default"]))
    return url


def _server_path(url: str) -> str:
    parsed = urlsplit(url if "://" in url else "//" + url)
    path = parsed.path or "/"
    return path.rstrip("/") or "/"


def _server_path_candidates(path: str, servers: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    candidates = [(path, {})]
    for server in servers:
        base = _server_path(_server_url(server))
        if base != "/" and (path == base or path.startswith(base + "/")):
            stripped = path[len(base):] or "/"
            candidates.append((stripped, server))
    return candidates


def _security_check(spec: dict[str, Any], operation: dict[str, Any], headers: dict[str, list[tuple[str, int]]], query_values: list[tuple[str, str]], cookies: dict[str, str]) -> tuple[bool | None, str, str, int | None]:
    requirements = operation["security"] if "security" in operation else spec.get("security", [])
    if not requirements:
        return True, "This operation does not require an OpenAPI security scheme.", "security", None
    schemes = spec.get("components", {}).get("securitySchemes", {})
    unsupported: list[str] = []
    missing: list[str] = []
    for requirement in requirements:
        satisfied = True
        alternative_missing: list[str] = []
        for name in requirement:
            raw_scheme = schemes.get(name)
            if not isinstance(raw_scheme, dict):
                unsupported.append(name)
                satisfied = False
                continue
            scheme = _resolve_object(spec, raw_scheme)
            kind = scheme.get("type")
            scheme_name = scheme.get("name", name)
            location = scheme.get("in")
            offset: int | None = None
            if kind == "apiKey" and location == "header":
                present = bool(headers.get(str(scheme_name).lower()))
                offset = headers.get(str(scheme_name).lower(), [("", None)])[0][1] if present else None
            elif kind == "apiKey" and location == "query":
                found = next((value for key, value in query_values if key == scheme_name), None)
                present = found is not None
            elif kind == "apiKey" and location == "cookie":
                present = scheme_name in cookies
            elif kind == "http":
                auth = headers.get("authorization", [])
                offset = auth[0][1] if auth else None
                value = auth[0][0] if auth else ""
                auth_scheme = str(scheme.get("scheme", "")).lower()
                present = value.lower().startswith(auth_scheme + " ") and bool(value[len(auth_scheme) + 1:].strip())
            elif kind in {"oauth2", "openIdConnect"}:
                auth = headers.get("authorization", [])
                offset = auth[0][1] if auth else None
                value = auth[0][0] if auth else ""
                present = value.lower().startswith("bearer ") and bool(value[7:].strip())
            else:
                unsupported.append(name)
                satisfied = False
                continue
            if not present:
                satisfied = False
                alternative_missing.append(name)
        if satisfied:
            return True, "A credential is present in the declared location and format. Its validity and permissions are not verified.", "security", None
        missing.extend(alternative_missing)
    if unsupported:
        names = ", ".join(sorted(set(unsupported)))
        return None, f"Security scheme(s) {names} are not supported for automatic verification; credentials were not evaluated.", "security", None
    names = ", ".join(sorted(set(missing)))
    return False, f"Request does not satisfy any declared security requirement; missing credential(s): {names or 'unknown'}.", "security", None


def _headers_and_offsets(raw: str) -> tuple[dict[str, list[tuple[str, int]]], dict[str, int]]:
    headers: dict[str, list[tuple[str, int]]] = {}
    first_line = raw.find("\r\n")
    cursor = first_line + 2 if first_line >= 0 else len(raw)
    head_end = raw.find("\r\n\r\n", cursor)
    if head_end < 0:
        head_end = len(raw)
    for line in raw[cursor:head_end].split("\r\n"):
        colon = line.find(":")
        if colon <= 0:
            cursor += len(line) + 2
            continue
        name = line[:colon].strip().lower()
        value_start = cursor + colon + 1
        value = line[colon + 1:].strip(" \t")
        headers.setdefault(name, []).append((value, value_start))
        cursor += len(line) + 2
    return headers, {name: values[0][1] for name, values in headers.items()}


def _parameter_raw_values(location: str, name: str, path_values: dict[str, str], query_values: list[tuple[str, str]], headers: dict[str, list[tuple[str, int]]], cookies: dict[str, str]) -> list[str]:
    if location == "path":
        return [path_values[name]] if name in path_values else []
    if location == "query":
        return [value for key, value in query_values if key == name]
    if location == "header":
        return [value for value, _ in headers.get(name.lower(), [])]
    if location == "cookie":
        return [cookies[name]] if name in cookies else []
    return []


def _parameter_offset(raw: str, location: str, name: str, target: str, headers: dict[str, list[tuple[str, int]]], query_offset: int) -> int | None:
    if location == "header":
        values = headers.get(name.lower(), [])
        return values[0][1] if values else None
    if location == "query":
        for item in target.split("?", 1)[1].split("&") if "?" in target else []:
            key, separator, _ = item.partition("=")
            if unquote_plus(key) == name:
                return query_offset + target.find("?") + 1 + target.split("?", 1)[1].find(item) + len(key) + (1 if separator else 0)
    return None


def _deserialize_parameter(parameter: dict[str, Any], values: list[str], query_values: list[tuple[str, str]]) -> tuple[Any, str | None]:
    schema = parameter.get("schema", {})
    if not isinstance(schema, dict):
        return values[0] if values else None, "Parameter schema must be an object."
    location = parameter["in"]
    style = parameter.get("style", "form" if location in {"query", "cookie"} else "simple")
    explode = parameter.get("explode", style == "form")
    if style == "deepObject" and location == "query":
        prefix = parameter["name"] + "["
        obj = {key[len(prefix):-1]: value for key, value in query_values if key.startswith(prefix) and key.endswith("]")}
        return obj if obj else None, None
    if not values:
        return None, None
    parameter_type = schema.get("type", "string")
    if parameter_type == "array":
        if location == "query" and style == "form" and explode:
            items = values
        else:
            delimiter = {"spaceDelimited": " ", "pipeDelimited": "|"}.get(style, ",")
            items = [item for value in values for item in value.split(delimiter)]
        item_schema = schema.get("items", {})
        return [_coerce(value, item_schema.get("type", "string")) for value in items], None
    if len(values) > 1:
        return values[0], "Scalar parameter appears more than once; use an array schema for repeated values."
    return _coerce(values[0], parameter_type), None


def _coerce(value: str, schema_type: str) -> Any:
    if schema_type == "integer":
        try:
            return int(value, 10)
        except ValueError:
            return value
    if schema_type == "number":
        try:
            return float(value)
        except ValueError:
            return value
    if schema_type == "boolean":
        if value.lower() == "true":
            return True
        if value.lower() == "false":
            return False
    return value


def _check(checks: list[dict[str, Any]], trace: list[TraceStep], *, raw: str, check_id: str, title: str, passed: bool | None, message: str, contract_path: str, position: int | None = None) -> None:
    status = "warn" if passed is None else "pass" if passed else "fail"
    bounded = max(0, position) if position is not None else None
    before = raw[:bounded] if bounded is not None else ""
    check = {
        "id": check_id,
        "title": title,
        "status": status,
        "message": message,
        "rfc": "OpenAPI contract",
        "contractPath": contract_path,
        "position": {"offset": bounded, "line": before.count("\n") + 1, "column": bounded - before.rfind("\n")} if bounded is not None else None,
        "automatonId": None,
        "input": None,
    }
    checks.append(check)
    trace.append(TraceStep(title=f"{status.title()}: {title}", explanation=message, data={"checkId": check_id, "status": status, "contractPath": contract_path, "position": check["position"]}))


def validate_openapi_contract(raw: str, openapi_value: str | dict[str, Any], *, max_request_line: int = 8000, max_header_section: int = 65536, custom_rules: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return the HTTP report with additional OpenAPI operation checks."""
    spec = _load_spec(openapi_value)
    report = validate_http_request(raw, max_request_line=max_request_line, max_header_section=max_header_section, custom_rules=custom_rules)
    checks: list[dict[str, Any]] = []
    trace: list[TraceStep] = []
    parts = report["parts"]
    target = str(parts["target"])
    method = str(parts["method"]).lower()
    parsed_target = urlsplit(target)
    request_path = parsed_target.path or ("*" if target == "*" else "/")
    target_start = raw.find(target) if target else 0

    global_servers = spec.get("servers") or [{"url": "/"}]
    candidate_paths = _server_path_candidates(request_path, global_servers)
    path_matches: list[tuple[int, str, dict[str, str], dict[str, Any], str, dict[str, Any]]] = []
    for template, raw_item in spec["paths"].items():
        if not isinstance(template, str) or not isinstance(raw_item, dict):
            continue
        item = _resolve_object(spec, raw_item)
        for candidate_path, server in candidate_paths:
            matched = _route_match(template, candidate_path)
            if matched:
                parameters, dynamic_count = matched
                path_matches.append((dynamic_count, template, parameters, item, candidate_path, server))
    if not path_matches:
        _check(checks, trace, raw=raw, check_id="contract-path", title="API path exists", passed=False, message=f"No OpenAPI path matches {request_path!r}.", contract_path="paths", position=target_start)
        operation_path = "paths"
        path_parameters: dict[str, str] = {}
        path_item: dict[str, Any] = {}
    else:
        path_matches.sort(key=lambda item: (item[0], item[1].count("/"), len(item[1])))
        dynamic_count, operation_path, path_parameters, path_item, matched_path, matched_server = path_matches[0]
        _check(checks, trace, raw=raw, check_id="contract-path", title="API path exists", passed=True, message=f"Request path matches {operation_path}.", contract_path=f"paths.{operation_path}", position=target_start)

    operation = path_item.get(method) if method in _METHODS else None
    if not isinstance(operation, dict):
        _check(checks, trace, raw=raw, check_id="contract-method", title="HTTP method is defined", passed=False, message=f"{method.upper() or 'This'} method is not defined for {operation_path}.", contract_path=f"paths.{operation_path}.{method}", position=raw.find(str(parts["method"])) if parts["method"] else 0)
        operation = {}
    else:
        operation_id = operation.get("operationId")
        suffix = f" ({operation_id})" if operation_id else ""
        _check(checks, trace, raw=raw, check_id="contract-method", title="HTTP method is defined", passed=True, message=f"{method.upper()} is defined for {operation_path}{suffix}.", contract_path=f"paths.{operation_path}.{method}", position=raw.find(str(parts["method"])) if parts["method"] else 0)

    effective_servers = operation.get("servers") or path_item.get("servers") or global_servers
    request_host = raw.split("\r\n")[1:]
    host_value = next((line.split(":", 1)[1].strip() for line in request_host if ":" in line and line.split(":", 1)[0].lower() == "host"), "")
    declared_hosts = [urlsplit(_server_url(server) if "://" in _server_url(server) else "//" + _server_url(server)).netloc for server in effective_servers if isinstance(server, dict)]
    declared_hosts = [host.lower() for host in declared_hosts if host]
    if declared_hosts:
        host_ok = host_value.lower() in declared_hosts
        host_offset = raw.lower().find("host:") + len("host:") if "host:" in raw.lower() else None
        _check(checks, trace, raw=raw, check_id="contract-server-host", title="Host matches an API server", passed=host_ok, message=f"Host matches one of the declared API servers." if host_ok else f"Host {host_value or '(missing)'} does not match the declared server(s): {', '.join(declared_hosts)}.", contract_path="servers", position=host_offset if not host_ok else None)

    headers, header_value_offsets = _headers_and_offsets(raw)
    target_query = parsed_target.query
    query_values = parse_qsl(target_query, keep_blank_values=True)
    cookies: dict[str, str] = {}
    for cookie_value, _ in headers.get("cookie", []):
        for pair in cookie_value.split(";"):
            key, separator, value = pair.strip().partition("=")
            if separator:
                cookies[key] = value

    security_passed, security_message, security_path, security_offset = _security_check(spec, operation, headers, query_values, cookies)
    _check(checks, trace, raw=raw, check_id="contract-security", title="API authentication requirement", passed=security_passed, message=security_message, contract_path=security_path, position=security_offset)

    raw_parameters = [*path_item.get("parameters", []), *operation.get("parameters", [])]
    resolved_parameters: dict[tuple[str, str], dict[str, Any]] = {}
    for raw_parameter in raw_parameters:
        parameter = _resolve_object(spec, raw_parameter)
        location, name = parameter.get("in"), parameter.get("name")
        if location in _PARAMETER_LOCATIONS and isinstance(name, str):
            resolved_parameters[(location, name.lower() if location == "header" else name)] = parameter

    query_start = target_start + (target.find("?") + 1 if "?" in target else len(target))
    for (location, normalized_name), parameter in resolved_parameters.items():
        name = parameter["name"]
        parameter_path = f"paths.{operation_path}.{method}.parameters[{location}.{name}]"
        values = _parameter_raw_values(location, normalized_name, path_parameters, query_values, headers, cookies)
        position = _parameter_offset(raw, location, normalized_name, target, headers, target_start)
        schema = parameter.get("schema", {})
        required = location == "path" or bool(parameter.get("required", False))
        if not values:
            if required:
                _check(checks, trace, raw=raw, check_id=f"contract-parameter-{location}-{name}", title=f"Required {location} parameter: {name}", passed=False, message=f"Required {location} parameter {name!r} is missing.", contract_path=parameter_path, position=target_start if location == "path" else None)
            continue
        value, serialization_error = _deserialize_parameter(parameter, values, query_values)
        if serialization_error:
            _check(checks, trace, raw=raw, check_id=f"contract-parameter-{location}-{name}", title=f"Parameter: {name}", passed=False, message=serialization_error, contract_path=parameter_path, position=position)
            continue
        if spec["openapi"].startswith("3.0."):
            schema = _convert_oas30_schema(schema)
        try:
            validator = _validator(spec, schema)
            errors = sorted(validator.iter_errors(value), key=lambda error: list(map(str, error.absolute_path)))
        except (ValueError, SchemaError) as error:
            raise ValueError(f"Could not validate {parameter_path}: {error}") from error
        if errors:
            _check(checks, trace, raw=raw, check_id=f"contract-parameter-{location}-{name}", title=f"Parameter: {name}", passed=False, message=f"{location.title()} parameter {name!r}: {errors[0].message}", contract_path=parameter_path, position=position)
        else:
            _check(checks, trace, raw=raw, check_id=f"contract-parameter-{location}-{name}", title=f"Parameter: {name}", passed=True, message=f"{location.title()} parameter {name!r} matches its schema.", contract_path=parameter_path, position=position)

    request_body = operation.get("requestBody")
    body = str(parts["body"])
    body_start = int(parts["bodyStart"])
    content_type = headers.get("content-type", [("", 0)])[0][0].split(";", 1)[0].strip().lower()
    content_type_offset = header_value_offsets.get("content-type")
    if request_body is not None:
        request_body = _resolve_object(spec, request_body)
        request_body_path = f"paths.{operation_path}.{method}.requestBody"
        if request_body.get("required") and not body:
            _check(checks, trace, raw=raw, check_id="contract-request-body-required", title="Request body is required", passed=False, message="The operation requires a request body, but the message body is empty.", contract_path=request_body_path, position=body_start)
        content = request_body.get("content", {})
        selected_media = next((media for media in content if _media_type_matches(media, content_type)), None) if content_type else None
        if body and not selected_media:
            _check(checks, trace, raw=raw, check_id="contract-content-type", title="Request Content-Type is allowed", passed=False, message=f"Content-Type {content_type or '(missing)'} is not declared for this operation.", contract_path=request_body_path + ".content", position=content_type_offset or body_start)
        elif selected_media:
            _check(checks, trace, raw=raw, check_id="contract-content-type", title="Request Content-Type is allowed", passed=True, message=f"Content-Type {content_type} is declared for this operation.", contract_path=request_body_path + f".content.{selected_media}", position=content_type_offset)
            media_object = content[selected_media]
            schema = media_object.get("schema") if isinstance(media_object, dict) else None
            if body and schema is not None:
                is_json_media = content_type == "application/json" or content_type.endswith("+json") or selected_media.endswith("+json")
                if not is_json_media:
                    _check(checks, trace, raw=raw, check_id="contract-body-schema", title="Request body schema", passed=None, message="The declared body media type is allowed, but schema validation currently supports JSON media types only.", contract_path=request_body_path + f".content.{selected_media}.schema", position=body_start)
                else:
                    try:
                        instance = json.loads(body)
                    except json.JSONDecodeError as error:
                        _check(checks, trace, raw=raw, check_id="contract-body-json", title="Request body is valid JSON", passed=False, message=f"Invalid JSON body: {error.msg}.", contract_path=request_body_path, position=body_start + error.pos)
                    else:
                        _check(checks, trace, raw=raw, check_id="contract-body-json", title="Request body is valid JSON", passed=True, message="Request body parses as JSON.", contract_path=request_body_path, position=body_start)
                        schema_for_validation = _convert_oas30_schema(schema) if spec["openapi"].startswith("3.0.") else schema
                        try:
                            validator = _validator(spec, schema_for_validation)
                            errors = sorted(validator.iter_errors(instance), key=lambda error: (list(map(str, error.absolute_path)), error.message))[:_MAX_SCHEMA_ERRORS]
                        except (ValueError, SchemaError) as error:
                            raise ValueError(f"Could not validate request body schema: {error}") from error
                        for index, error in enumerate(errors):
                            json_path = "$" + "".join(f"[{part}]" if isinstance(part, int) else f".{part}" for part in error.absolute_path)
                            location = _json_path_offset(body, error.absolute_path)
                            _check(checks, trace, raw=raw, check_id=f"contract-body-schema-{index + 1}", title=f"Request body schema: {json_path}", passed=False, message=error.message, contract_path=request_body_path + ".content." + selected_media + ".schema" + json_path, position=body_start + location if location is not None else body_start)
                        if not errors:
                            _check(checks, trace, raw=raw, check_id="contract-body-schema", title="Request body matches schema", passed=True, message="JSON request body satisfies the operation schema.", contract_path=request_body_path + ".content." + selected_media + ".schema", position=body_start)
    elif body:
        _check(checks, trace, raw=raw, check_id="contract-request-body-unspecified", title="Request body declaration", passed=None, message="This operation does not declare a request body; the supplied body was not schema-validated.", contract_path=f"paths.{operation_path}.{method}.requestBody", position=body_start)

    report["checks"].extend(checks)
    if any(item["status"] == "fail" for item in checks):
        report["overall"] = "INVALID"
    report["contract"] = {"title": spec["info"].get("title", "OpenAPI contract"), "version": spec["info"].get("version", ""), "openapi": spec["openapi"], "path": operation_path, "method": method.upper(), "checks": checks}
    report["trace"].extend(step.model_dump(mode="json") for step in trace)
    return report


def _media_type_matches(pattern: str, actual: str) -> bool:
    normalized = pattern.lower().split(";", 1)[0].strip()
    if normalized == actual:
        return True
    if normalized == "*/*":
        return bool(actual)
    if normalized.endswith("/*"):
        return actual.startswith(normalized[:-1])
    if normalized.endswith("/*+json"):
        prefix = normalized[:-6]
        return actual.startswith(prefix) and actual.endswith("+json")
    return False


def _json_path_offset(body: str, path: Any) -> int | None:
    if not path:
        return 0
    property_name = path[-1]
    if isinstance(property_name, str):
        for token in (json.dumps(property_name), json.dumps(property_name) + " "):
            found = body.find(token)
            if found >= 0:
                return found + (0 if token.endswith(" ") else len(token) - len(property_name) - 2)
    return None


__all__ = ["validate_openapi_contract"]
