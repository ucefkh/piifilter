#!/usr/bin/env python3
"""Fix: add street suffixes to blocked list for single-word city detection."""
import re

# Known US state abbreviations
states = "AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC"

# Blocked words (including street suffixes) that should never be treated as city names
blocked = "Office|Offices|Suite|Room|Rm|Floor|Fl|Dept|Department|Building|Bldg|Center|Centre|Institute|School|College|University|Hospital|Hotel|Church|Bank|Store|Shop|Market|Mall|Club|House|Home|Lab|Laboratory|Studio|Factory|Warehouse|Station|Terminal|Airport|Port|Dock|Marina|Resort|Spa|Garden|Park|Zoo|Museum|Gallery|Theater|Theatre|Cinema|Stadium|Arena|Gym|Cafe|Bar|Pub|Restaurant|Bakery|Pharmacy|Clinic|January|February|March|April|May|June|July|August|September|October|November|December|Spring|Summer|Autumn|Winter|Red|Blue|Green|Yellow|Black|White|Gray|Grey|Brown|Orange|Purple|Pink|Violet|Indigo|Gold|Silver|Bronze|Platinum|Diamond|Ruby|Emerald|Sapphire|Jade|Coral|Ivory|Azure|Crimson|Scarlet|Mathematics|Physics|Chemistry|Biology|Geology|Astronomy|Economics|Philosophy|Psychology|Sociology|Literature|Geography|Politics|Law|Engineering|Computing|Medicine|Nursing|Pharmacy|Dentistry|Architecture|Business|Finance|Accounting|Marketing|Design|Education|Training|Learning|Teaching|Coaching|Mentoring|Consulting|Planning|Strategy|Operations|Logistics|Procurement|Desk|Lab|Workshop|Institute|Academy|School|College|University|Department|Division|Section|Unit|Team|Group|Committee|Council|Board|Authority|Agency|Bureau|Ministry|Commission|Foundation|Association|Society|Union|League|Club|Config|Configuration|Settings|Options|Preferences|Admin|Administrator|System|Dashboard|Profile|Account|General|Security|Network|Users|Groups|Roles|Permissions|Logs|Backup|Notifications|Integrations|Plugins|Extensions|Appearance|Layout|Theme|Support|Manager|Management|Report|Reports|Analytics|Statistics|Overview|Summary|Details|Editor|Viewer|Designer|Developer|Engineer|Moderator|Contributor|Maintenance|Upgrade|Update|Installation|Deployment|Release|Version|Testing|Review|Approval|Approved|Rejected|Pending|Status|Progress|Complete|Finished|Canceled|Failed|Error|Warning|Info|Success|Critical|Alert|Debug|Trace|Monitor|Metrics|Logging|Audit|Access|Control|Policy|Rule|Rules|Template|Templates|Workflow|Pipeline|Queue|Schedule|Calendar|Agenda|Invoice|Order|Transaction|Payment|Shipping|Billing|Tax|Nature|Science|General|Practice|Theory|Process|Public|Private|Common|Research|Development|Text|Mode|Here|There|This|That|These|Those|The|A|An|All|Some|Many|Both|Each|Every|Few|More|Most|Other|Such|Same|Just|Also|Very|Too|Quite|Well|Now|Then|Than|Into|Upon|Under|Over|Again|Before|After|Until|During|Since|About|Between|Through|Because|North|South|East|West|Northeast|Northwest|Southeast|Southwest|Northern|Southern|Eastern|Western|Central|Upper|Lower|Mid|Inner|Outer|Forward|Backward|Upward|Downward|Internal|External|Left|Right|Top|Bottom|Front|Back|Side|End|Edge|Corner|Middle|Heart|Core|Base|Basis|Ground|Floor|Level|Layer|Tier|Phase|Stage|Step|Point|Spot|Site|Area|Zone|Sector|Region|District|Quarter|Block|Lot|Plot|Field|Track|Line|Row|Column|Node|End|Location|Place|Space|Mark|Sign|Symbol|Icon|Logo|Image|Picture|Photo|Graphic|Art|Design|Pattern|Model|Style|Type|Form|Kind|Sort|Class|Category|Set|Series|Range|Scale|Rate|Degree|Grade|Rank|Status|State|Condition|Position|Role|Function|Task|Job|Work|Duty|Charge|Mission|Operation|Action|Activity|Process|Procedure|Method|Approach|Technique|System|Scheme|Plan|Program|Project|Initiative|Campaign|Drive|Push|Effort|Attempt|Try|Trial|Test|Experiment|Study|Survey|Poll|Census|Count|Tally|Total|Sum|Amount|Number|Figure|Digit|Value|Quantity|Measure|Metric|Index|Indicator|Test|Assessment|Evaluation|Judgment|Rating|Score|Grade|Mark|Label|Brand|Tag|Title|Term|Source|Origin|Root|Cause|Reason|Basis|Ground|Foundation|Path|Route|Course|Channel|Track|Lane|Alley|Passage|Corridor|Hall|Window|Gate|Entrance|Exit|Door|Wall|Ceiling|Roof|Capacity|Size|Dimension|Length|Width|Height|Depth|Breadth|Span|Range|Scope|Extent|Scale|Standard|Norm|Criterion|Benchmark|Baseline|Threshold|Cutoff|Meeting|Conference|Summit|Forum|Seminar|Workshop|Symposium|Convention|Congress|Assembly|Gathering|Meetup|Event|Function|Gala|Ceremony|Tradition|Custom|Convention|Practice|Norm|Standard|Rule|Code|Law|Regulation|Statute|Ordinance|Decree|Edict|Mandate|Order|Command|Instruction|Direction|Guideline|Requirement|Specification|Protocol|Procedure|Policy|Principle|Doctrine|Tenet|Maxim|Axiom|Truth|Fact|Reality|Certainty|Absolute|Given|Constant|Variable|Parameter|Factor|Element|Component|Part|Piece|Segment|Section|Portion|Fraction|Division|Subdivision|Category|Class|Group|Set|Collection|Assembly|Cluster|Batch|Bunch|Pack|Bundle|Stack|Heap|Pile|Mass|Volume|Bulk|Majority|Minority|Plurality|Multitude|Array|Range|Variety|Diversity|Selection|Choice|Option|Alternative|Possibility|Opportunity|Chance|Risk|Threat|Danger|Hazard|Peril|Jeopardy|Crisis|Emergency|Disaster|Catastrophe|Calamity|Tragedy|Accident|Incident|Occurrence|Happening|Phenomenon|Situation|Circumstance|Condition|Context|Environment|Setting|Atmosphere|Ambiance|Mood|Tone|Feeling|Sense|Impression|Effect|Impact|Influence|Result|Outcome|Consequence|Product|Fruit|Reward|Benefit|Gain|Profit|Advantage|Edge|Lead|Headway|Progress|Advancement|Development|Evolution|Growth|Expansion|Extension|Enlargement|Increase|Rise|Surge|Boost|Jump|Leap|Bound|Spurt|Burst|Flash|Blast|Explosion|Eruption|Outburst|Outbreak|Epidemic|Pandemic|Plague|Scourge|Curse|Avenue|Ave|Street|St|Road|Rd|Drive|Dr|Lane|Ln|Boulevard|Blvd|Way|Place|Pl|Court|Ct|Square|Sq|Circle|Cir|Park|Pkwy|Parkway|Highway|Hwy"

# Pattern A1: City before US state + ZIP
pat_a = r"\b(?!(?:" + blocked + r")\b)[A-Z][a-z]{2,}(?:\s+(?!" + blocked + r"\b)[A-Z][a-z]+)?(?=\s*,\s*(?:" + states + r")(?:\s+\d{5}(?:-\d{4})?)?\b)"

# Pattern A2: City before UK postcode
pat_a2 = r"\b(?!(?:" + blocked + r")\b)[A-Z][a-z]{2,}(?=\s*,\s*[A-Z]{1,2}\d{1,2}[A-Z]?\s+\d[A-Z]{2}\b)"

# Pattern B: Major capital cities at start followed by verb
pat_b = r"\b(?:Paris|London|Berlin|Tokyo|Beijing|Delhi|Moscow|Rome|Madrid|Oslo|Stockholm|Helsinki|Copenhagen|Amsterdam|Brussels|Vienna|Prague|Warsaw|Budapest|Dublin|Lisbon|Athens|Seoul|Bangkok|Jakarta|Hanoi|Dubai|Istanbul|Cairo|Jerusalem|Riyadh|Singapore|Manila|Kuala Lumpur)(?=\s+(?:has|is|was|lies|sits|became|remains|serves|boasts|encompasses|covers|spans|welcomes|hosts|attracts))"

texts = [
    ("FN1", "Our office is at 350 Fifth Avenue, New York, NY 10118"),
    ("FN2", "Paris has a population of over 2 million people and is the capital of France."),
    ("FN3", "Visit us at 10 Downing Street, London, SW1A 2AA"),
    ("OK2", "Visit New York, NY 10001 for the conference"),
    ("OK4", "located in London, SW1A 1AA at the Houses of Parliament"),
    ("OK5", "Berlin is the capital of Germany"),
    ("OK6", "Tokyo has hosted the Olympics multiple times."),
    ("FP8", "Fifth Avenue, NY 10001 is a famous street"),
    ("FP11", "Office, NY 10001"),
    ("FP20", "Avenue, NY 10001"),
    ("FP22", "The building is at 123 Main Street, Springfield, IL 62701"), # Springfield IS a real city
    ("FP23", "Tenant moved to Austin, TX 78701"),
    ("FP24", "John works in San Francisco, CA 94102"),
]

for label, text in texts:
    print(f"\n--- {label}: '{text}' ---")
    for name, pat, conf in [("A1", pat_a, 0.55), ("A2", pat_a2, 0.55), ("B", pat_b, 0.65)]:
        try:
            for m in re.finditer(pat, text):
                print(f"  [{name}] '{m.group()}' [{m.start()}:{m.end()}] conf={conf:.2f}")
        except re.error as e:
            print(f"  [{name}] ERROR: {e}")