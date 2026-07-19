text = "My street is 123 Main Street, not 123 Main St."
for i, c in enumerate(text):
    if 27 <= i <= 36:
        print(f'  {i}: {repr(c)}')