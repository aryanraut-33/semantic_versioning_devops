# Flask API Contract

Initial application version: `1.0.0`.

This document defines the public behavior used for tests and future semantic version decisions. Local examples use `http://127.0.0.1:5001`.

## Endpoints

All three endpoints accept `GET`, return HTTP `200` on success, and respond with a JSON object using the `application/json` content type. They need no authentication, query parameters, or request body. JSON field order is not significant.

| Endpoint | Required fields | Meaning |
|---|---|---|
| `/` | `message`: string with value `Release Governance API` | Identifies the application |
| `/health` | `status`: string with value `ok` | Confirms that the application can serve a request |
| `/version` | `version`: string; `commit`: string | Identifies the version and supplied source commit |

Example responses:

```json
{"message": "Release Governance API"}
```

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
- `/health` is a basic application liveness check. Release verification also checks `/version` against the expected identity.

## Compatibility rules

- Preserve supported endpoint paths, required response fields, field types, and documented behavior in compatible releases.
- Clients should ignore additional response fields. Adding an optional field or a new endpoint can be a minor change if existing behavior stays compatible.
- Correcting an implementation defect to match this contract can be a patch change.
- Removing an endpoint, removing or renaming a required field, changing its type, or incompatibly changing documented behavior requires a major change.
- Version and commit values naturally change between releases; changing those values is not itself a breaking API change.

Unknown paths return HTTP `404`; unsupported methods such as `POST` on these endpoints return HTTP `405`. Error response bodies are not part of this initial contract. Flask also supplies standard `HEAD` and `OPTIONS` handling.

Automated contract tests are planned for Sprint 2. Declared change-type validation is planned for Sprint 4.
