import unicodedata
cyr_a = '\u0430'
lat_a = 'a'
nfkc = unicodedata.normalize('NFKC', cyr_a)
print(f'Cyrillic a: {repr(cyr_a)} -> NFKC: {repr(nfkc)}')
print(f'Same as Latin a: {nfkc == lat_a}')
# Test if NFKC normalizes Cyrillic a to Latin a
s = 'test.ex\u0430mple.com'
print(f'With Cyrillic a: {repr(s)} -> NFKC: {repr(unicodedata.normalize("NFKC", s))}')