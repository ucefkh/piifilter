#!/usr/bin/env python3
"""Refined address-city pattern with check that last word isn't a street/location."""
import re

# Known US state abbreviations
states = "AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC"

# Pattern A: City before US state + ZIP
# Only match if the word(s) don't end with a street/location suffix OR start with a blocked word
street_suffixes = "Avenue|Street|Road|Drive|Lane|Boulevard|Way|Place|Court|Square|Circle|Parkway|Highway|Suite|Room|Floor|Department|Building|Center|Centre|Institute|School|College|University|Hospital|Hotel|Church|Bank|Store|Shop|Market|Mall|Club|House|Home|Lab|Laboratory|Studio|Office|Factory|Warehouse|Station|Terminal|Airport|Port|Dock|Marina|Resort|Spa|Garden|Zoo|Museum|Gallery|Theater|Theatre|Cinema|Stadium|Arena|Gym|Cafe|Bar|Pub|Restaurant|Bakery|Pharmacy|Clinic|Dental|Veterinary|Grocery|Boutique|Salon|Nail|Barber|Tailor|Cleaner|Laundry|Repair|Garage|Service|Depot|Hub|Node|Site|Location|Venue|Area|Zone|Region|District|January|February|March|April|May|June|July|August|September|October|November|December|Spring|Summer|Autumn|Winter|Red|Blue|Green|Yellow|Black|White|Gray|Grey|Brown|Orange|Purple|Pink|Violet|Indigo|Gold|Silver|Bronze|Platinum|Diamond|Ruby|Emerald|Sapphire|Jade|Coral|Ivory|Azure|Crimson|Scarlet|Mathematics|Physics|Chemistry|Biology|Geology|Astronomy|Economics|Philosophy|Psychology|Sociology|Literature|Geography|Politics|Law|Engineering|Computing|Medicine|Nursing|Pharmacy|Dentistry|Architecture|Business|Finance|Accounting|Marketing|Design|Education|Training|Learning|Teaching|Coaching|Mentoring|Consulting|Planning|Strategy|Operations|Logistics|Procurement|Desk|Lab|Workshop|Institute|Academy|School|College|University|Department|Division|Section|Unit|Team|Group|Committee|Council|Board|Authority|Agency|Bureau|Office|Ministry|Commission|Foundation|Association|Society|Union|League|Club|Config|Configuration|Settings|Options|Preferences|Admin|Administrator|System|Dashboard|Profile|Account|General|Security|Network|Users|Groups|Roles|Permissions|Logs|Backup|Notifications|Integrations|Plugins|Extensions|Appearance|Layout|Theme|Support|Manager|Management|Report|Reports|Analytics|Statistics|Overview|Summary|Details|Editor|Viewer|Designer|Developer|Engineer|Moderator|Contributor|Maintenance|Upgrade|Update|Installation|Deployment|Release|Version|Testing|Review|Approval|Approved|Rejected|Pending|Status|Progress|Complete|Finished|Canceled|Failed|Error|Warning|Info|Success|Critical|Alert|Debug|Trace|Monitor|Metrics|Logging|Audit|Access|Control|Policy|Rule|Rules|Template|Templates|Workflow|Pipeline|Queue|Schedule|Calendar|Agenda|Invoice|Order|Transaction|Payment|Shipping|Billing|Tax"

# Only match single-word city name, or two-word city but neither word is a street/location suffix
# Use negative lookbehind for the LAST word: not a street suffix
pat_a = r"\b(?!(?:" + street_suffixes + r")\b)[A-Z][a-z]+(?:\s+(?!" + street_suffixes + r"\b)[A-Z][a-z]+)?(?=\s*,\s*(?:" + states + r")(?:\s+\d{5}(?:-\d{4})?)?\b)"

# Pattern A2: City before UK postcode — must be a common city name or start-of-sentence
# UK postcodes: SW1A 2AA format
pat_a2 = r"\b[A-Z][a-z]{2,}(?=\s*,\s*[A-Z]{1,2}\d{1,2}[A-Z]?\s+\d[A-Z]{2}\b)"

# Don't match if the city candidate is a known non-city word
pat_a2_blocked = r"\b(?!(?:Office|Suite|Room|Floor|Dept|Department|Building|Bldg|Center|Centre|Institute|School|College|University|Hospital|Hotel|Church|Bank|Store|Shop|Market|Mall|Club|House|Home|Lab|Laboratory|Studio|Factory|Warehouse|Station|Terminal|Airport|Port|Dock|Marina|Resort|Spa|Garden|Park|Zoo|Museum|Gallery|Theater|Theatre|Cinema|Stadium|Arena|Gym|Cafe|Bar|Pub|Restaurant|Bakery|Pharmacy|Clinic|January|February|March|April|May|June|July|August|September|October|November|December|Spring|Summer|Autumn|Winter|Red|Blue|Green|Yellow|Black|White|Gray|Grey|Brown|Orange|Purple|Pink|Violet|Indigo|Gold|Silver|Bronze|Platinum|Diamond|Ruby|Emerald|Sapphire|Jade|Coral|Ivory|Azure|Crimson|Scarlet|Mathematics|Physics|Chemistry|Biology|Geology|Astronomy|Economics|Philosophy|Psychology|Sociology|Literature|Geography|Politics|Law|Engineering|Computing|Medicine|Nursing|Pharmacy|Dentistry|Architecture|Business|Finance|Accounting|Marketing|Design|Education|Training|Learning|Teaching|Coaching|Mentoring|Consulting|Planning|Strategy|Operations|Logistics|Procurement|Desk|Lab|Workshop|Institute|Academy|School|College|University|Department|Division|Section|Unit|Team|Group|Committee|Council|Board|Authority|Agency|Bureau|Ministry|Commission|Foundation|Association|Society|Union|League|Club|Config|Configuration|Settings|Options|Preferences|Admin|Administrator|System|Dashboard|Profile|Account|General|Security|Network|Users|Groups|Roles|Permissions|Logs|Backup|Notifications|Integrations|Plugins|Extensions|Appearance|Layout|Theme|Support|Manager|Management|Report|Reports|Analytics|Statistics|Overview|Summary|Details|Editor|Viewer|Designer|Developer|Engineer|Moderator|Contributor|Maintenance|Upgrade|Update|Installation|Deployment|Release|Version|Testing|Review|Approval|Approved|Rejected|Pending|Status|Progress|Complete|Finished|Canceled|Failed|Error|Warning|Info|Success|Critical|Alert|Debug|Trace|Monitor|Metrics|Logging|Audit|Access|Control|Policy|Rule|Rules|Template|Templates|Workflow|Pipeline|Queue|Schedule|Calendar|Agenda|Invoice|Order|Transaction|Payment|Shipping|Billing|Tax)\b)[A-Z][a-z]{2,}(?=\s*,\s*[A-Z]{1,2}\d{1,2}[A-Z]?\s+\d[A-Z]{2}\b)"

texts = [
    ("FN1", "Our office is at 350 Fifth Avenue, New York, NY 10118"),
    ("FN2", "Paris has a population of over 2 million people and is the capital of France."),
    ("FN3", "Visit us at 10 Downing Street, London, SW1A 2AA"),
    ("OK2", "Visit New York, NY 10001 for the conference"),
    ("OK4", "located in London, SW1A 1AA at the Houses of Parliament"),
    ("OK5", "Berlin is the capital of Germany"),
    ("OK6", "Tokyo has hosted the Olympics multiple times."),
    ("FP1", "The Paris office is located at 123 Rue de Rivoli"),
    ("FP3", "Spring has arrived early this year"),
    ("FP8", "Fifth Avenue, NY 10001 is a famous street"),
    ("FP11", "Office, NY 10001"),
    ("FP16", "Dashboard has been loaded"),
    ("FP17", "Settings, NY 10001 is not a real place"),
    ("FP18", "I visited New York, NY last year"),
    ("FP19", "Berlin, Germany is the capital"),  # country after comma, not US state — should NOT match A1
]

for label, text in texts:
    print(f"\n--- {label}: '{text}' ---")
    for name, pat, conf in [("A1", pat_a, 0.55), ("A2", pat_a2_blocked, 0.55), ("B", pat_b, 0.65)]:
        try:
            for m in re.finditer(pat, text):
                print(f"  [{name}] '{m.group()}' [{m.start()}:{m.end()}] conf={conf:.2f}")
        except re.error as e:
            print(f"  [{name}] ERROR: {e}")