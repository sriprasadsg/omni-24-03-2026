import os
print("Root Directory Contents:")
try:
    files = os.listdir('.')
    for f in files:
        if "app" in f:
            print(f"FOUND POTENTIAL ROGUE: {f}")
except Exception as e:
    print(f"Error: {e}")
