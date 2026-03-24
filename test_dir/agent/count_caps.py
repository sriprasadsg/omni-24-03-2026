from capabilities import CAPABILITY_REGISTRY
print(f"Total capabilities registered: {len(CAPABILITY_REGISTRY)}")
for k in sorted(CAPABILITY_REGISTRY.keys()):
    print(f"  - {k}")
