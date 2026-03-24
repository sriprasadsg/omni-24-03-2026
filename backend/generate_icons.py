
import os
from PIL import Image, ImageDraw, ImageFont, ImageOps

ICON_DIR = os.path.join(os.path.dirname(__file__), "static", "device_icons")
os.makedirs(ICON_DIR, exist_ok=True)

def create_icon(name, color, shape="circle", symbol=None):
    size = (64, 64)
    img = Image.new("RGBA", size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    
    # Draw Background Shape
    if shape == "circle":
        draw.ellipse((4, 4, 60, 60), fill=color, outline="black", width=2)
    elif shape == "rect":
        draw.rectangle((8, 16, 56, 48), fill=color, outline="black", width=2)
    elif shape == "server":
        draw.rectangle((16, 4, 48, 60), fill=color, outline="black", width=2)
        # Server lines
        draw.line((20, 14, 44, 14), fill="black", width=1)
        draw.line((20, 24, 44, 24), fill="black", width=1)
        draw.line((20, 34, 44, 34), fill="black", width=1)
        draw.line((20, 44, 44, 44), fill="black", width=1)
    elif shape == "cloud":
        # Simple Cloud
        draw.ellipse((10, 20, 30, 40), fill=color, outline="black", width=1)
        draw.ellipse((20, 10, 50, 40), fill=color, outline="black", width=1)
        draw.ellipse((40, 20, 60, 40), fill=color, outline="black", width=1)
        draw.rectangle((20, 25, 50, 40), fill=color, outline=None)
        
    # Draw Symbol (Simplified geometric representations)
    if symbol == "arrow":
        # Router arrows
        draw.line((20, 32, 44, 32), fill="white", width=3)
        draw.polygon([(44, 32), (38, 26), (38, 38)], fill="white", outline="black")
        draw.line((44, 32, 20, 32), fill="white", width=3)
        draw.polygon([(20, 32), (26, 26), (26, 38)], fill="white", outline="black")
    elif symbol == "shield":
        # Shield cross
        draw.line((32, 16, 32, 48), fill="white", width=4)
        draw.line((16, 32, 48, 32), fill="white", width=4)
    elif symbol == "screen":
        if shape == "rect":
            draw.rectangle((12, 20, 52, 44), fill="black") # Screen inner
    
    # Save
    output_path = os.path.join(ICON_DIR, f"{name}.png")
    img.save(output_path)
    print(f"Generated {output_path}")

def generate_all_icons():
    print("Generating network device icons...")
    
    # Server: Tall rectangle, dark blue
    create_icon("server", "#1A237E", shape="server")
    
    # Router: Circle, Blue, with arrows
    create_icon("router", "#2196F3", shape="circle", symbol="arrow")
    
    # Switch: Rectangle, Green
    create_icon("switch", "#4CAF50", shape="rect")
    
    # Firewall: Circle, Red, Shield-like
    create_icon("firewall", "#F44336", shape="circle", symbol="shield")
    
    # Laptop/Desktop: Rectangle, Teal
    create_icon("laptop", "#009688", shape="rect", symbol="screen")
    create_icon("desktop", "#009688", shape="rect", symbol="screen")
    
    # Printer: Rectangle, Grey
    create_icon("printer", "#9E9E9E", shape="rect")
    
    # IoT: Small Circle, Purple
    create_icon("iot", "#9C27B0", shape="circle")
    
    # Unknown: Grey Circle
    create_icon("unknown", "#BDBDBD", shape="circle")
    
    print("All icons generated successfully.")

if __name__ == "__main__":
    generate_all_icons()
