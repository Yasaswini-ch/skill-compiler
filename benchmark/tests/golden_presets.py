"""Hand-worked answers for the arena presets (benchmark/presets_src.py).

GOLDEN_PRESETS[id] = {"good": [outputs that must pass every check],
                      "bad":  [(output, {ids of the checks that must fail, exactly})]}
Check ids are c1, c2, ... in the order of the preset's checks.
"""
import json


def j(**kw) -> str:
    return json.dumps(kw)


def with_(base: dict, **changes) -> str:
    return json.dumps({**base, **changes})


def all_of(n: int) -> set:
    return {f"c{i}" for i in range(1, n + 1)}


P01 = dict(subtotal="197.15", discount="23.66", tax="13.01", total="186.50")
P04 = dict(price_a="199.99", price_b="169.99", tax="13.60", final="183.59")
P05 = dict(final_balance="-46.75", overdrafts=3)
P06 = dict(quiz_average="89.0", final_grade="91.2", letter="A")
P07 = dict(weight_fee="10.50", surcharge="2.00", vat="1.25", total="13.75")

HEAD = "| Ingredient | Original | Scaled |\n|---|---|---|\n"
P03 = (HEAD + "| beans | 900 g | 3.6 kg |\n| tomatoes | 1200 g | 4.8 kg |\n| beef | 450 g | 1.8 kg |\n"
       "| oil | 3 tbsp | 12.0 tbsp |\n| salt | 1.2 tsp | 4.8 tsp |\nScale factor: 4")

P08 = ("Dear Customer,\nThank you for your message. We will send a replacement with all the screws as soon as possible "
       "and keep you informed about the delivery date.\nBest regards, Support")

GOLDEN_PRESETS = {
    "p01": {
        "good": [j(**P01), "```json\n" + j(**P01) + "\n```"],
        "bad": [
            ("The total is 186.50.", all_of(6)),                      # not JSON
            (j(**P01)[:-1], {"c1", "c2"}),                            # broken JSON; the text checks still see the values
            (with_(P01, note="x"), {"c2"}),                           # extra key
            (with_(P01, subtotal="197.50"), {"c3"}),
            (with_(P01, discount="0.00"), {"c4"}),                    # forgot the discount
            (with_(P01, tax="13.02"), {"c5"}),
            (with_(P01, total="186.51"), {"c6"}),
            (with_(P01, subtotal=197.15), {"c3"}),                    # a JSON number is not the required string
        ],
    },
    "p02": {
        "good": ["Local arrival: 02:15\nDay: next day", "\n Local arrival: 02:15\nDay: next day \n"],
        "bad": [
            ("Arrival at 02:15, next day.", all_of(4)),
            ("Local arrival: 02:20\nDay: next day", {"c2"}),
            ("Local arrival: 02:15\nDay: same day", {"c3"}),
            ("Local arrival: 02:15\nDay: next day\nHave a good trip", {"c4"}),
            ("Here is the answer:\nLocal arrival: 02:15\nDay: next day", {"c1", "c4"}),
        ],
    },
    "p03": {
        "good": [P03, "```\n" + P03 + "\n```"],
        "bad": [
            ("Here is the table:\n" + P03, {"c1"}),
            (P03.replace("| beans | 900 g | 3.6 kg |", "| beans | 900 g | 3600.0 g |"), {"c2"}),
            (P03.replace("| tomatoes | 1200 g | 4.8 kg |", "| tomatoes | 1.2 kg | 4.8 kg |"), {"c3"}),
            (P03.replace("| beef | 450 g | 1.8 kg |", "| beef | 450 g | 1800.0 g |"), {"c4"}),
            (P03.replace("12.0 tbsp", "12 tbsp"), {"c5"}),
            (P03.replace("| 4.8 tsp |", "| 4.80 tsp |"), {"c6"}),
            (P03.replace("Scale factor: 4", "Scale factor: 6"), {"c7"}),
            (P03 + "\nEnjoy the chili", {"c7"}),
        ],
    },
    "p04": {
        "good": [j(**P04), "```json\n" + j(**P04) + "\n```"],
        "bad": [
            ("The final price is 183.59.", all_of(6)),
            (with_(P04, note="x"), {"c2"}),
            (with_(P04, price_a="200.00"), {"c3"}),
            (with_(P04, price_b="170.00"), {"c4"}),
            (with_(P04, tax="13.6"), {"c5"}),
            (with_(P04, final="183.60"), {"c6"}),
        ],
    },
    "p05": {
        "good": [j(**P05), "```json\n" + j(**P05) + "\n```"],
        "bad": [
            ("Final balance -46.75 with 3 overdrafts.", all_of(4)),
            (with_(P05, note="x"), {"c2"}),
            (with_(P05, final_balance="-34.75"), {"c3"}),             # forgot the fees
            (with_(P05, overdrafts=2), {"c4"}),
            (with_(P05, overdrafts="3"), {"c4"}),                     # a string, not an integer
        ],
    },
    "p06": {
        "good": [j(**P06), "```json\n" + j(**P06) + "\n```"],
        "bad": [
            ("The grade is 91.2, an A.", all_of(5)),
            (with_(P06, note="x"), {"c2"}),
            (with_(P06, quiz_average="89"), {"c3"}),
            (with_(P06, final_grade="90.7"), {"c4"}),                 # used the 30/30/40 weights
            (with_(P06, letter="B"), {"c5"}),
        ],
    },
    "p07": {
        "good": [j(**P07), "```json\n" + j(**P07) + "\n```"],
        "bad": [
            ("The total is 13.75.", all_of(6)),
            (with_(P07, note="x"), {"c2"}),
            (with_(P07, weight_fee="9.30"), {"c3"}),                  # 4 started halves instead of 5
            (with_(P07, surcharge="0.00"), {"c4"}),
            (with_(P07, vat="1.00"), {"c5"}),
            (with_(P07, total="13.00"), {"c6"}),
        ],
    },
    "p08": {
        "good": [P08, "```\n" + P08 + "\n```"],
        "bad": [
            (P08.replace("Dear Customer,", "Hello Customer,"), {"c1"}),
            (P08.replace("Thank you for your message.",
                         "Thank you for your message and for telling us exactly what happened with the parcel and its "
                         "contents, which we take seriously."), {"c2"}),
            (P08.replace("Thank you", "We are sorry, thank you"), {"c3"}),
            (P08.replace("Thank you", "Sorry, thank you"), {"c3"}),
            (P08.replace("keep you", "apologise and keep you"), {"c3"}),
            (P08.replace("date.", "date, with no problem."), {"c3"}),
            (P08.replace("Best regards, Support", "Best regards, Support Team"), {"c4"}),
            (P08 + "\nP.S. Thank you!", {"c4"}),
        ],
    },
}
