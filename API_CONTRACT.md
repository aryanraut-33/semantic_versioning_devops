# Fitness API Contract — 2.0.0

Local container URL: `http://127.0.0.1:5005`. Release deployment: `http://127.0.0.1:5004`. In development Vite serves pages on 5173 and Flask serves APIs on 5001. JSON field order is not significant. No authentication is required for calculator endpoints. Release authorization is a separate pipeline concern.

## Routes

| Method | Path | Response / purpose |
|---|---|---|
| GET | `/` | HTML shell for the React fitness calculator |
| GET | `/assets/<filename>` | Built JavaScript/CSS assets; missing assets return 404 |
| GET | `/api/activities` | Supported activity IDs, labels, and multipliers |
| POST | `/api/fitness` | Combined calorie and BMI results |
| POST | `/api/calories` | Calorie results without BMI |
| POST | `/api/bmi` | BMI results without calories |
| GET | `/health` | `{"status":"ok"}` |
| GET | `/frontend-version.json` | Frontend image version and commit, generated at build time |
| GET | `/version` | `{"version":"2.0.0","commit":"unknown"}` in an unconfigured local run |

Successful requests return HTTP 200. Nginx serves the built frontend; Flask no longer serves HTML or assets. Direct requests to Flask page paths return 404. Unknown routes return 404; unsupported methods return 405. Flask supplies standard HEAD handling for GET routes and OPTIONS handling.

## Fitness request schema

Send `Content-Type: application/json` and one JSON object. Requests are limited to 16 KiB. Numeric fields must be actual finite JSON numbers, not strings, booleans, NaN, or infinity. No extra fields are accepted.

| Field | Type / allowed values | Required by |
|---|---|---|
| `units` | String: `metric` or `us` | All fitness POST routes |
| `age` | Whole-number age, 20–100 inclusive | All fitness POST routes |
| `weight` | Number: kg for metric; lb for US | All fitness POST routes |
| `height` | Number: cm for metric; **total inches** for US | All fitness POST routes |
| `sex` | String: `male` or `female`, selecting the equation coefficient | `/api/fitness`, `/api/calories` |
| `activity` | String: one of the IDs below | `/api/fitness`, `/api/calories` |

After conversion, height must be 100–250 cm and weight 30–350 kg, inclusive. These are application limits, not definitions of healthy measurements. Age is required for BMI to enforce the adult-only scope; it does not enter the BMI equation. Do not send `sex` or `activity` to `/api/bmi`.

### Metric request

```json
{"units":"metric","age":30,"weight":80,"height":180,"sex":"male","activity":"moderate"}
```

### US request

```json
{"units":"us","age":30,"weight":176.36980974790207,"height":70.86614173228347,"sex":"male","activity":"moderate"}
```

This is approximately the same person as the metric example. For 5 ft 10 in, send `height: 70`, **not** `5.10`. The React form does that conversion for you.

## Response schemas

### POST `/api/fitness`

The metric example returns:

```json
{
  "measurements": {"weight_kg": 80.0, "height_cm": 180.0},
  "bmi": {"value": 24.69, "category": "Healthy weight"},
  "calories": {
    "resting_kcal": 1780,
    "maintenance_kcal": 2759,
    "activity": "moderate",
    "activity_factor": 1.55,
    "formula": "Mifflin–St Jeor"
  }
}
```

- `measurements`: normalised kg/cm as JSON numbers, rounded to four decimal places.
- `bmi.value`: number rounded to two decimal places; `bmi.category`: string determined from the unrounded BMI.
- `calories.resting_kcal`: integer kcal/day.
- `calories.maintenance_kcal`: integer kcal/day, or **null** for `resting` activity.
- `calories.activity`: selected activity ID; `activity_factor`: number; `formula`: string.

JSON numbers need not retain trailing zeroes. Do not infer category from the rounded BMI; use the returned category.

### POST `/api/calories`

Uses the same request as `/api/fitness`. Returns `measurements` and `calories` with the same schemas, and **no** `bmi` field.

### POST `/api/bmi`

Request:

```json
{"units":"metric","age":30,"weight":80,"height":180}
```

Response:

```json
{
  "measurements": {"weight_kg": 80.0, "height_cm": 180.0},
  "bmi": {"value": 24.69, "category": "Healthy weight"}
}
```

No `calories` field is included. Categories are `Underweight`, `Healthy weight`, `Overweight`, and `Obesity`.

### GET `/api/activities`

Returns an object with an `activities` array. Each entry contains `id` (string), `label` (human-readable string), and `factor` (number). Labels may be refined without changing IDs.

```json
{
  "activities": [
    {"id":"resting","label":"Resting energy only","factor":1.0},
    {"id":"sedentary","label":"Sedentary · little or no exercise","factor":1.2},
    {"id":"light","label":"Light · exercise 1–3 days/week","factor":1.375},
    {"id":"moderate","label":"Moderate · exercise 3–5 days/week","factor":1.55},
    {"id":"active","label":"Very active · exercise 6–7 days/week","factor":1.725},
    {"id":"extra_active","label":"Extra active · strenuous training or physical job","factor":1.9}
  ]
}
```

## Fitness errors

| Status | Meaning |
|---|---|
| 400 | Malformed JSON, wrong shape, invalid/missing/unknown fields, or an unusable non-positive resting estimate |
| 404 | API route not found |
| 405 | Unsupported method |
| 413 | Request body exceeds 16 KiB |
| 415 | Missing/incorrect JSON content type |

Fitness validation failures return an `error` string and `field` string, e.g.:

```json
{"error":"Enter a whole-number age from 20 to 100.","field":"age"}
```

`field` is the input name, or `body` for object-level errors. Framework errors under `/api/` return an `error` string without a `field`. Do not depend on exact framework error wording. Failed requests have no calculation results.

## Release identity

`/version` reads VERSION and APP_COMMIT once at startup. Missing/blank APP_COMMIT gives `unknown`. Missing/empty VERSION prevents startup. The application reports the supplied commit; it does not inspect Git or detect uncommitted work. Restart after changing local metadata; rebuild images after changing packaged code or metadata.

Docker copies VERSION and embeds the APP_COMMIT build argument. CI and release checks compare both values with the selected source identity. `/health` is only a liveness check; it does not assert that frontend assets exist. Smoke verification checks those separately.

## Compatibility and version decision

2.0.0 is major because the earlier contract explicitly promised the arithmetic HTML form at `/`; that behaviour is replaced by a JavaScript fitness interface. The former arithmetic endpoints have also been removed and return HTTP 404.

Preserve endpoint paths, required response fields/types, and documented semantics in compatible releases. Clients should tolerate additional response fields. New compatible capabilities can be minor; fixing an implementation to match this contract can be patch. Removing or incompatibly changing documented behaviour requires major.

For equations, rounding, input limitations, and source references, see [FORMULAS.md](FORMULAS.md).

## Browser navigation

Browser page routes and JSON API routes are separate:

| Action | Browser URL | Backend request |
|---|---|---|
| Home | `/` | GET page |
| Calories + BMI | `/calories-bmi` | Calculations wait for submission |
| BMI only | `/bmi` | Calculations wait for submission |
| Calculate calories + BMI | `/calories-bmi/results` | POST `/api/fitness` |
| Calculate BMI | `/bmi/results` | POST `/api/bmi` |
| Behind the numbers | `/behind-the-numbers` | Static explanation page |

Calculate navigates only after a successful API response; invalid input stays on the form. Nginx serves the React shell for every listed page route, allowing direct links and refreshes. Unknown server paths still return 404. Back/Forward updates the selected page; results are cleared on navigation and never stored in history, URLs, or browser storage. A refreshed/revisited results page asks you to calculate again. Editing details keeps the form values for the current session.

Manual checks: switch both calculator modes, calculate each, open the methods page, use Back/Forward, and refresh each page. A results refresh should show the calculate-again prompt.

## Container ownership

Nginx owns page routes, assets, and /frontend-version.json. It proxies /api/*, /health, and /version to Flask. Requests through the frontend keep their original paths and bodies. Only the frontend port is published to the host. Backend /version and frontend /frontend-version.json must match the selected release identity. Smoke tests verify both. See CONTAINERS.md for setup and migration.
