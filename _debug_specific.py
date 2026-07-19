import re

# Check Mumbai
text = 'City: The population of Mumbai is over 20 million.'
pattern = r"(?i)\b(?:city|town)\s*(?:of|pop|population)?\s*:?\s*(?-i:[A-Z])[a-z]+(?:\s+(?-i:[A-Z])[a-z]+)?\b"
compiled = re.compile(pattern, re.UNICODE)
for m in compiled.finditer(text):
    print(f"Mumbai pattern: {m.start()}-{m.end()} val='{m.group()}'")
if not list(compiled.finditer(text)):
    print("Mumbai: No match")
    # Debug: what's at position 0?
    m2 = re.match(r"(?i)\b(?:city|town)\s*", text)
    if m2:
        print(f"  Step1: '{m2.group()}' at {m2.start()}-{m2.end()}")
        remaining = text[m2.end():]
        print(f"  Remaining: '{remaining}'")
        # Check of|pop|population
        m3 = re.match(r"(?:of|pop|population)?\s*:?\s*", remaining)
        if m3:
            print(f"  Step2: '{m3.group()}' at {m3.start()}-{m3.end()}")
            remaining2 = remaining[m3.end():]
            print(f"  After step2: '{remaining2}'")
            m4 = re.match(r"(?-i:[A-Z])[a-z]+", remaining2)
            if m4:
                print(f"  Step3: '{m4.group()}' at {m4.start()}-{m4.end()}")
    
print()

# Check Redmond
text = 'Person: Dr. Sarah Chen works at Microsoft Research in Redmond'
pattern = r"(?i)\b(?:based\s+in|works?\s+in|lives?\s+in|located\s+in|situated\s+in)\s+(?-i:[A-Z])[a-z]{2,}\b"
compiled = re.compile(pattern, re.UNICODE)
for m in compiled.finditer(text):
    print(f"Redmond pattern: {m.start()}-{m.end()} val='{m.group()}'")
if not list(compiled.finditer(text)):
    print("Redmond: No match")
    # The text is: "Person: Dr. Sarah Chen works at Microsoft Research in Redmond"
    # "works at Microsoft Research in Redmond" - "works at" then "Microsoft" then "Research" then "in Redmond"
    # My pattern needs: works? at|in - let me check
    m2 = re.search(r"in\s+[A-Z][a-z]+", text)
    if m2:
        print(f"  'in + cap word': {m2.start()}-{m2.end()} val='{m2.group()}'")
    
print()

# Check London
text = 'Visit us at 10 Downing Street, London, SW1A 2AA'
# Looking for "London" after comma and space
m2 = re.search(r", (\w+)", text)
if m2:
    print(f"  After comma: '{m2.group(1)}' at {m2.start()}-{m2.end()}")
    
# Check Paris standalone
text = "Paris has a population"
print(f"\nParis: starts with capital city name: {text[0:5]}")

# Check ADDRESS German
text = "Located in Berlin, Germany - our HQ is at Unter den Linden 1, 10117 Berlin"
# German address: street name + number + zip + city
m2 = re.search(r"(\w+(?:\s+\w+)+)\s+(\d+)\s*,\s*(\d{5})\s+(\w+)", text)
if m2:
    print(f"\nGerman address: full='{m2.group(0)}' street='{m2.group(1)}' num='{m2.group(2)}' zip='{m2.group(3)}' city='{m2.group(4)}'")