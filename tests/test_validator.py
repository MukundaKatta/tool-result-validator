"""Tests for tool_result_validator."""

from __future__ import annotations

import asyncio

import pytest

from tool_result_validator import (
    ToolResultError,
    ToolResultValidator,
    ValidationResult,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

OBJECT_SCHEMA = {
    "type": "object",
    "required": ["id", "name"],
    "properties": {
        "id": {"type": "integer"},
        "name": {"type": "string"},
    },
}

ARRAY_SCHEMA = {
    "type": "array",
    "items": {"type": "string"},
}


def make_validator(strict: bool = True) -> ToolResultValidator:
    v = ToolResultValidator(strict=strict)
    v.register("my_tool", OBJECT_SCHEMA)
    return v


# ---------------------------------------------------------------------------
# 1. Unregistered tool always passes
# ---------------------------------------------------------------------------


def test_unregistered_tool_passes():
    v = ToolResultValidator()
    r = v.validate("unknown_tool", {"anything": True})
    assert r.ok is True
    assert r.errors == []
    assert r.result == {"anything": True}


def test_unregistered_tool_passes_with_bad_value():
    v = ToolResultValidator()
    r = v.validate("ghost", "not even a dict")
    assert r.ok is True


# ---------------------------------------------------------------------------
# 2. type: "object"
# ---------------------------------------------------------------------------


def test_object_type_pass():
    v = make_validator()
    r = v.validate("my_tool", {"id": 1, "name": "Alice"})
    assert r.ok is True


def test_object_type_fail_wrong_type():
    v = make_validator(strict=False)
    r = v.validate("my_tool", ["not", "a", "dict"])
    assert r.ok is False
    assert any("object" in e for e in r.errors)


# ---------------------------------------------------------------------------
# 3. type: "array"
# ---------------------------------------------------------------------------


def test_array_type_pass():
    v = ToolResultValidator()
    v.register("arr_tool", ARRAY_SCHEMA)
    r = v.validate("arr_tool", ["hello", "world"])
    assert r.ok is True


def test_array_type_fail():
    v = ToolResultValidator(strict=False)
    v.register("arr_tool", ARRAY_SCHEMA)
    r = v.validate("arr_tool", {"not": "a list"})
    assert r.ok is False
    assert any("array" in e for e in r.errors)


# ---------------------------------------------------------------------------
# 4. Scalar types
# ---------------------------------------------------------------------------


def test_type_string_pass():
    v = ToolResultValidator()
    v.register("t", {"type": "string"})
    assert v.validate("t", "hello").ok is True


def test_type_string_fail():
    v = ToolResultValidator(strict=False)
    v.register("t", {"type": "string"})
    r = v.validate("t", 42)
    assert r.ok is False


def test_type_integer_pass():
    v = ToolResultValidator()
    v.register("t", {"type": "integer"})
    assert v.validate("t", 7).ok is True


def test_type_integer_rejects_bool():
    # JSON Schema: booleans are not integers
    v = ToolResultValidator(strict=False)
    v.register("t", {"type": "integer"})
    r = v.validate("t", True)
    assert r.ok is False


def test_type_boolean_pass():
    v = ToolResultValidator()
    v.register("t", {"type": "boolean"})
    assert v.validate("t", False).ok is True


def test_type_null_pass():
    v = ToolResultValidator()
    v.register("t", {"type": "null"})
    assert v.validate("t", None).ok is True


def test_type_null_fail():
    v = ToolResultValidator(strict=False)
    v.register("t", {"type": "null"})
    r = v.validate("t", 0)
    assert r.ok is False


# ---------------------------------------------------------------------------
# 5. required fields
# ---------------------------------------------------------------------------


def test_required_fields_present():
    v = make_validator()
    r = v.validate("my_tool", {"id": 1, "name": "Bob"})
    assert r.ok is True


def test_required_field_missing():
    v = make_validator(strict=False)
    r = v.validate("my_tool", {"id": 1})  # missing "name"
    assert r.ok is False
    assert any("name" in e for e in r.errors)


def test_both_required_fields_missing():
    v = make_validator(strict=False)
    r = v.validate("my_tool", {})
    assert r.ok is False
    # Both "id" and "name" errors should be present
    combined = " ".join(r.errors)
    assert "id" in combined and "name" in combined


# ---------------------------------------------------------------------------
# 6. properties recursive check
# ---------------------------------------------------------------------------


def test_properties_field_wrong_type():
    v = make_validator(strict=False)
    r = v.validate("my_tool", {"id": "not-an-int", "name": "Alice"})
    assert r.ok is False
    assert any("id" in e for e in r.errors)


def test_properties_nested_pass():
    v = ToolResultValidator()
    v.register("nested", {
        "type": "object",
        "properties": {
            "meta": {
                "type": "object",
                "required": ["created"],
                "properties": {"created": {"type": "string"}},
            }
        },
    })
    r = v.validate("nested", {"meta": {"created": "2024-01-01"}})
    assert r.ok is True


def test_properties_nested_fail():
    v = ToolResultValidator(strict=False)
    v.register("nested", {
        "type": "object",
        "properties": {
            "meta": {
                "type": "object",
                "required": ["created"],
            }
        },
    })
    r = v.validate("nested", {"meta": {}})  # missing "created"
    assert r.ok is False
    assert any("created" in e for e in r.errors)


# ---------------------------------------------------------------------------
# 7. items check for array
# ---------------------------------------------------------------------------


def test_items_all_pass():
    v = ToolResultValidator()
    v.register("t", {"type": "array", "items": {"type": "integer"}})
    assert v.validate("t", [1, 2, 3]).ok is True


def test_items_one_wrong_type():
    v = ToolResultValidator(strict=False)
    v.register("t", {"type": "array", "items": {"type": "integer"}})
    r = v.validate("t", [1, "oops", 3])
    assert r.ok is False
    assert any("[1]" in e for e in r.errors)


# ---------------------------------------------------------------------------
# 8. strict=True raises ToolResultError
# ---------------------------------------------------------------------------


def test_strict_raises_tool_result_error():
    v = make_validator(strict=True)
    with pytest.raises(ToolResultError) as exc_info:
        v.validate("my_tool", "wrong type entirely")
    err = exc_info.value
    assert err.tool_name == "my_tool"
    assert len(err.errors) > 0


def test_strict_error_message_contains_tool_name():
    v = make_validator(strict=True)
    with pytest.raises(ToolResultError) as exc_info:
        v.validate("my_tool", {})
    assert "my_tool" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 9. strict=False returns ValidationResult without raising
# ---------------------------------------------------------------------------


def test_non_strict_no_raise():
    v = make_validator(strict=False)
    r = v.validate("my_tool", "bad")
    assert isinstance(r, ValidationResult)
    assert r.ok is False


def test_non_strict_errors_populated():
    v = make_validator(strict=False)
    r = v.validate("my_tool", {})
    assert len(r.errors) >= 2  # id and name both missing


# ---------------------------------------------------------------------------
# 10. validated() decorator
# ---------------------------------------------------------------------------


def test_validated_decorator_pass():
    v = ToolResultValidator()
    v.register("add", {"type": "integer"})

    @v.validated("add")
    def add(a, b):
        return a + b

    assert add(2, 3) == 5


def test_validated_decorator_raises_on_bad_result():
    v = ToolResultValidator(strict=True)
    v.register("add", {"type": "integer"})

    @v.validated("add")
    def add(a, b):
        return str(a + b)  # wrong: returns string

    with pytest.raises(ToolResultError):
        add(1, 2)


# ---------------------------------------------------------------------------
# 11. validated_async() decorator
# ---------------------------------------------------------------------------


def test_validated_async_decorator_pass():
    v = ToolResultValidator()
    v.register("fetch", {"type": "object", "required": ["url"]})

    @v.validated_async("fetch")
    async def fetch(url):
        return {"url": url, "status": 200}

    result = asyncio.run(fetch("https://example.com"))
    assert result["status"] == 200


def test_validated_async_decorator_raises_on_bad_result():
    v = ToolResultValidator(strict=True)
    v.register("fetch", {"type": "object"})

    @v.validated_async("fetch")
    async def fetch(url):
        return "not a dict"

    with pytest.raises(ToolResultError):
        asyncio.run(fetch("https://example.com"))


# ---------------------------------------------------------------------------
# 12. schemas() returns copy
# ---------------------------------------------------------------------------


def test_schemas_returns_copy():
    v = make_validator()
    copy1 = v.schemas()
    copy1["injected"] = {}
    assert "injected" not in v.schemas()


def test_schemas_reflects_registrations():
    v = ToolResultValidator()
    v.register("a", {"type": "string"})
    v.register("b", {"type": "integer"})
    s = v.schemas()
    assert set(s.keys()) == {"a", "b"}


# ---------------------------------------------------------------------------
# 13. Multiple registered tools are independent
# ---------------------------------------------------------------------------


def test_multiple_tools_independent():
    v = ToolResultValidator(strict=False)
    v.register("tool_a", {"type": "string"})
    v.register("tool_b", {"type": "integer"})

    ra = v.validate("tool_a", "ok")
    rb = v.validate("tool_b", 42)
    assert ra.ok is True
    assert rb.ok is True

    bad_a = v.validate("tool_a", 99)
    good_b = v.validate("tool_b", 7)
    assert bad_a.ok is False
    assert good_b.ok is True
