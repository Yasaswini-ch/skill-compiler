"""Hand-written answers used to verify the checks in benchmark/tasks.json.

GOLDEN[task_id] = {"good": [outputs that must pass every check],
                   "bad":  [(output, {ids of the checks that must fail, exactly})]}
A wrong check would create a fake failure, so each task has a correct answer worked out by hand
(see the arithmetic in the comments) and wrong answers that break specific checks.
"""
import json

TABLE_HEAD = "| Ingredient | Original | Scaled |\n|---|---|---|\n"


def j(**kw) -> str:
    return json.dumps(kw)


# --- t01: bug triage, checkout crash -------------------------------------------------------
T01 = dict(bug="App crashes whenever Pay is tapped on the checkout page.",          # 10 words
           impact="Whole sales team cannot place orders, so work is blocked.",       # 10 words
           version="v2.4.1", os="Android 13", severity="critical", component="payments",
           fix="Fix the crash in the checkout payment handler after 2.4.1 update.")  # 11 words

# --- t02: bug triage, slow search with a feature-request distraction ----------------------
T02 = dict(bug="Search results take about 20 seconds to appear.",
           impact="One user waits too long for search results.",
           version="v3.0.12", os="Windows 11", severity="minor", component="search",
           fix="Optimize the search query and add caching.")

# --- t03: candidate screen -----------------------------------------------------------------
T03 = dict(name="Priya Nair", experience="Data analyst at Orbit Retail for 2 years.",  # 8 words
           skills="SQL, Excel, Tableau, Power BI, R", years=2, meets_minimum="no",
           reason="Under 3 years and no Python.",
           note="Recommend: do not advance Priya, as she lacks Python and 3 years.")

# --- t04: invoice. 12*3.50=42.00, 5*18.00=90.00, 3*6.25=18.75 -> subtotal 150.75 (not > 200,
#          discount 0.00); tax 150.75*0.08=12.06; total 150.75+12.06=162.81 -------------------
T04 = dict(vendor="Brightwell Supplies", invoice="INV-20417", subtotal="150.75", discount="0.00",
           tax="12.06", total="162.81")

# --- t05: invoice. 4*45.50=182.00, 10*12.40=124.00, 2*89.99=179.98 -> subtotal 485.98 (> 200);
#          discount 10% = 48.598 -> 48.60; taxable 485.98-48.60=437.38; tax 437.38*0.08=34.9904
#          -> 34.99; total 437.38+34.99=472.37 ------------------------------------------------
T05 = dict(vendor="Harlow Office Co.", invoice="INV-3392", subtotal="485.98", discount="48.60",
           tax="34.99", total="472.37")

# --- t06: pancakes 4 -> 14, factor 3.5: flour 400*3.5=1400.0 g -> 1.4 kg; milk 300*3.5=1050.0 ml;
#          eggs 2*3.5=7.0; butter 45*3.5=157.5 g ------------------------------------------------
T06 = (TABLE_HEAD + "| flour | 400 g | 1.4 kg |\n| milk | 300 ml | 1050.0 ml |\n"
       "| eggs | 2 | 7.0 |\n| butter | 45 g | 157.5 g |\nScale factor: 3.5")

# --- t07: lands 10:35 + 45 min = 11:20 leave; + 1h50 (110 min) = 13:10 arrive; before 15:00 so
#          check-in 15:00; 15:00 -> 19:30 = 270 minutes ------------------------------------------
T07 = "Leave airport: 11:20\nHotel arrival: 13:10\nCheck-in: 15:00\nFree minutes before dinner: 270"

# --- t08: chili 8 -> 2, factor 0.25: beef 1000*0.25=250.0 g; tomatoes 800*0.25=200.0 g;
#          paste 2*0.25=0.5 tbsp; cumin 1.6*0.25=0.4 tsp. Original column stays "1000 g". --------
T08 = (TABLE_HEAD + "| beef mince | 1000 g | 250.0 g |\n| canned tomatoes | 800 g | 200.0 g |\n"
       "| tomato paste | 2 tbsp | 0.5 tbsp |\n| cumin | 1.6 tsp | 0.4 tsp |\nScale factor: 0.25")

# --- t09: headline 8 words, summary 16 words ----------------------------------------------
T09 = dict(headline="Meet the Lumo Desk Lamp, light on touch",
           summary="Lumo dims with a touch slider, charges your phone wirelessly and runs 12 hours on battery.",
           bullets=["Dims from 5% to 100% with a touch slider", "Built-in wireless phone charger",
                    "Battery lasts 12 hours"],
           closing="Available 14/11/2026.", hashtags="#lumo #desklamp")

# --- t10: every bullet 5 words --------------------------------------------------------------
T10 = dict(headline="Meet the Quill Notes app for students",
           summary="Quill Notes searches handwriting, syncs offline and mutes distractions.",
           bullets=["Search handwriting inside scanned notes", "Sync offline across 3 devices",
                    "Focus mode hides all notifications"],
           closing="Available 03/12/2026 for everyone.", hashtags="#quillnotes #students")


def with_(base: dict, **changes) -> str:
    return json.dumps({**base, **changes})


GOLDEN = {
    "t01": {
        "good": [j(**T01), "```json\n" + j(**T01) + "\n```"],
        "bad": [
            (with_(T01, bug="The app crashes every single time that anyone taps the Pay button on the checkout page of the app"), {"c3"}),  # 19 words
            (with_(T01, version="2.4.1", component="Payments"), {"c5", "c6"}),
            (with_(T01, impact="App crashes when tapping Pay on checkout."), {"c7"}),
            ("The app crashes on Android 13 when you tap Pay.", {"c1", "c2", "c3", "c4", "c5", "c6", "c7"}),
        ],
    },
    "t02": {
        "good": [j(**T02)],
        "bad": [
            (with_(T02, bug="Search is slow and dark mode is missing."), {"c6"}),
            (with_(T02, fix="Just add an index to the search table."), {"c7"}),
            (with_(T02, fix="Adjust the search index."), set()),  # "Adjust" must not trip the word "just"
            (with_(T02, severity="low"), {"c5"}),
            (with_(T02, version="3.0.12"), {"c3"}),
            (with_(T02, component="other"), {"c4"}),
            ("Search is slow on Windows 11, version 3.0.12.", {"c1", "c2", "c3", "c4", "c5", "c7"}),
        ],
    },
    "t03": {
        "good": [j(**T03)],
        "bad": [
            (with_(T03, skills="SQL, Excel, Tableau, Power BI, R, statistics"), {"c6"}),  # 6 skills
            (with_(T03, skills=["SQL", "Excel"]), {"c6"}),                               # array, not a list
            (with_(T03, meets_minimum="yes"), {"c4"}),
            (with_(T03, note="I recommend Priya."), {"c5"}),
            (with_(T03, years="2 years"), {"c3"}),
            (with_(T03, experience="Priya has worked as a data analyst for Orbit Retail, a large retail company, "
                                   "for a total of two years so far."), {"c7"}),  # 24 words
        ],
    },
    "t04": {
        "good": [j(**T04)],
        "bad": [
            (with_(T04, total="162.80"), {"c7"}),
            (with_(T04, tax="12.07"), {"c6"}),
            (with_(T04, discount="0"), {"c5"}),
            (with_(T04, subtotal="150.25"), {"c4"}),
            (with_(T04, subtotal=150.75), {"c4"}),  # a JSON number is not the required string
            (with_(T04, invoice="20417"), {"c3"}),
        ],
    },
    "t05": {
        "good": [j(**T05)],
        "bad": [
            (with_(T05, discount="0.00", tax="38.88", total="524.86"), {"c5", "c6", "c7"}),  # forgot discount
            (with_(T05, discount="48.598"), {"c5"}),
            (with_(T05, subtotal="485.00", discount="48.50"), {"c4", "c5"}),
        ],
    },
    "t06": {
        "good": [T06, "```\n" + T06 + "\n```"],
        "bad": [
            (T06.replace("1.4 kg", "1400.0 g"), {"c2"}),
            ("Here is the scaled recipe:\n" + T06, {"c1"}),
            (T06 + "\nEnjoy!", {"c7"}),
            (T06.replace("| 7.0 |", "| 7 |"), {"c4"}),
            (T06.replace("1050.0 ml", "1.1 l"), {"c3"}),
        ],
    },
    "t07": {
        "good": [T07],
        "bad": [
            ("Here is your plan:\n" + T07, {"c1", "c7"}),
            (T07.replace("13:10", "13:20"), {"c3"}),
            (T07.replace("270", "330"), {"c5"}),
            (T07.replace("Check-in: 15:00", "Check-in: 13:10").replace("270", "380"), {"c4", "c5"}),
            ("Hotel arrival: 13:10\nLeave airport: 11:20\nCheck-in: 15:00\nFree minutes before dinner: 270",
             {"c1", "c6"}),
        ],
    },
    "t08": {
        "good": [T08],
        "bad": [
            (T08.replace("1000 g | 250.0 g", "1 kg | 250.0 g"), {"c2"}),
            (T08.replace("0.4 tsp", "0.40 tsp"), {"c5"}),
            (T08.replace("Scale factor: 0.25", "Scale factor: 0.5"), {"c7"}),
            (T08.replace("2 tbsp | 0.5 tbsp", "2 tbsp | 0.5 tsp"), {"c4"}),
        ],
    },
    "t09": {
        "good": [j(**T09)],
        "bad": [
            (with_(T09, headline="Introducing the Lumo Desk Lamp"), {"c3"}),
            (with_(T09, headline="Meet the Lumo Desk Lamp, light on touch today"), {"c4"}),  # 9 words
            (with_(T09, summary="Lumo is a desk lamp that dims smoothly from five percent to one hundred percent with "
                                "a touch slider, charges your phone wirelessly, and keeps running for twelve whole "
                                "hours on one charge."), {"c5"}),  # 34 words
            (with_(T09, summary="A revolutionary lamp that dims by touch."), {"c6"}),
            (with_(T09, bullets=["A cutting-edge touch slider", "Wireless charger", "12 hour battery"]), {"c6"}),
            (with_(T09, closing="Available 11/14/2026."), {"c7"}),
            (with_(T09, closing="Out now on 14/11/2026."), {"c7"}),
        ],
    },
    "t10": {
        "good": [j(**T10)],
        "bad": [
            (with_(T10, bullets=["Search handwriting inside every scanned note that you have ever saved on any device",
                                 "Sync offline across 3 devices", "Focus mode hides all notifications"]), {"c3"}),
            (with_(T10, hashtags="#QuillNotes #students"), {"c6"}),
            (with_(T10, hashtags="#quill #notes #students"), {"c6"}),
            (with_(T10, closing="Available 3/12/2026"), {"c7"}),
            (with_(T10, bullets=["Search handwriting inside scanned notes", "Sync offline across 3 devices"]), {"c5"}),
        ],
    },
}


# Broken JSON (last brace cut off) and a wrong key set, for the tasks whose c1/c2 were not yet exercised.
_ALL = {f"c{i}" for i in range(1, 8)}
GOLDEN["t03"]["bad"] += [(j(**T03)[:-1], _ALL), (with_(T03, extra="x"), {"c2"})]
GOLDEN["t04"]["bad"] += [(j(**T04)[:-1], {"c1", "c2", "c3"}), (with_(T04, currency="USD"), {"c2"})]
GOLDEN["t05"]["bad"] += [(j(**T05)[:-1], {"c1", "c2", "c3"}), (with_(T05, currency="USD"), {"c2"})]
GOLDEN["t09"]["bad"] += [(j(**T09)[:-1], {"c1", "c2", "c3", "c4", "c5", "c7"}), (with_(T09, extra="x"), {"c2"})]
GOLDEN["t10"]["bad"] += [(j(**T10)[:-1], _ALL), (with_(T10, extra="x"), {"c2"})]

GOLDEN["t06"]["bad"] += [
    (T06.replace("157.5 g", "157 g"), {"c5"}),
    (TABLE_HEAD + "| milk | 300 ml | 1050.0 ml |\n| flour | 400 g | 1.4 kg |\n| eggs | 2 | 7.0 |\n"
     "| butter | 45 g | 157.5 g |\nScale factor: 3.5", {"c6"}),
]

GOLDEN["t07"]["bad"] += [(T07.replace("Leave airport: 11:20", "Leave airport: 11:05"), {"c2"})]
GOLDEN["t08"]["bad"] += [
    ("Sure!\n" + T08, {"c1"}),
    (T08.replace("200.0 g", "200 g"), {"c3"}),
    (TABLE_HEAD + "| canned tomatoes | 800 g | 200.0 g |\n| beef mince | 1000 g | 250.0 g |\n"
     "| tomato paste | 2 tbsp | 0.5 tbsp |\n| cumin | 1.6 tsp | 0.4 tsp |\nScale factor: 0.25", {"c6"}),
]
