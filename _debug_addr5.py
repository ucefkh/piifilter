texts = {
    1: 'Our office is at 350 Fifth Avenue, New York, NY 10118', # "at " before "350"
    21: 'Visit us at 10 Downing Street, London, SW1A 2AA', # "at " before "10"
    44: 'Home address: 123 Maple Drive, Springfield, IL 62704, USA', # "address: " before "123"
    95: "My street is 123 Main Street, not 123 Main St.", # no address context
    101: "The address is at 42 Wallaby Way, Sydney (famous from Finding Nemo).", # "address is at " before "42"
}
for k, v in texts.items():
    # Find where the street number appears
    import re
    m = re.search(r'\d{1,5}\s+(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\s+(?:St(?:reet)?|Ave(?:nue)?|Dr(?:ive)?|Rd|Road|Blvd|Boulevard|Ln|Lane|Way|Ct|Court|Pl|Place|Cir(?:cle)?|Pkwy|Parkway)', v)
    if m:
        ctx_start = max(0, m.start()-30)
        ctx = v[ctx_start:m.start()]
        print(f'Ex {k}: match at {m.start()}-{m.end()}: "...{ctx}<HERE>{v[m.start():m.end()]}"')
        print(f'  Pre-context ({ctx_start}:{m.start()}): {repr(ctx)}')