# Fitness calculation reference

All calculations run in `fitness.py`. The browser sends measurements to Flask; it does not independently calculate calorie or BMI results. These are estimates for adults, not diagnoses or personalised dietary prescriptions.

## 1. Convert units

Metric requests provide kilograms and centimetres. US requests provide pounds and **total inches**. The UI combines feet and inches before submission.

- `kilograms = pounds × 0.45359237`
- `centimetres = inches × 2.54`
- `total_inches = feet × 12 + inches`
- `metres = centimetres / 100`

Calculate with unrounded converted values. Returned normalised measurements have four decimal places; this rounding does not feed back into the calculations. Switching UI units rounds displayed conversions to three decimal places, so repeated switching can introduce small rounding differences.

## 2. Resting energy: Mifflin–St Jeor

```text
resting_kcal_per_day = 10 × weight_kg + 6.25 × height_cm − 5 × age_years + coefficient

male coefficient:   +5
female coefficient: −161
```

The original equation estimates resting energy expenditure (REE/RMR), often described as BMR in online calculators. The UI calls it **resting energy** for clarity. The sex input selects the equation coefficient; it is not a measure of gender identity. These two coefficients do not capture all physiological differences, and no unvalidated third coefficient is invented.

Source: [Mifflin et al., A new predictive equation for resting energy expenditure in healthy individuals (1990)](https://pubmed.ncbi.nlm.nih.gov/2305711/).

## 3. Estimated maintenance calories

```text
maintenance_kcal_per_day = unrounded_resting_energy × activity_factor
```

| API activity ID | UI description | Factor |
|---|---|---:|
| `resting` | Resting energy only | 1.0 |
| `sedentary` | Little or no exercise | 1.2 |
| `light` | Exercise 1–3 days/week | 1.375 |
| `moderate` | Exercise 3–5 days/week | 1.55 |
| `active` | Very active: exercise 6–7 days/week | 1.725 |
| `extra_active` | Strenuous training or physical job | 1.9 |

These are conventional calculator activity assumptions, **not coefficients established by the Mifflin paper**. Frequency alone does not establish energy expenditure: intensity, duration, occupation, and individual physiology matter. The UI deliberately uses six clear options rather than implying precision from overlapping exercise categories.

`resting` returns `maintenance_kcal: null` because resting expenditure alone is not a maintenance intake estimate. All other levels return estimated maintenance calories. No weight-loss deficit, surplus, or diet recommendation is calculated.

Calorie outputs use Python `round()` to whole kcal (ties to even). Maintenance uses the unrounded resting estimate, not the rounded displayed number.

### Worked example

Male coefficient, age 30, weight 80 kg, height 180 cm, moderate activity:

```text
Resting = 10×80 + 6.25×180 − 5×30 + 5 = 1,780 kcal/day
Maintenance = 1,780 × 1.55 = 2,759 kcal/day
BMI = 80 / 1.8² = 24.691358… → 24.69 (Healthy weight)
```

## 4. Adult BMI

```text
BMI = weight_kg / height_metres²
```

| Unrounded BMI | Category |
|---|---|
| Below 18.5 | Underweight |
| 18.5 to below 25 | Healthy weight |
| 25 to below 30 | Overweight |
| 30 or above | Obesity |

The value is displayed to two decimal places. Classify **before rounding**: a raw value of 24.9999 displays as 25.00 but remains in the Healthy weight category. The UI explains this boundary behaviour. The decorative scale spans 10–40 and clamps its marker at either end; the numeric result is never clamped.

Source: [CDC Adult BMI Categories](https://www.cdc.gov/bmi/adult-calculator/bmi-categories.html), for adults aged 20 and older. BMI does not distinguish muscle, fat, and bone or measure fat distribution.

## Input limits and limitations

- Whole-number age 20–100, height 100–250 cm, weight 30–350 kg, or exact US equivalents. These are application guardrails, not clinical definitions of healthy values.
- Reject missing values, booleans, numeric strings, non-finite numbers, unsupported units/activity/sex, unknown fields, and non-positive resting energy estimates.
- The original Mifflin study covered ages 19–78. Estimates beyond that range are extrapolations; the broader application age limit does not imply equivalent validation.
- Not intended for children, pregnancy, or breastfeeding. Estimates can be less useful for athletes, older adults, and people with conditions affecting metabolism.
- Measurements are neither persisted nor intentionally logged by the application. They are sent in POST bodies, not URL query strings. Do not add request-body logging without revisiting this privacy statement.
