# tool-result-validator

[![PyPI](https://img.shields.io/pypi/v/tool-result-validator.svg)](https://pypi.org/project/tool-result-validator/)
[![Python](https://img.shields.io/pypi/pyversions/tool-result-validator.svg)](https://pypi.org/project/tool-result-validator/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**Validate tool-call results against registered JSON-Schema-style schemas before
handing them back to the LLM.**

When an LLM agent calls a tool, the tool's return value is fed straight back
into the model. If that value is malformed — a missing field, a string where an
integer was expected, a `null` where an object should be — the model often
hallucinates around the bad data instead of failing loudly. This library catches
those problems at the boundary, with a tiny hand-rolled checker and **zero
runtime dependencies**.

## Install

```bash
pip install tool-result-validator
```

## Use

Register a schema per tool, then validate results before returning them:

```python
from tool_result_validator import ToolResultValidator, ToolResultError

validator = ToolResultValidator()  # strict=True by default

validator.register("get_user", {
    "type": "object",
    "required": ["id", "name"],
    "properties": {
        "id": {"type": "integer"},
        "name": {"type": "string"},
    },
})

# In strict mode, a bad result raises ToolResultError:
try:
    validator.validate("get_user", {"id": "oops"})  # id wrong type, name missing
except ToolResultError as e:
    print(e.tool_name)  # "get_user"
    print(e.errors)     # ['get_user.id: expected integer, got str', "get_user: missing required field 'name'"]
```

Tools with **no registered schema always pass** — registration is opt-in, so you
can adopt the validator incrementally.

### Non-strict mode

Pass `strict=False` to get a `ValidationResult` back instead of an exception:

```python
validator = ToolResultValidator(strict=False)
validator.register("search", {"type": "array", "items": {"type": "string"}})

result = validator.validate("search", ["alpha", 42, "gamma"])
result.ok       # False
result.errors   # ['search[1]: expected string, got int']
result.result   # the original value, unchanged
```

### Decorators

Wrap a tool function so its return value is validated automatically:

```python
@validator.validated("get_user")
def get_user(uid: int) -> dict:
    return fetch_from_db(uid)

@validator.validated_async("get_user")
async def get_user_async(uid: int) -> dict:
    return await fetch_from_db(uid)
```

In strict mode, a bad return value raises `ToolResultError`. In either mode the
original return value is passed through unchanged.

## Supported schema keywords

A deliberately small subset of JSON Schema:

| Keyword       | Applies to | Behaviour                                              |
| ------------- | ---------- | ----------------------------------------------------- |
| `type`        | any        | `string`, `integer`, `number`, `boolean`, `null`, `object`, `array` |
| `properties`  | `object`   | Recursively validates each named field that is present |
| `required`    | `object`   | Each listed key must be present                        |
| `items`       | `array`    | Recursively validates every element                    |

Notes:

- **Booleans are not integers/numbers.** Following JSON Schema, `True` fails a
  `{"type": "integer"}` or `{"type": "number"}` check even though `bool` is a
  Python subclass of `int`.
- **`number` accepts both `int` and `float`**; `integer` accepts only `int`.
- **Unknown keywords are ignored** (permissive), so a schema with extra keys
  won't raise — only the supported keywords are enforced.

## Introspection

```python
validator.schemas()  # shallow copy of {tool_name: schema}; safe to mutate
```

## What it does NOT do

- No full JSON Schema. No `enum`, `pattern`, `minimum`, `additionalProperties`,
  `$ref`, etc. — just the keywords above.
- No network or LLM calls. It only inspects values you pass it.
- No coercion. It validates; it never rewrites your data.

## License

MIT
