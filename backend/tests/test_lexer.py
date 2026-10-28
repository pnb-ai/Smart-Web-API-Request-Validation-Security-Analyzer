from fastapi.testclient import TestClient

from app.main import app
from app.automata.lexer import tokenize_request


client = TestClient(app)


def test_tokenize_request_line_and_headers_with_maximal_munch():
    result = tokenize_request("GET /api/users?id=42 HTTP/1.1\r\nHost: example.com\r\n")
    assert [token["type"] for token in result["tokens"]] == [
        "METHOD", "WHITESPACE", "PATH", "OPERATORS", "QUERY_KEY", "OPERATORS", "QUERY_VALUE",
        "WHITESPACE", "HTTP_VERSION", "CRLF", "HEADER_NAME", "OPERATORS",
        "WHITESPACE", "IDENTIFIER", "CRLF",
    ]
    assert result["tokens"][0]["dfaPath"][0] == "d0"
    assert result["automaton"]["type"] == "DFA"
    assert all(step["title"] for step in result["trace"])


def test_lexer_reports_positions_and_recovers_after_illegal_characters():
    result = tokenize_request("GET /bad path@\r\n")
    errors = [token for token in result["tokens"] if token["type"] == "ERROR"]
    assert [(token["value"], token["line"], token["column"]) for token in errors] == [(" ", 1, 9), ("@", 1, 14)]
    assert errors[0]["error"].startswith("Space in path")
    assert any(token["type"] == "CRLF" for token in result["tokens"])
    assert errors[0]["error"]


def test_tokenize_endpoint_returns_machine_and_trace():
    response = client.post("/api/lexer/tokenize", json={"text": "POST /v1 HTTP/1.0\r\n"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["tokens"][0]["type"] == "METHOD"
    assert payload["automaton"]["type"] == "DFA"
    assert payload["trace"]


def test_unterminated_crlf_is_reported_and_scanning_continues():
    result = tokenize_request("GET\rX")
    error = next(token for token in result["tokens"] if token["type"] == "ERROR")
    assert (error["value"], error["line"], error["column"]) == ("\r", 1, 4)
    assert error["error"].startswith("Unterminated CRLF")
    assert result["tokens"][-1]["value"] == "X"
