import re


class UnsafeQueryError(ValueError):
    pass


_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|TRUNCATE|ATTACH|DETACH|VACUUM|REINDEX)\b",
    re.IGNORECASE,
)


def validate_read_only_sql(sql: str) -> str:
    candidate = sql.strip()
    if not candidate:
        raise UnsafeQueryError("SQL cannot be empty")

    without_trailing_semicolon = candidate[:-1].rstrip() if candidate.endswith(";") else candidate
    if ";" in without_trailing_semicolon:
        raise UnsafeQueryError("Only one SQL statement is allowed")

    if _FORBIDDEN.search(without_trailing_semicolon):
        raise UnsafeQueryError("Only read-only SQL is allowed")

    normalized = without_trailing_semicolon.lstrip().upper()
    if not (normalized.startswith("SELECT") or normalized.startswith("WITH")):
        raise UnsafeQueryError("Query must start with SELECT or WITH")

    return without_trailing_semicolon
