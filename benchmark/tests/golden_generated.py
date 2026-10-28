"""Hand-worked answers for the 7 hand-checked generated tasks (benchmark/tasks_generated_reviewed.json).

GOLDEN_GENERATED[task_id] = {"good": [outputs that must pass every check],
                             "bad":  [(output, {ids of the checks that must fail, exactly})]}
Same idea as golden.py: every check needs a correct answer that passes and a wrong answer that fails it.
"""
import json

TABLE_HEAD = "| Ingredient | Original | Scaled |\n|---|---|---|\n"


def j(**kw) -> str:
    return json.dumps(kw)


def with_(base: dict, **changes) -> str:
    return json.dumps({**base, **changes})


ALL5 = {"c1", "c2", "c3", "c4", "c5"}

# --- t01-v2: login screen hangs, version 5.5.0 on Android 14 ------------------------------------
G_T01V2 = dict(bug="Login screen hangs on Android 14 when tapping Submit.",             # 9 words
               impact="Users cannot access their accounts, affecting 500 users.",        # 8 words
               version="v5.5.0", os="Android 14", severity="critical", component="login",
               fix="Fix the hang in the login submit handler.")                          # 8 words

# --- t01-v3: payment button greyed out, v1.1.1 on macOS 14 ---------------------------------------
G_T01V3 = dict(bug="Payment button is greyed out after moving to v1.1.1.",              # 9 words
               impact="Account managers cannot process invoices, stopping revenue flow.",  # 8 words
               version="v1.1.1", os="macOS 14", severity="critical", component="payments",
               fix="Re-enable the payment button state after the update.")               # 8 words

# --- t05-v1: 3*125.55=376.65, 5*12.99=64.95 -> subtotal 441.60 (> 200) -> discount 10% = 44.16;
#             taxable 441.60-44.16=397.44; tax 397.44*0.08=31.7952 -> 31.80; total 397.44+31.80=429.24
G_T05V1 = dict(vendor="Global Tech Ltd.", invoice="INV-8821", subtotal="441.60", discount="44.16",
               tax="31.80", total="429.24")

# --- t06-v2: soup 2 -> 5, factor 2.5: broth 150*2.5=375.0 ml; chili 10*2.5=25.0 g;
#             potato 800*2.5=2000 g -> 2.0 kg; onion 200*2.5=500.0 g ---------------------------------
G_T06V2 = (TABLE_HEAD + "| broth | 150 ml | 375.0 ml |\n| chili | 10 g | 25.0 g |\n"
           "| potato | 800 g | 2.0 kg |\n| onion | 200 g | 500.0 g |\nScale factor: 2.5")

# --- t07-v2: lands 14:20 + 45 = 15:05 leave; + 1h05 = 16:10 arrive; after 15:00 so check-in 16:10;
#             16:10 -> 19:30 = 3h20 = 200 minutes ------------------------------------------------
G_T07V2 = "Leave airport: 15:05\nHotel arrival: 16:10\nCheck-in: 16:10\nFree minutes before dinner: 200"

# --- t07-v3: lands 14:45 + 45 = 15:30 leave; + 15 = 15:45 arrive; check-in 15:45;
#             15:45 -> 19:30 = 3h45 = 225 minutes ------------------------------------------------
G_T07V3 = "Leave airport: 15:30\nHotel arrival: 15:45\nCheck-in: 15:45\nFree minutes before dinner: 225"

# --- t08-v3: stew 2 -> 20, factor 10: beef 1500*10=15000 g -> 15.0 kg; potatoes 500*10=5000 g -> 5.0 kg;
#             onions 100*10=1000 g (>= 1000) -> 1.0 kg; soy sauce 10*10=100.0 ml ----------------------
G_T08V3 = (TABLE_HEAD + "| beef | 1500 g | 15.0 kg |\n| potatoes | 500 g | 5.0 kg |\n"
           "| onions | 100 g | 1.0 kg |\n| soy sauce | 10 ml | 100.0 ml |\nScale factor: 10")


GOLDEN_GENERATED = {
    "t01-v2": {
        "good": [j(**G_T01V2), "```json\n" + j(**G_T01V2) + "\n```"],
        "bad": [
            (json.dumps({k: v for k, v in G_T01V2.items() if k != "fix"}), {"c1"}),       # missing key
            (with_(G_T01V2, extra="x"), {"c1"}),                                           # extra key
            (with_(G_T01V2, version="5.5.0"), {"c2"}),                                     # no leading v
            (with_(G_T01V2, version="v5.5"), {"c2"}),
            (with_(G_T01V2, bug="The login screen of the mobile application hangs completely whenever a user "
                                "taps the Submit button on Android 14"), {"c3"}),           # 19 words
            (with_(G_T01V2, impact="Users are unable to access their accounts at all and the company has about "
                                   "five hundred users who are now blocked"), {"c4"}),     # 20 words
            (with_(G_T01V2, severity="high"), {"c5"}),
            (with_(G_T01V2, severity="Critical"), {"c5"}),                                 # case matters
            ("The login screen hangs on Android 14.", ALL5),                              # not JSON
        ],
    },
    "t01-v3": {
        "good": [j(**G_T01V3), with_(G_T01V3, component="Payments"), "```json\n" + j(**G_T01V3) + "\n```"],
        "bad": [
            ("Payment button greyed out on macOS 14.", ALL5),                              # not JSON
            (with_(G_T01V3, component="billing"), {"c2"}),
            (with_(G_T01V3, fix="Just restart the payment service."), {"c3"}),
            (with_(G_T01V3, fix="Fix the payment button handler so that it is enabled again for all account "
                                "managers after the update"), {"c4"}),                      # 18 words
            (with_(G_T01V3, impact="The payment button is greyed out."), {"c5"}),
        ],
    },
    "t05-v1": {
        "good": [j(**G_T05V1), "```json\n" + j(**G_T05V1) + "\n```"],
        "bad": [
            (j(**G_T05V1)[:-1], ALL5 | {"c6", "c7"}),                                      # broken JSON
            (with_(G_T05V1, currency="USD"), {"c2"}),
            (with_(G_T05V1, invoice="8821"), {"c3"}),
            (with_(G_T05V1, subtotal="441.00"), {"c4"}),
            (with_(G_T05V1, discount="0.00"), {"c5"}),                                     # forgot the discount
            (with_(G_T05V1, tax="31.79"), {"c6"}),
            (with_(G_T05V1, total="429.25"), {"c7"}),
        ],
    },
    "t06-v2": {
        "good": [G_T06V2, "```\n" + G_T06V2 + "\n```"],
        "bad": [
            (G_T06V2.replace("375.0 ml", "375 ml"), {"c1"}),
            (G_T06V2.replace("2.0 kg", "2000.0 g"), {"c2"}),                               # kg conversion missed
            (G_T06V2.replace("500.0 g", "500 g"), {"c3"}),
            (G_T06V2.replace("Scale factor: 2.5", "Scale factor: 2.50"), {"c4"}),
            (G_T06V2 + "\nEnjoy!", {"c4"}),                                                # text after the factor line
        ],
    },
    "t07-v2": {
        "good": [G_T07V2,
                 "\n\n" + G_T07V2 + "\n\n",                                                # surrounding blank lines
                 "  " + G_T07V2 + "   \n",                                                 # surrounding spaces
                 "```\n" + G_T07V2 + "\n```"],
        "bad": [
            (G_T07V2.replace("15:05", "15:20"), {"c1"}),
            (G_T07V2.replace("16:10\nCheck", "16:00\nCheck"), {"c2"}),
            (G_T07V2.replace("Check-in: 16:10", "Check-in: 15:00"), {"c3"}),
            (G_T07V2.replace("200", "190"), {"c4"}),
            ("Here is your plan:\n" + G_T07V2, {"c5"}),                                    # 5 lines
            (G_T07V2.replace("\nHotel", "\n\nHotel"), {"c5"}),                             # blank line inside
            (G_T07V2 + "\nEnjoy the trip", {"c5"}),
        ],
    },
    "t07-v3": {
        "good": [G_T07V3, "```\n" + G_T07V3 + "\n```"],
        "bad": [
            (G_T07V3.replace("15:30", "15:15"), {"c1"}),
            (G_T07V3.replace("Hotel arrival: 15:45", "Hotel arrival: 15:50"), {"c2"}),
            (G_T07V3.replace("Check-in: 15:45", "Check-in: 15:00"), {"c3"}),
            (G_T07V3.replace("225", "270"), {"c4"}),
            ("Leave airport: 15:30\nCheck-in: 15:45\nHotel arrival: 15:45\nFree minutes before dinner: 225", {"c5"}),
        ],
    },
    "t08-v3": {
        "good": [G_T08V3, G_T08V3.replace("Scale factor: 10", "Scale factor: 10.0"), "```\n" + G_T08V3 + "\n```"],
        "bad": [
            (G_T08V3.replace("| beef | 1500 g | 15.0 kg |", "| beef | 1500 g | 15000.0 g |"), {"c1"}),
            (G_T08V3.replace("| potatoes | 500 g | 5.0 kg |", "| potatoes | 500 g | 5000.0 g |"), {"c2"}),
            (G_T08V3.replace("| onions | 100 g | 1.0 kg |", "| onions | 100 g | 1000.0 g |"), {"c3"}),
            (G_T08V3.replace("| soy sauce | 10 ml | 100.0 ml |", "| soy sauce | 10 ml | 100 ml |"), {"c4"}),
            (G_T08V3.replace("Scale factor: 10", "Scale factor: 10.5"), {"c5"}),
            (G_T08V3.replace("Scale factor: 10", "Scale factor: 1"), {"c5"}),
            (G_T08V3 + "\nDone", {"c5"}),
        ],
    },
}
