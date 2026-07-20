"""Quick test of DOMAIN and CITY detection."""
import asyncio
import sys
sys.path.insert(0, 'core/src')
sys.path.insert(0, 'plugins/detector-regex/src')
from piifilter_detector_regex.detector import RegexDetector

async def test():
    d = RegexDetector()
    await d.initialize()
    
    # DOMAIN tests
    print("=== DOMAIN Tests ===")
    for text in [
        'Domain: google.com',
        'Visit www.myapp.dev', 
        'Access test.company.net',
        'gmail.com is my email host',
        'I use github.com for code',
        'outlook.com works',
        'yahoo.com mail service',
        'Visit staging.corp.cloud',
        'Access api.testapp.internal',
        'hotmail.com is a provider',
        'I have an icloud.com account',
        'Check amazon.com for details',
    ]:
        results = await d.detect(text)
        for r in results:
            et = r.entity_type.value if hasattr(r.entity_type, 'value') else str(r.entity_type)
            if et in ('DOMAIN', 'URL'):
                print(f'  TEXT: "{text}" -> {et}: "{r.text}" score={r.raw_score}')
    
    # CITY tests  
    print("\n=== CITY Tests ===")
    for text in [
        'I live in Miami',
        'Amsterdam headquarters',
        'Our Dublin office',
        'City: Tokyo',
        'Based in Seattle',
        'Paris has a population',
        'I visited Boston',
        'The Settings page is broken',
        'Check the Admin panel',
        'System config needs update',
        'Profile settings',
        'Running Mode detection',
        'Default configuration',
        'Support team contact',
        'Config options manager',
        'Manager approval needed',
        'in Boston',
        'in Settings',
        'in System',
        'in Mode',
        'in Config',
    ]:
        results = await d.detect(text)
        for r in results:
            et = r.entity_type.value if hasattr(r.entity_type, 'value') else str(r.entity_type)
            if et in ('CITY', 'PERSON', 'COMPANY', 'DOMAIN'):
                print(f'  TEXT: "{text}" -> {et}: "{r.text}" score={r.raw_score}')

asyncio.run(test())