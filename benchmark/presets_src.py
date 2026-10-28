"""Source definitions of the Break Gemma arena challenges (the attack presets).

build_presets.py tests these against plain Gemma and the harness and writes benchmark/attack_presets.json
(the file web/arena.py loads). Nothing here is a result: the "tested" counts and the tag come only from saved runs.

Each spec has: id, title, skill_text (at most 6 numbered steps), input (at most 1500 characters), checks that
benchmark/scorer.py can score, steps, why_it_breaks.

The arithmetic checks are tied to the exact input numbers. If an attendee edits the numbers, a correct answer can fail
the check, so a "failure" collected from an edited input must be looked at by hand (the arena log is reviewed anyway).
"""
from __future__ import annotations

import re


def field(key: str, value: str, label: str = "lost_track") -> dict:
    """A check that the JSON field `key` holds exactly this string. Matches the whole output text, so it also
    requires the value to be written as a string, as the skills ask."""
    return {"type": "regex", "value": rf'"{key}"\s*:\s*"{re.escape(value)}"', "label": label}


def row(name: str, original: str, scaled: str, label: str = "lost_track") -> dict:
    """A check for one row of a Markdown table: | name | original | scaled |"""
    return {"type": "regex", "value": rf"(?im)^\|\s*{name}\s*\|\s*{original}\s*\|\s*{scaled}\s*\|\s*$", "label": label}


def numbered(checks: list[dict]) -> list[dict]:
    return [{"id": f"c{i}", **c} for i, c in enumerate(checks, 1)]


def skill(name: str, description: str, steps: list[str]) -> str:
    body = "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1))
    return f"---\nname: {name}\ndescription: {description}\n---\n\n{body}"


JSON_VALID = {"type": "json_valid", "label": "wrong_format"}


def json_keys(*keys: str) -> dict:
    return {"type": "json_keys", "value": list(keys), "label": "skipped_step"}


PRESET_SPECS = [
    {
        "id": "p01",
        "title": "The invoice that does not add up",
        "skill_text": skill("invoice-check", "Total a supplier invoice with a threshold discount and tax.", [
            "List each line item with its quantity and unit price.",
            "Multiply the quantity by the unit price for each item, then add the results to get the subtotal.",
            "If the subtotal is more than 150.00, the discount is 12% of the subtotal, rounded to 2 decimals. Otherwise the discount is 0.00.",
            "The tax is 7.5% of (subtotal minus discount), rounded to 2 decimals.",
            "The total is subtotal minus discount plus tax.",
            "Output JSON with exactly these keys: subtotal, discount, tax, total. Write every amount as a string with exactly 2 decimals.",
        ]),
        "input": "Order 5513 from Corvin Hardware: 7 x work gloves at 8.90, 3 x tape measures at 14.75, "
                 "12 x wood screw packs at 2.35, 2 x clamps at 31.20.",
        "checks": numbered([JSON_VALID, json_keys("subtotal", "discount", "tax", "total"),
                            field("subtotal", "197.15"), field("discount", "23.66"), field("tax", "13.01"),
                            field("total", "186.50")]),
        "steps": 6,
        "why_it_breaks": "Six chained calculations with a threshold and two roundings: one slip early carries into every later amount.",
    },
    {
        "id": "p02",
        "title": "Landing on the other side of midnight",
        "skill_text": skill("arrival-time", "Work out the local arrival time and day of a flight.", [
            "Read the departure time (24-hour clock), the flight duration, and how many hours the destination clock is ahead of or behind the departure city's clock.",
            "Add the flight duration to the departure time.",
            "Move the clock by the time difference: add it if the destination is ahead, subtract it if the destination is behind.",
            'If the result is 24:00 or later, subtract 24:00 and the day is "next day". If it is below 00:00, add 24:00 and the day is "previous day". Otherwise the day is "same day".',
            'Output exactly 2 lines and nothing else: "Local arrival: HH:MM" and "Day: " followed by same day, next day or previous day.',
        ]),
        "input": "Departure 21:40 from Lisbon. Flight time 9 hours 35 minutes. The destination clock is 5 hours behind Lisbon.",
        "checks": numbered([
            {"type": "starts_with", "value": "Local arrival:", "label": "ignored_constraint"},
            {"type": "regex", "value": r"(?m)^Local arrival: 02:15$", "label": "lost_track"},
            {"type": "regex", "value": r"(?m)^Day: next day$", "label": "lost_track"},
            {"type": "regex", "value": r"\A[^\n]+\n[^\n]+\Z", "label": "ignored_constraint"},
        ]),
        "steps": 5,
        "why_it_breaks": "The clock passes midnight twice in different directions, and the time difference is subtracted, not added.",
    },
    {
        "id": "p03",
        "title": "The chili that outgrew the pot",
        "skill_text": skill("recipe-table", "Scale a recipe and print it as a fixed table.", [
            "Read the original servings and the target servings. The scale factor is target servings divided by original servings.",
            "List each ingredient with its original quantity and unit, exactly as written.",
            "Multiply each quantity by the scale factor and show the result with exactly 1 decimal place, keeping the unit.",
            "If a scaled quantity in grams is 1000 or more, show it in kg instead (divide by 1000) with exactly 1 decimal place.",
            'Output a Markdown table whose first line is exactly "| Ingredient | Original | Scaled |", then a separator line, then one row per ingredient in the order of the recipe.',
            'After the table write one last line "Scale factor: " followed by the factor. Write nothing else before or after.',
        ]),
        "input": "Chili for 6: 900 g beans, 1200 g tomatoes, 450 g beef, 3 tbsp oil, 1.2 tsp salt. Scale it to 24 servings.",
        "checks": numbered([
            {"type": "starts_with", "value": "| Ingredient | Original | Scaled |", "label": "ignored_constraint"},
            row("beans", r"900\s*g", r"3\.6\s*kg", "wrong_format"),
            row("tomatoes", r"1200\s*g", r"4\.8\s*kg", "wrong_format"),
            row("beef", r"450\s*g", r"1\.8\s*kg", "wrong_format"),
            row("oil", r"3\s*tbsp", r"12\.0\s*tbsp"),
            row("salt", r"1\.2\s*tsp", r"4\.8\s*tsp"),
            {"type": "regex", "value": r"(?m)^Scale factor:\s*4(\.0)?\s*\Z", "label": "ignored_constraint"},
        ]),
        "steps": 6,
        "why_it_breaks": "Grams switch to kg only in the Scaled column; the Original column must stay in grams, even for 1200 g.",
    },
    {
        "id": "p04",
        "title": "Two discounts, one tax",
        "skill_text": skill("price-ladder", "Apply two discounts in a row and then tax.", [
            "Read the list price.",
            "Take 20% off the list price and round to 2 decimals. Call the result price A.",
            "Take 15% off price A and round to 2 decimals. Call the result price B.",
            "Add 8% tax on price B, rounding the tax to 2 decimals. The final price is price B plus the tax.",
            "Output JSON with exactly these keys: price_a, price_b, tax, final. Write every amount as a string with exactly 2 decimals.",
        ]),
        "input": "List price: 249.99.",
        "checks": numbered([JSON_VALID, json_keys("price_a", "price_b", "tax", "final"),
                            field("price_a", "199.99"), field("price_b", "169.99"), field("tax", "13.60"),
                            field("final", "183.59")]),
        "steps": 5,
        "why_it_breaks": "Two percentages are applied one after the other, each rounded before the next, so a wrong first price spoils the rest.",
    },
    {
        "id": "p05",
        "title": "The overdraft counter",
        "skill_text": skill("balance-tracker", "Track an account balance and count overdraft fees.", [
            "Start with the opening balance.",
            "Apply the transactions one by one in the order given. A deposit adds to the balance and a withdrawal subtracts from it.",
            "After any withdrawal that leaves the balance below 0.00, subtract a fee of 12.00 immediately and count one overdraft.",
            "After the last transaction, take the final balance and the number of overdrafts.",
            "Output JSON with exactly these keys: final_balance, overdrafts. Write final_balance as a string with exactly 2 decimals and overdrafts as an integer.",
        ]),
        "input": "Opening balance 120.00. Transactions in this order: withdraw 85.50, withdraw 60.00, deposit 40.00, "
                 "withdraw 30.00, deposit 100.00, withdraw 95.25.",
        "checks": numbered([JSON_VALID, json_keys("final_balance", "overdrafts"),
                            field("final_balance", "-46.75"),
                            {"type": "regex", "value": r'"overdrafts"\s*:\s*3\b', "label": "lost_track"}]),
        "steps": 5,
        "why_it_breaks": "Order matters: every overdraft fee changes the balance that the next transaction starts from.",
    },
    {
        "id": "p06",
        "title": "The grade that moves the goalposts",
        "skill_text": skill("grade-calc", "Compute a course grade from quizzes, a project and an exam.", [
            "List the three quiz scores, the project score and the exam score.",
            "Drop the lowest quiz score. Never drop the project or the exam.",
            "The quiz average is the average of the two remaining quiz scores.",
            "If the exam score is higher than the quiz average, the final grade is 20% quiz average + 30% project + 50% exam. Otherwise it is 30% quiz average + 30% project + 40% exam. Round to 1 decimal.",
            "The letter is A for 90 or more, B for 80 to 89.9, C for 70 to 79.9, D for 60 to 69.9, otherwise F.",
            "Output JSON with exactly these keys: quiz_average, final_grade, letter. Write quiz_average and final_grade as strings with exactly 1 decimal.",
        ]),
        "input": "Quizzes: 78, 92, 86. Project: 88. Exam: 94.",
        "checks": numbered([JSON_VALID, json_keys("quiz_average", "final_grade", "letter"),
                            field("quiz_average", "89.0"), field("final_grade", "91.2"),
                            {"type": "regex", "value": r'"letter"\s*:\s*"A"', "label": "lost_track"}]),
        "steps": 6,
        "why_it_breaks": "A condition changes the formula, and the lowest quiz has to be dropped before anything is averaged.",
    },
    {
        "id": "p07",
        "title": "Parcel post, every started half kilo",
        "skill_text": skill("parcel-rate", "Price a parcel by weight and distance.", [
            "Read the parcel weight in kg and the distance in km.",
            "The first 1.0 kg costs 4.50. Weight above 1.0 kg is charged 1.20 for every started 0.5 kg. The weight fee is 4.50 plus these charges.",
            "If the distance is more than 100 km, add a surcharge of 2.00. Otherwise the surcharge is 0.00.",
            "VAT is 10% of (weight fee plus surcharge), rounded to 2 decimals.",
            "The total is weight fee plus surcharge plus VAT.",
            "Output JSON with exactly these keys: weight_fee, surcharge, vat, total. Write every amount as a string with exactly 2 decimals.",
        ]),
        "input": "Parcel: 3.2 kg, travelling 140 km.",
        "checks": numbered([JSON_VALID, json_keys("weight_fee", "surcharge", "vat", "total"),
                            field("weight_fee", "10.50"), field("surcharge", "2.00"), field("vat", "1.25"),
                            field("total", "13.75")]),
        "steps": 6,
        "why_it_breaks": '"Every started 0.5 kg" means rounding up, then a distance threshold, then VAT on the sum.',
    },
    {
        "id": "p08",
        "title": "Four rules, one polite reply",
        "skill_text": skill("polite-reply", "Reply to a customer message under strict wording rules.", [
            "Read the customer message.",
            "Write a reply of at most 40 words in total, including the sign-off.",
            'The reply must begin with "Dear Customer,".',
            "The reply must not contain any of these words: sorry, unfortunately, apologize, problem.",
            'The reply must end with the exact last line "Best regards, Support".',
            "Output only the reply.",
        ]),
        "input": "My parcel arrived with a broken lid and the screws are missing. I want a replacement and I want it quickly.",
        "checks": numbered([
            {"type": "starts_with", "value": "Dear Customer,", "label": "ignored_constraint"},
            {"type": "max_words", "value": 40, "label": "ignored_constraint"},
            {"type": "regex", "value": r"(?is)\A(?!.*\b(sorry|unfortunately|apologi[sz]e|problem)\b)", "label": "ignored_constraint"},
            {"type": "regex", "value": r"(?m)^Best regards, Support\Z", "label": "ignored_constraint"},
        ]),
        "steps": 6,
        "why_it_breaks": "No arithmetic: four wording rules at once. Its checks do not depend on the input numbers, so it is also a control for rule-following.",
    },
]
