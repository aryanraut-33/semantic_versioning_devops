"""Adult fitness estimates. All calculations use kilograms and centimetres."""

import math

ACTIVITIES = {
    "resting": ("Resting energy only", 1.0),
    "sedentary": ("Sedentary · little or no exercise", 1.2),
    "light": ("Light · exercise 1–3 days/week", 1.375),
    "moderate": ("Moderate · exercise 3–5 days/week", 1.55),
    "active": ("Very active · exercise 6–7 days/week", 1.725),
    "extra_active": ("Extra active · strenuous training or physical job", 1.9),
}


class InputError(ValueError):
    def __init__(self, field, message):
        super().__init__(message)
        self.field = field


def number(data, field):
    value = data.get(field)
    if type(value) not in (int, float):
        raise InputError(field, f"{field} must be a finite JSON number.")
    try:
        valid = math.isfinite(value)
    except OverflowError:
        valid = False
    if not valid:
        raise InputError(field, f"{field} must be a finite JSON number.")
    return value


def measurements(data, calories):
    if not isinstance(data, dict):
        raise InputError("body", "Send a JSON object.")
    units = data.get("units")
    if units not in ("metric", "us"):
        raise InputError("units", "units must be metric or us.")
    allowed = {"units", "age", "weight", "height"}
    if calories:
        allowed |= {"sex", "activity"}
    if set(data) - allowed:
        raise InputError("body", "Unknown fields: " + ", ".join(sorted(set(data) - allowed)))
    age = number(data, "age")
    if not 20 <= age <= 100 or age != int(age):
        raise InputError("age", "Enter a whole-number age from 20 to 100.")
    weight = number(data, "weight")
    height = number(data, "height")
    kg = weight if units == "metric" else weight * 0.45359237
    cm = height if units == "metric" else height * 2.54
    if not 30 <= kg <= 350:
        raise InputError("weight", "Weight must be between 30 and 350 kg (66.14–771.62 lb approximately).")
    if not 100 <= cm <= 250:
        raise InputError("height", "Height must be between 100 and 250 cm (39.37–98.43 in approximately).")
    return age, kg, cm


def bmi_category(value):
    if value < 18.5:
        return "Underweight"
    if value < 25:
        return "Healthy weight"
    if value < 30:
        return "Overweight"
    return "Obesity"


def estimate(data, kind="fitness"):
    include_calories = kind != "bmi"
    age, kg, cm = measurements(data, include_calories)
    result = {"measurements": {"weight_kg": round(kg, 4), "height_cm": round(cm, 4)}}
    if kind != "calories":
        bmi = kg / (cm / 100) ** 2
        result["bmi"] = {"value": round(bmi, 2), "category": bmi_category(bmi)}
    if include_calories:
        sex = data.get("sex")
        if sex not in ("male", "female"):
            raise InputError("sex", "sex must be male or female for this equation.")
        activity = data.get("activity")
        if not isinstance(activity, str) or activity not in ACTIVITIES:
            raise InputError("activity", "Choose a supported activity level.")
        factor = ACTIVITIES[activity][1]
        resting = 10 * kg + 6.25 * cm - 5 * age + (5 if sex == "male" else -161)
        if resting <= 0:
            raise InputError("body", "These measurements fall outside this equation's useful range.")
        result["calories"] = {
            "resting_kcal": round(resting),
            "maintenance_kcal": None if activity == "resting" else round(resting * factor),
            "activity": activity,
            "activity_factor": factor,
            "formula": "Mifflin–St Jeor",
        }
    return result
