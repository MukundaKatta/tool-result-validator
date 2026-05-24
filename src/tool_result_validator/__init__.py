"""
tool_result_validator
~~~~~~~~~~~~~~~~~~~~~
Validate tool call results against registered JSON-Schema-style schemas
before handing them back to the LLM. Catches bad data early. Zero runtime deps.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ToolResultError(Exception):
    """Raised when a tool result fails schema validation (strict mode)."""

    def __init__(self, tool_name: str, errors: list[str]) -> None:
        self.tool_name = tool_name
        self.errors = errors
        super().__init__(
            f"Tool '{tool_name}' result validation failed: {'; '.join(errors)}"
        )


# ---------------------------------------------------------------------------
# ValidationResult
# ---------------------------------------------------------------------------


class ValidationResult:
    """Holds the outcome of a single validation run."""

    def __init__(self, ok: bool, errors: list[str], result: Any) -> None:
        self.ok = ok
        self.errors = errors
        self.result = result

    def __repr__(self) -> str:  # pragma: no cover
        return f"ValidationResult(ok={self.ok}, errors={self.errors!r})"


# ---------------------------------------------------------------------------
# Hand-rolled schema checker
# ---------------------------------------------------------------------------

_PYTHON_TYPE_MAP: dict[str, type | tuple[type, ...]] = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "null": type(None),
    "object": dict,
    "array": list,
}


def _check(schema: dict, value: Any, path: str, errors: list[str]) -> None:
    """Recursively validate *value* against *schema*, appending to *errors*."""

    # ---- type check -------------------------------------------------------
    type_name: str | None = schema.get("type")
    if type_name is not None:
        expected = _PYTHON_TYPE_MAP.get(type_name)
        if expected is None:
            # Unknown type keyword — ignore (permissive).
            pass
        elif type_name == "integer":
            # JSON Schema: integer must not be a bool (bool is subclass of int)
            if not isinstance(value, int) or isinstance(value, bool):
                errors.append(
                    f"{path}: expected integer, got {type(value).__name__}"
                )
                return  # stop: sub-checks won't make sense on wrong type
        elif type_name == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                errors.append(
                    f"{path}: expected number, got {type(value).__name__}"
                )
                return
        elif not isinstance(value, expected):  # type: ignore[arg-type]
            errors.append(
                f"{path}: expected {type_name}, got {type(value).__name__}"
            )
            return  # stop: sub-checks won't make sense on wrong type

    # ---- object-specific checks -------------------------------------------
    if isinstance(value, dict):
        # required
        required: list[str] = schema.get("required", [])
        for key in required:
            if key not in value:
                errors.append(f"{path}: missing required field '{key}'")

        # properties (recursive)
        properties: dict[str, dict] = schema.get("properties", {})
        for field, sub_schema in properties.items():
            if field in value:
                _check(sub_schema, value[field], f"{path}.{field}", errors)

    # ---- array-specific checks --------------------------------------------
    elif isinstance(value, list):
        items_schema: dict | None = schema.get("items")
        if items_schema is not None:
            for idx, item in enumerate(value):
                _check(items_schema, item, f"{path}[{idx}]", errors)


# ---------------------------------------------------------------------------
# ToolResultValidator
# ---------------------------------------------------------------------------


class ToolResultValidator:
    """
    Registry that maps tool names to JSON-Schema-style schemas and validates
    tool results against them before they reach the LLM.

    Parameters
    ----------
    strict:
        If ``True`` (default), :meth:`validate` raises :class:`ToolResultError`
        when validation fails.  If ``False``, it returns a
        :class:`ValidationResult` with ``ok=False`` instead.
    """

    def __init__(self, strict: bool = True) -> None:
        self._strict = strict
        self._schemas: dict[str, dict] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, tool_name: str, schema: dict) -> None:
        """Register a JSON-Schema-style *schema* for *tool_name*.

        Supported keywords: ``type``, ``properties``, ``required``, ``items``.
        Unknown keywords are silently ignored (permissive).
        """
        self._schemas[tool_name] = schema

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self, tool_name: str, result: Any) -> ValidationResult:
        """Validate *result* against the schema registered for *tool_name*.

        - If *tool_name* has no registered schema, always returns a passing
          :class:`ValidationResult`.
        - In strict mode, raises :class:`ToolResultError` on failure.
        - In non-strict mode, returns a :class:`ValidationResult` with
          ``ok=False`` and a populated ``errors`` list.
        """
        schema = self._schemas.get(tool_name)
        if schema is None:
            # No schema registered — pass through unconditionally.
            return ValidationResult(ok=True, errors=[], result=result)

        errors: list[str] = []
        _check(schema, result, tool_name, errors)

        if errors:
            if self._strict:
                raise ToolResultError(tool_name, errors)
            return ValidationResult(ok=False, errors=errors, result=result)

        return ValidationResult(ok=True, errors=[], result=result)

    # ------------------------------------------------------------------
    # Decorators
    # ------------------------------------------------------------------

    def validated(self, tool_name: str) -> Callable:
        """Decorator that validates the return value of a sync function.

        Usage::

            @validator.validated("search_web")
            def search_web(query: str) -> dict:
                ...
        """

        def decorator(fn: Callable) -> Callable:
            @functools.wraps(fn)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                result = fn(*args, **kwargs)
                self.validate(tool_name, result)
                return result

            return wrapper

        return decorator

    def validated_async(self, tool_name: str) -> Callable:
        """Decorator that validates the return value of an async function.

        Usage::

            @validator.validated_async("search_web")
            async def search_web(query: str) -> dict:
                ...
        """

        def decorator(fn: Callable) -> Callable:
            @functools.wraps(fn)
            async def wrapper(*args: Any, **kwargs: Any) -> Any:
                result = await fn(*args, **kwargs)
                self.validate(tool_name, result)
                return result

            return wrapper

        return decorator

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def schemas(self) -> dict:
        """Return a shallow copy of the registered schemas dict."""
        return dict(self._schemas)


__all__ = [
    "ToolResultError",
    "ValidationResult",
    "ToolResultValidator",
]
