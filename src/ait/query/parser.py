from __future__ import annotations

import re

from ait.query.models import (
    BinaryExpression,
    Comparison,
    Expression,
    QueryError,
    UnaryExpression,
)


TOKEN_RE = re.compile(
    r"""
    (?P<SPACE>\s+)
    |(?P<STRING>"(?:[^"\\]|\\.)*")
    |(?P<OP><=|>=|!=|=|<|>|~)
    |(?P<LPAREN>\()
    |(?P<RPAREN>\))
    |(?P<COMMA>,)
    |(?P<NUMBER>-?\d+)
    |(?P<IDENT>[A-Za-z_][A-Za-z0-9._]*)
    """,
    re.VERBOSE,
)


KEYWORDS = {"AND", "OR", "NOT", "IN", "TRUE", "FALSE", "NULL"}


def parse_query(expression: str) -> Expression:
    parser = _Parser(expression)
    return parser.parse()


class _Parser:
    def __init__(self, expression: str) -> None:
        self._tokens = list(_tokenize(expression))
        self._index = 0

    def parse(self) -> Expression:
        if not self._tokens:
            raise QueryError("query expression must not be empty")
        expression = self._parse_or()
        if self._peek() is not None:
            raise QueryError(f"unexpected token: {self._peek()!r}")
        return expression

    def _parse_or(self) -> Expression:
        left = self._parse_and()
        while self._match_keyword("OR"):
            left = BinaryExpression("OR", left, self._parse_and())
        return left

    def _parse_and(self) -> Expression:
        left = self._parse_not()
        while self._match_keyword("AND"):
            left = BinaryExpression("AND", left, self._parse_not())
        return left

    def _parse_not(self) -> Expression:
        if self._match_keyword("NOT"):
            return UnaryExpression("NOT", self._parse_not())
        return self._parse_primary()

    def _parse_primary(self) -> Expression:
        if self._match("LPAREN"):
            expression = self._parse_or()
            self._expect("RPAREN")
            return expression

        field = self._expect("IDENT")
        if self._match_keyword("IN"):
            self._expect("LPAREN")
            values = [self._parse_literal()]
            while self._match("COMMA"):
                values.append(self._parse_literal())
            self._expect("RPAREN")
            return Comparison(field, "IN", tuple(values))

        operator = self._expect("OP")
        value = self._parse_literal()
        return Comparison(field, operator, value)

    def _parse_literal(self) -> object:
        token = self._peek()
        if token is None:
            raise QueryError("expected literal")
        token_type, token_value = token
        self._index += 1

        if token_type == "STRING":
            return _decode_string_literal(token_value[1:-1])
        if token_type == "NUMBER":
            return int(token_value)
        if token_type == "IDENT":
            upper = token_value.upper()
            if upper == "TRUE":
                return True
            if upper == "FALSE":
                return False
            if upper == "NULL":
                return None
        raise QueryError(f"expected literal, got {token_value!r}")

    def _expect(self, token_type: str) -> str:
        token = self._peek()
        if token is None or token[0] != token_type:
            raise QueryError(f"expected {token_type}")
        self._index += 1
        return token[1]

    def _match(self, token_type: str) -> bool:
        token = self._peek()
        if token is None or token[0] != token_type:
            return False
        self._index += 1
        return True

    def _match_keyword(self, keyword: str) -> bool:
        token = self._peek()
        if token is None or token[0] != "IDENT" or token[1].upper() != keyword:
            return False
        self._index += 1
        return True

    def _peek(self) -> tuple[str, str] | None:
        if self._index >= len(self._tokens):
            return None
        return self._tokens[self._index]


def _decode_string_literal(value: str) -> str:
    result: list[str] = []
    index = 0
    while index < len(value):
        char = value[index]
        if char != "\\":
            result.append(char)
            index += 1
            continue
        index += 1
        if index >= len(value):
            result.append("\\")
            break
        escaped = value[index]
        index += 1
        if escaped == "n":
            result.append("\n")
        elif escaped == "t":
            result.append("\t")
        elif escaped in {'"', "\\"}:
            result.append(escaped)
        elif escaped == "x" and index + 2 <= len(value):
            hex_value = value[index : index + 2]
            if re.fullmatch(r"[0-9A-Fa-f]{2}", hex_value):
                result.append(chr(int(hex_value, 16)))
                index += 2
            else:
                result.append("\\x")
        else:
            result.append("\\" + escaped)
    return "".join(result)


def _tokenize(expression: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    position = 0
    while position < len(expression):
        match = TOKEN_RE.match(expression, position)
        if match is None:
            raise QueryError(f"unexpected character at position {position}: {expression[position]!r}")
        position = match.end()
        token_type = match.lastgroup
        assert token_type is not None
        if token_type == "SPACE":
            continue
        token_value = match.group(token_type)
        if token_type == "IDENT" and token_value.upper() in KEYWORDS:
            tokens.append(("IDENT", token_value.upper()))
        else:
            tokens.append((token_type, token_value))
    return tokens
