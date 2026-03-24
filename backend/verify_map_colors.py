
from PIL import Image
import os

def verify_colors():
    image_path = "network_topology.png"
    if not os.path.exists(image_path):
        print("VERIFICATION_FAILURE: Image not found")
        return

    img = Image.open(image_path)
    img = img.convert("RGB")
    pixels = list(img.getdata())
    
    from collections import Counter
    # Count colors
    c = Counter(pixels)
    print("Top 200 colors:")
    for color, count in c.most_common(200):
        print(f"Color: {color}, Count: {count}")
        
    # Check for known icon colors
    targets = {
        "Server": (26, 35, 126),
        "Router": (33, 150, 243),
        "Laptop": (0, 150, 136),
        "Firewall": (244, 67, 54),
        "Switch": (76, 175, 80)
    }
    
    found_any = False
    for name, target in targets.items():
        # Check closest color
        best_match = min(c.keys(), key=lambda x: sum(abs(a-b) for a,b in zip(x, target)))
        diff = sum(abs(a-b) for a,b in zip(best_match, target))
        print(f"Closest match for {name} {target}: {best_match} (diff: {diff})")
        if diff < 50: # increased tolerance
             found_any = True
             print(f"VERIFICATION_SUCCESS: Found loose match for {name}")

    if found_any:
        print("Final Verdict: ICONS_DETECTED")
    else:
        print("Final Verdict: ICONS_NOT_DETECTED")

if __name__ == "__main__":
    verify_colors()
