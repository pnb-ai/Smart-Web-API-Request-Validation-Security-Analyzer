"""Definitions and expansion rules for readable automata alphabet classes."""

from string import ascii_letters, digits, hexdigits, printable

EPSILON = "ε"

# Classes are finite sets of input tokens. CRLF is one token consuming two
# code points, which keeps HTTP grammar edges readable in diagrams.
SYMBOL_CLASSES: dict[str, frozenset[str]] = {
    # Regex Lab's dot and negated classes use a clear finite ASCII universe.
    "ANY": frozenset(chr(code) for code in range(128)),
    "DOT": frozenset(chr(code) for code in range(128) if code != 10),
    "DIGIT": frozenset(digits),
    "ALPHA": frozenset(ascii_letters),
    "HEXDIG": frozenset(hexdigits),
    "TCHAR": frozenset("!#$%&'*+-.^_`|~0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"),
    "SP": frozenset({" "}),
    "CRLF": frozenset({"\r\n"}),
    "VCHAR": frozenset(ch for ch in printable if 0x21 <= ord(ch) <= 0x7E),
}


def expand_symbol(symbol: str) -> frozenset[str]:
    """Expand a named class; ordinary symbols represent themselves."""
    if symbol == EPSILON:
        return frozenset()
    return SYMBOL_CLASSES.get(symbol, frozenset({symbol}))


def expand_symbols(symbols: list[str] | tuple[str, ...] | set[str]) -> frozenset[str]:
    """Expand labels into concrete input tokens, ignoring ε transitions."""
    return frozenset(token for symbol in symbols for token in expand_symbol(symbol))


def tokenize_input(value: str, alphabet: list[str]) -> list[str]:
    """Split input using declared multi-codepoint symbols, then code points.

    This makes CRLF one simulation step while leaving a stream of class
    members such as ``123`` as three ordinary DIGIT inputs.
    """
    multi_tokens = sorted(
        (token for token in expand_symbols(alphabet) if len(token) > 1),
        key=lambda token: (-len(token), token),
    )
    result: list[str] = []
    offset = 0
    while offset < len(value):
        match = next((token for token in multi_tokens if value.startswith(token, offset)), None)
        if match is None:
            result.append(value[offset])
            offset += 1
        else:
            result.append(match)
            offset += len(match)
    return result


def display_symbol(symbol: str) -> str:
    """Use a concise visible spelling in traces and rejection reasons."""
    return "CRLF" if symbol == "\r\n" else symbol
