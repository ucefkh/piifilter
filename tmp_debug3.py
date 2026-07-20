"""Trace deobfuscation of URL-encoded phone step by step."""
import sys, re
sys.path.insert(0, 'benchmarks')
sys.path.insert(0, 'core/src')
sys.path.insert(0, 'plugins/detector-regex/src')

from piifilter.shared.deobfuscator import Deobfuscator

text = 'URL-encoded phone: %2B1-555-123-4567'
print(f"Input: {text!r}")

deob = Deobfuscator()

# Manual step-by-step
log = []
t = deob._nfkc_normalize(text, log)
print(f"1 NFKC: {t!r}")

t = deob._strip_html_comments(t, log)
print(f"2 HTML comments: {t!r}")

t = deob._decode_morse(t, log)
print(f"3 Morse: {t!r}")

t = deob._unwrap_at_dot(t, log)
print(f"4 [at]/[dot]: {t!r}")

t = deob._fix_obfuscated_email_entities(t, log)
print(f"5 Obf email: {t!r}")

t = deob._decode_xml_escape(t, log)
print(f"6 XML escape: {t!r}")

t = deob._unwrap_html_entities(t, log)
print(f"7 HTML entities: {t!r}")

t = deob._unwrap_zero_width(t, log)
print(f"8 Zero width: {t!r}")

t = deob._normalize_dashes(t, log)
print(f"9 Dashes: {t!r}")

t = deob._remove_soft_hyphen(t, log)
print(f"10 Soft hyphen: {t!r}")

t = deob._flatten_fullwidth(t, log)
print(f"11 Fullwidth: {t!r}")

t = deob._unwrap_unicode_escapes(t, log)
print(f"12 Unicode escapes: {t!r}")

t = deob._decode_hex_escapes(t, log)
print(f"13 Hex escapes: {t!r}")

# URL percent decode loop
for _round in range(5):
    prev = t
    t = deob._decode_url_percent(t, log)
    print(f"14.{_round} URL pct: {t!r}")
    t = deob._decode_hex_escapes(t, log)
    print(f"14.{_round}b Hex esc: {t!r}")
    if t == prev:
        break

t = deob._normalize_pct_separator(t, log)
print(f"15 Pct sep: {t!r}")

t = deob._decode_binary_strings(t, log)
print(f"16 Binary: {t!r}")

t = deob._normalize_unicode_fractions(t, log)
print(f"17 Fractions: {t!r}")

t = deob._unwrap_spoken_numbers(t, log)
print(f"18 Spoken: {t!r}")

t = deob._map_spoken_separators(t, log)
print(f"19 Spoken seps: {t!r}")

t = deob._normalize_ip_octet_spaces(t, log)
print(f"20 IP octet spaces: {t!r}")

t = deob._normalize_ip_octet_dots(t, log)
print(f"21 IP octet dots: {t!r}")

t = deob._normalize_ssn_segments(t, log)
print(f"22 SSN segments: {t!r}")

t = deob._normalize_cc_segments(t, log)
print(f"23 CC segments: {t!r}")

t = deob._cleanup_dash_spaces(t, log)
print(f"24 Dash spaces: {t!r}")

t = deob._collapse_ip_spaces(t, log)
print(f"25 IP collapse: {t!r}")

t = deob._collapse_digit_spaces(t, log)
print(f"26 Digit collapse: {t!r}")

print(f"\nFINAL: {t!r}")
print(f"STRIPPED: {Deobfuscator._strip_inner_separators(t)!r}")