#!/usr/bin/env python3
"""Test proposed patterns against ALL dataset examples to check for new FPs."""
import sys, re, json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

# Load dataset
with open(str(PROJECT_ROOT / "benchmarks" / "data" / "pii_dataset.json")) as f:
    data = json.load(f)
examples = data["examples"] if isinstance(data, dict) and "examples" in data else data

states = "AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC"

blocked = "Office|Offices|Suite|Room|Rm|Floor|Fl|Dept|Department|Building|Bldg|Center|Centre|Institute|School|College|University|Hospital|Hotel|Church|Bank|Store|Shop|Market|Mall|Club|House|Home|Lab|Laboratory|Studio|Factory|Warehouse|Station|Terminal|Airport|Port|Dock|Marina|Resort|Spa|Garden|Park|Zoo|Museum|Gallery|Theater|Theatre|Cinema|Stadium|Arena|Gym|Cafe|Bar|Pub|Restaurant|Bakery|Pharmacy|Clinic|January|February|March|April|May|June|July|August|September|October|November|December|Spring|Summer|Autumn|Winter|Red|Blue|Green|Yellow|Black|White|Gray|Grey|Brown|Orange|Purple|Pink|Violet|Indigo|Gold|Silver|Bronze|Platinum|Diamond|Ruby|Emerald|Sapphire|Jade|Coral|Ivory|Azure|Crimson|Scarlet|Mathematics|Physics|Chemistry|Biology|Geology|Astronomy|Economics|Philosophy|Psychology|Sociology|Literature|Geography|Politics|Law|Engineering|Computing|Medicine|Nursing|Pharmacy|Dentistry|Architecture|Business|Finance|Accounting|Marketing|Design|Education|Training|Learning|Teaching|Coaching|Mentoring|Consulting|Planning|Strategy|Operations|Logistics|Procurement|Desk|Lab|Workshop|Institute|Academy|School|College|University|Department|Division|Section|Unit|Team|Group|Committee|Council|Board|Authority|Agency|Bureau|Ministry|Commission|Foundation|Association|Society|Union|League|Club|Config|Configuration|Settings|Options|Preferences|Admin|Administrator|System|Dashboard|Profile|Account|General|Security|Network|Users|Groups|Roles|Permissions|Logs|Backup|Notifications|Integrations|Plugins|Extensions|Appearance|Layout|Theme|Support|Manager|Management|Report|Reports|Analytics|Statistics|Overview|Summary|Details|Editor|Viewer|Designer|Developer|Engineer|Moderator|Contributor|Maintenance|Upgrade|Update|Installation|Deployment|Release|Version|Testing|Review|Approval|Approved|Rejected|Pending|Status|Progress|Complete|Finished|Canceled|Failed|Error|Warning|Info|Success|Critical|Alert|Debug|Trace|Monitor|Metrics|Logging|Audit|Access|Control|Policy|Rule|Rules|Template|Templates|Workflow|Pipeline|Queue|Schedule|Calendar|Agenda|Invoice|Order|Transaction|Payment|Shipping|Billing|Tax|Nature|Science|General|Practice|Theory|Process|Public|Private|Common|Research|Development|Text|Mode|Here|There|This|That|These|Those|The|A|An|All|Some|Many|Both|Each|Every|Few|More|Most|Other|Such|Same|Just|Also|Very|Too|Quite|Well|Now|Then|Than|Into|Upon|Under|Over|Again|Before|After|Until|During|Since|About|Between|Through|Because|North|South|East|West|Northeast|Northwest|Southeast|Southwest|Northern|Southern|Eastern|Western|Central|Upper|Lower|Mid|Inner|Outer|Forward|Backward|Upward|Downward|Internal|External|Left|Right|Top|Bottom|Front|Back|Side|End|Edge|Corner|Middle|Heart|Core|Base|Basis|Ground|Floor|Level|Layer|Tier|Phase|Stage|Step|Point|Spot|Site|Area|Zone|Sector|Region|District|Quarter|Block|Lot|Plot|Field|Track|Line|Row|Column|Node|End|Location|Place|Space|Mark|Sign|Symbol|Icon|Logo|Image|Picture|Photo|Graphic|Art|Design|Pattern|Model|Style|Type|Form|Kind|Sort|Class|Category|Set|Series|Range|Scale|Rate|Degree|Grade|Rank|Status|State|Condition|Position|Role|Function|Task|Job|Work|Duty|Charge|Mission|Operation|Action|Activity|Process|Procedure|Method|Approach|Technique|System|Scheme|Plan|Program|Project|Initiative|Campaign|Drive|Push|Effort|Attempt|Try|Trial|Test|Experiment|Study|Survey|Poll|Census|Count|Tally|Total|Sum|Amount|Number|Figure|Digit|Value|Quantity|Measure|Metric|Index|Indicator|Test|Assessment|Evaluation|Judgment|Rating|Score|Grade|Mark|Label|Brand|Tag|Title|Term|Source|Origin|Root|Cause|Reason|Basis|Ground|Foundation|Path|Route|Course|Channel|Track|Lane|Alley|Passage|Corridor|Hall|Window|Gate|Entrance|Exit|Door|Wall|Ceiling|Roof|Capacity|Size|Dimension|Length|Width|Height|Depth|Breadth|Span|Range|Scope|Extent|Scale|Standard|Norm|Criterion|Benchmark|Baseline|Threshold|Cutoff|Meeting|Conference|Summit|Forum|Seminar|Workshop|Symposium|Convention|Congress|Assembly|Gathering|Meetup|Event|Function|Gala|Ceremony|Tradition|Custom|Convention|Practice|Norm|Standard|Rule|Code|Law|Regulation|Statute|Ordinance|Decree|Edict|Mandate|Order|Command|Instruction|Direction|Guideline|Requirement|Specification|Protocol|Procedure|Policy|Principle|Doctrine|Tenet|Maxim|Axiom|Truth|Fact|Reality|Certainty|Absolute|Given|Constant|Variable|Parameter|Factor|Element|Component|Part|Piece|Segment|Section|Portion|Fraction|Division|Subdivision|Category|Class|Group|Set|Collection|Assembly|Cluster|Batch|Bunch|Pack|Bundle|Stack|Heap|Pile|Mass|Volume|Bulk|Majority|Minority|Plurality|Multitude|Array|Range|Variety|Diversity|Selection|Choice|Option|Alternative|Possibility|Opportunity|Chance|Risk|Threat|Danger|Hazard|Peril|Jeopardy|Crisis|Emergency|Disaster|Catastrophe|Calamity|Tragedy|Accident|Incident|Occurrence|Happening|Phenomenon|Situation|Circumstance|Condition|Context|Environment|Setting|Atmosphere|Ambiance|Mood|Tone|Feeling|Sense|Impression|Effect|Impact|Influence|Result|Outcome|Consequence|Product|Fruit|Reward|Benefit|Gain|Profit|Advantage|Edge|Lead|Headway|Progress|Advancement|Development|Evolution|Growth|Expansion|Extension|Enlargement|Increase|Rise|Surge|Boost|Jump|Leap|Bound|Spurt|Burst|Flash|Blast|Explosion|Eruption|Outburst|Outbreak|Epidemic|Pandemic|Plague|Scourge|Curse|Avenue|Ave|Street|St|Road|Rd|Drive|Dr|Lane|Ln|Boulevard|Blvd|Way|Place|Pl|Court|Ct|Square|Sq|Circle|Cir|Park|Pkwy|Parkway|Highway|Hwy"

# New patterns
pat_a1 = r"\b(?!(?:" + blocked + r")\b)[A-Z][a-z]{2,}(?:\s+(?!" + blocked + r"\b)[A-Z][a-z]+)?(?=\s*,\s*(?:" + states + r")(?:\s+\d{5}(?:-\d{4})?)?\b)"
pat_a2 = r"\b(?!(?:" + blocked + r")\b)[A-Z][a-z]{2,}(?=\s*,\s*[A-Z]{1,2}\d{1,2}[A-Z]?\s+\d[A-Z]{2}\b)"
pat_b = r"\b(?:Paris|London|Berlin|Tokyo|Beijing|Delhi|Moscow|Rome|Madrid|Oslo|Stockholm|Helsinki|Copenhagen|Amsterdam|Brussels|Vienna|Prague|Warsaw|Budapest|Dublin|Lisbon|Athens|Seoul|Bangkok|Jakarta|Hanoi|Dubai|Istanbul|Cairo|Jerusalem|Riyadh|Singapore|Manila|Kuala Lumpur)(?=\s+(?:has|is|was|lies|sits|became|remains|serves|boasts|encompasses|covers|spans|welcomes|hosts|attracts))"

new_patterns = [("CITY_ADDR_US", pat_a1, 0.55), ("CITY_ADDR_UK", pat_a2, 0.55), ("CITY_MAJOR_SBJ", pat_b, 0.65)]

# Test all examples
print("Testing new patterns against all", len(examples), "examples...")
total_new_fps = 0
for i, ex in enumerate(examples):
    text = ex["text"]
    expected_cities = [e for e in ex.get("entities", []) if e["type"] == "CITY"]
    
    for name, pat, conf in new_patterns:
        try:
            for m in re.finditer(pat, text):
                # Check if this match is an expected CITY
                is_expected = any(m.start() == e["start"] and m.end() == e["end"] for e in expected_cities)
                if not is_expected:
                    total_new_fps += 1
                    print(f"  NEW FP [{i}] '{name}': '{m.group()}' [{m.start()}:{m.end()}] in: '{text}'")
        except re.error as e:
            print(f"  [{i}] ERROR in {name}: {e}")

print(f"\nTotal new FPs from proposed patterns: {total_new_fps}")

# Also check which FNs are now matched
print("\nChecking FN coverage:")
for i, ex in enumerate(examples):
    text = ex["text"]
    expected_cities = [e for e in ex.get("entities", []) if e["type"] == "CITY"]
    if not expected_cities:
        continue
    
    matched_expected = set()
    for name, pat, conf in new_patterns:
        try:
            for m in re.finditer(pat, text):
                for e in expected_cities:
                    if m.start() == e["start"] and m.end() == e["end"]:
                        matched_expected.add((e["start"], e["end"]))
        except re.error:
            pass
    
    for e in expected_cities:
        if (e["start"], e["end"]) in matched_expected:
            print(f"  NEW MATCH [{i}]: '{e['value']}' [{e['start']}:{e['end']}] in: '{text}'")