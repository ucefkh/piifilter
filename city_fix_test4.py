#!/usr/bin/env python3
"""Test further refined city patterns."""
import re

# Pattern A: City before state/postcode — lookahead for ", STATE ZIP" or ", POSTCODE"
# No strict lookbehind requirement — the lookahead itself is a strong signal
# But block specific FPs: "Avenue", "Street", "Road", "Drive" etc. as city names
pat_a = r"\b(?!(?:Avenue|Ave|Street|St|Road|Rd|Drive|Dr|Lane|Ln|Boulevard|Blvd|Way|Place|Pl|Court|Ct|Square|Sq|Circle|Cir|Park|Parkway|Pkwy|Highway|Hwy|Suite|Ste|Room|Rm|Floor|Fl|Dept|Department|Building|Bldg|Center|Centre|Institute|School|College|University|Hospital|Hotel|Church|Bank|Store|Shop|Market|Mall|Club|House|Home|Lab|Laboratory|Studio|Office|Factory|Warehouse|Station|Terminal|Airport|Port|Dock|Marina|Resort|Spa|Garden|Zoo|Museum|Gallery|Theater|Theatre|Cinema|Stadium|Arena|Gym|Cafe|Bar|Pub|Restaurant|Bakery|Pharmacy|Clinic|Dental|Veterinary|Grocery|Boutique|Salon|Nail|Barber|Tailor|Cleaner|Laundry|Repair|Garage|Service|Depot|Hub|Node|Site|Location|Venue|Area|Zone|Region|District|January|February|March|April|May|June|July|August|September|October|November|December|Spring|Summer|Autumn|Winter|Red|Blue|Green|Yellow|Black|White|Gray|Grey|Brown|Orange|Purple|Pink|Violet|Indigo|Gold|Silver|Bronze|Platinum|Diamond|Ruby|Emerald|Sapphire|Jade|Coral|Ivory|Azure|Crimson|Scarlet|Mathematics|Physics|Chemistry|Biology|Geology|Astronomy|Economics|Philosophy|Psychology|Sociology|Literature|Geography|Politics|Law|Engineering|Computing|Medicine|Nursing|Pharmacy|Dentistry|Architecture|Business|Finance|Accounting|Marketing|Design|Education|Training|Learning|Teaching|Coaching|Mentoring|Consulting|Planning|Strategy|Operations|Logistics|Procurement|Desk|Lab|Workshop|Institute|Academy|School|College|University|Department|Division|Section|Unit|Team|Group|Committee|Council|Board|Authority|Agency|Bureau|Office|Ministry|Commission|Foundation|Association|Society|Union|League|Club)\\b)(?:[A-Z][a-z]+(?:[ -]+[A-Z][a-z]+)?)(?=\s*,\s*(?:[A-Z]{2}(?:\s+\d{5}(?:-\d{4})?)?|[A-Z]{1,2}\d{1,2}[A-Z]?\s+\d[A-Z]{2}))"

# Pattern B: Same as before — well-known capital/major cities at start followed by verb
pat_b = r"\b(?:Paris|London|Berlin|Tokyo|Beijing|Delhi|Moscow|Rome|Madrid|Oslo|Stockholm|Helsinki|Copenhagen|Amsterdam|Brussels|Vienna|Prague|Warsaw|Budapest|Dublin|Lisbon|Athens|Seoul|Bangkok|Jakarta|Hanoi|Dubai|Istanbul|Cairo|Jerusalem|Riyadh|Singapore|Manila|Kuala Lumpur)(?=\s+(?:has|is|was|lies|sits|became|remains|serves|boasts|encompasses|covers|spans|welcomes|hosts|attracts))"

texts = [
    ("FN1", "Our office is at 350 Fifth Avenue, New York, NY 10118"),
    ("FN2", "Paris has a population of over 2 million people and is the capital of France."),
    ("FN3", "Visit us at 10 Downing Street, London, SW1A 2AA"),
    ("OK2", "Visit New York, NY 10001 for the conference"),
    ("OK4", "located in London, SW1A 1AA at the Houses of Parliament"),
    ("OK5", "Berlin is the capital of Germany"),
    ("OK6", "Tokyo has hosted the Olympics multiple times."),
    ("FP1", "The Paris office is located at 123 Rue de Rivoli"),
    ("FP2", "London is not the capital"),
    ("FP3", "Spring has arrived early this year"),
    ("FP4", "Summer is my favorite season"),
    ("FP5", "Berlin has a great subway system"),
    ("FP6", "James has been working at Microsoft"),
    ("FP7", "Paris is known for..."),
    # Additional edge cases
    ("FP8", "Let me check Fifth Avenue, NY 10001 for the address"),  # "Fifth Avenue" should NOT be CITY
    ("FP9", "The Study has been completed."),  # "Study" capitalized before "has"
    ("FP10", "Support has been great."),
    ("FP11", "We visited the Office, NY 10001 yesterday"),  # "Office" in negative list
]

for label, text in texts:
    print(f"\n--- {label}: '{text}' ---")
    for name, pat, conf in [("A", pat_a, 0.55), ("B", pat_b, 0.65)]:
        try:
            for m in re.finditer(pat, text):
                print(f"  [{name}] '{m.group()}' [{m.start()}:{m.end()}] conf={conf:.2f}")
        except re.error as e:
            print(f"  [{name}] ERROR: {e}")