# Calculator API Contract

Initial application version: `1.0.0`.

This document defines the public behavior used for tests and future semantic version decisions. Local examples use `http://127.0.0.1:5001`.

## Endpoints

All endpoints accept `GET`. Successful responses return HTTP `200`. The entrypoint is HTML; operation endpoints return JSON by default. No authentication or request body is required. JSON field order is not significant.

| Endpoint | Required fields | Meaning |
|---|---|---|
| `/` | HTML calculator form | Entry page with two inputs and four operation buttons |
| `/add?a=8&b=2` | `operation`, `a`, `b`, `result` | A + B; example result `10.0` |
| `/subtract?a=8&b=2` | `operation`, `a`, `b`, `result` | A - B; example result `6.0` |
| `/multiply?a=8&b=2` | `operation`, `a`, `b`, `result` | A × B; example result `16.0` |
| `/divide?a=8&b=2` | `operation`, `a`, `b`, `result` | A ÷ B; example result `4.0` |
| `/health` | `status`: string with value `ok` | Confirms that the application can serve a request |
| `/version` | `version`: string; `commit`: string | Identifies the version and supplied source commit |

## Arithmetic requests and responses

Supply exactly one `a` and one `b` query parameter. Both must parse as finite numbers. Negative numbers, zero, decimals, and scientific notation are supported. Subtraction and division preserve operand order. Calculations use Python floating-point arithmetic, so decimal results may be approximate.

Operation responses use `application/json`: `operation` is the endpoint name as a string, and `a`, `b`, and `result` are JSON numbers. For example, `/add?a=8&b=2` returns:

```json
{"operation": "add", "a": 8.0, "b": 2.0, "result": 10.0}
```

Invalid requests return HTTP `400` with an `error` string and no result. This includes missing, duplicate, blank, or nonnumeric operands; non-finite inputs such as `NaN` or infinity; division by zero (including negative zero); and results outside the finite floating-point range. For example, `/divide?a=8&b=0` returns:

```json
{"error": "Cannot divide by zero."}
```

## HTML interface

`/` returns `text/html` with a single form, labeled inputs A and B, and four submit buttons. The form uses standard GET submission and needs no JavaScript or CSS. Each button submits to its corresponding operation endpoint with a hidden `format=html` parameter.

When `format=html` is present, an operation returns the calculator page with the result (HTTP `200`) or validation message (HTTP `400`). The inputs remain populated. Other requests use JSON. The initial page and error pages do not show a result; a successful zero result is displayed normally.

This replaces the prototype's JSON welcome response at `/` while preparing the initial application. If that earlier contract has already been released, replacing its response format is a breaking change and requires a major release under the project's policy.

## Health and version

`/health` and `/version` continue to return `application/json` without query parameters:

```json
{"status": "ok"}
```

```json
{"version": "1.0.0", "commit": "unknown"}
```

## Release identity

- `version` is read from the repository's `VERSION` file at application startup.
- `commit` is read from the `APP_COMMIT` environment variable at startup. Local development returns `unknown` when it is missing or blank.
- For a verified demonstration, commit the source and supply the full output of `git rev-parse HEAD` as `APP_COMMIT` before starting the server.
- The application reports the supplied value; it does not inspect Git or detect uncommitted changes. Commit changes and restart with the updated value when demonstrating another revision.
- Restart the server after changing either release value. A missing or empty `VERSION` file prevents startup.
- Docker builds copy `VERSION` into the image and store the `APP_COMMIT` build argument as its default environment value. Rebuild the image after changing packaged source or metadata. The demonstration runs the image without overriding that value or mounting local source over it.
- `/health` is a basic application liveness check. Release verification also checks `/version` against the expected identity.

## Compatibility rules

- Preserve supported endpoint paths, required response fields, field types, and documented behavior in compatible releases.
- Clients should ignore additional response fields. Adding an optional field or a new endpoint can be a minor change if existing behavior stays compatible.
- Correcting an implementation defect to match this contract can be a patch change.
- Removing an endpoint, removing or renaming a required field, changing its type, or incompatibly changing documented behavior requires a major change.
- Version and commit values naturally change between releases; changing those values is not itself a breaking API change.

Unknown paths return HTTP `404`; unsupported methods such as `POST` on these endpoints return HTTP `405`. The bodies of these routing errors are not part of this contract. Operation validation errors follow the HTTP `400` behavior described above. Flask also supplies standard `HEAD` and `OPTIONS` handling.

Automated tests are in `tests/test_api.py` and `tests/test_calculator.py`. They cover the entry form, arithmetic examples, invalid input, HTML results and errors, and release metadata. `scripts/smoke_test.py` checks the packaged UI, all four operations, division-by-zero handling, health, and expected version and commit. Execution is pending user verification. Declared change-type validation is planned for Sprint 4.
