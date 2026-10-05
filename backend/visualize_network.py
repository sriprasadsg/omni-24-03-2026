import os
import logging
import matplotlib
matplotlib.use('Agg') # Non-interactive backend
import matplotlib.pyplot as plt
import networkx as nx

# Add project backend to path to use ServerDiscovery
try:
    from .server_discovery import ServerDiscovery
except ImportError:
    try:
        from server_discovery import ServerDiscovery
    except ImportError:
        print("Error: Could not import ServerDiscovery.")
        # sys.exit(1) # Don't exit on import if used as library


logging.basicConfig(level=logging.INFO)

def _load_all_devices_sync():
    """Standalone CLI path only: read every device with a blocking pymongo client.

    The API never uses this — it passes a tenant-scoped device list instead.
    """
    from pymongo import MongoClient

    MONGO_URI = os.getenv("MONGODB_URL") or os.getenv("MONGO_URI", "mongodb://localhost:27017")
    MONGO_DB_NAME = os.getenv("MONGODB_DB_NAME", "omni_platform")

    try:
        client = MongoClient(MONGO_URI)
        db = client[MONGO_DB_NAME]
        devices = list(db.network_devices.find({}, {"_id": 0}))
        client.close()
    except Exception as e:
        print(f"Error connecting to DB: {e}")
        devices = []
    return devices


def generate_network_graph(devices=None, output_file="network_topology.png"):
    """Render devices as a topology PNG at output_file; return its absolute path.

    Blocking (matplotlib) — async callers must run it in a worker thread and
    serialize calls, since pyplot keeps global state.
    """
    print("Generating Network Graph...")
    if devices is None:
        devices = _load_all_devices_sync()

    print(f"Found {len(devices)} devices.")

    # Create Graph
    G = nx.Graph()
    
    # Add Central Node (The Server/Scanner)
    server_node = "Server (You)"
    G.add_node(server_node, type="server", color="blue", subnet="central")
    
    # Group devices by subnet
    subnet_groups = {}
    for device in devices:
        subnet = device.get("subnet", "Unknown")
        if subnet not in subnet_groups:
            subnet_groups[subnet] = []
        subnet_groups[subnet].append(device)
    
    # Add Discovered Nodes
    for device in devices:
        # Support both 'ip' (from scanner) and 'ipAddress' (from DB/Seed)
        ip = device.get("ip") or device.get("ipAddress")
        
        if not ip:
            continue

        hostname = device.get("hostname", ip)
        subnet = device.get("subnet", "Unknown")
        label = f"{hostname}\n({ip})"
        if hostname == ip: 
            label = ip
            
        device_type = device.get("device_type") or device.get("deviceType") or "Unknown"
        
        # Color coding by device type
        color = "green"
        if "Windows" in device_type: color = "cyan"
        if "Linux" in device_type: color = "orange"
        if "Printer" in device_type: color = "yellow"
        if "Router" in device_type: color = "red"
        if "Firewall" in device_type: color = "purple"
        
        G.add_node(ip, label=label, type="device", color=color, details=device, subnet=subnet)
        G.add_edge(server_node, ip)

    # Visualization with subnet grouping
    plt.figure(figsize=(14, 12)) # Increased size for multi-subnet view
    
    # Position nodes using a Star/Shell layout with subnet clustering
    pos = {}
    pos[server_node] = (0, 0) # Center
    
    # Calculate positions for devices grouped by subnet
    import math
    num_subnets = len(subnet_groups)
    
    if num_subnets == 1:
        # Single subnet - simple circle
        devices_list = list(subnet_groups.values())[0]
        if devices_list:
            radius = 1.2
            angle_step = 2 * math.pi / len(devices_list)
            for i, device in enumerate(devices_list):
                angle = i * angle_step
                x = radius * math.cos(angle)
                y = radius * math.sin(angle)
                ip = device.get("ip") or device.get("ipAddress")
                if ip:
                    pos[ip] = (x, y)
    elif num_subnets > 1:
        # Multiple subnets - group in sectors (no devices: only the server node is drawn)
        sector_angle = 2 * math.pi / num_subnets
        subnet_colors_bg = ['lightblue', 'lightgreen', 'lightyellow', 'lightcoral', 'lightpink', 'lightgray']
        
        for subnet_idx, (subnet, subnet_devices) in enumerate(subnet_groups.items()):
            base_angle = subnet_idx * sector_angle
            radius = 1.5
            
            # Position devices in this subnet's sector
            if subnet_devices:
                sub_angle_step = sector_angle * 0.8 / len(subnet_devices)  # 80% of sector
                for device_idx, device in enumerate(subnet_devices):
                    angle = base_angle + (device_idx - len(subnet_devices)/2) * sub_angle_step
                    x = radius * math.cos(angle)
                    y = radius * math.sin(angle)
                    ip = device.get("ip") or device.get("ipAddress")
                    if ip:
                        pos[ip] = (x, y)
    
    # Draw Edges first (so they are behind nodes)
    nx.draw_networkx_edges(G, pos, width=1.0, alpha=0.3, edge_color="gray")
    
    # Draw subnet background regions (if multiple subnets)
    if num_subnets > 1:
        from matplotlib.patches import Wedge
        sector_angle = 2 * math.pi / num_subnets
        subnet_colors_bg = ['#E3F2FD', '#E8F5E9', '#FFF9C4', '#FFEBEE', '#F3E5F5', '#E0E0E0']
        
        for subnet_idx, subnet in enumerate(subnet_groups.keys()):
            color_idx = subnet_idx % len(subnet_colors_bg)
            start_angle = math.degrees(subnet_idx * sector_angle - sector_angle/2)
            wedge = Wedge((0, 0), 1.8, start_angle, start_angle + math.degrees(sector_angle), 
                         facecolor=subnet_colors_bg[color_idx], alpha=0.2, edgecolor='none')
            plt.gca().add_patch(wedge)
            
            # Add subnet label
            label_angle = subnet_idx * sector_angle
            label_radius = 2.1
            label_x = label_radius * math.cos(label_angle)
            label_y = label_radius * math.sin(label_angle)
            plt.text(label_x, label_y, f"Subnet:\n{subnet}", 
                    fontsize=8, ha='center', va='center', 
                    bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.7))
    
    # Define Icon Mapping (Files)
    icon_map = {
        "server": "server.png",
        "router": "router.png",
        "firewall": "firewall.png",
        "switch": "switch.png",
        "printer": "printer.png",
        "laptop": "laptop.png",
        "desktop": "desktop.png",
        "iot": "iot.png",
        "unknown": "unknown.png"
    }

    from matplotlib.offsetbox import AnnotationBbox, OffsetImage
    # import os (Removed redundant import)

    # Load images
    loaded_icons = {}
    icon_dir = os.path.join(os.path.dirname(__file__), "static", "device_icons")
    print(f"Loading icons from: {icon_dir}")
    
    for key, filename in icon_map.items():
        try:
            path = os.path.join(icon_dir, filename)
            if os.path.exists(path):
                img = plt.imread(path)
                loaded_icons[key] = img
                print(f"Loaded icon: {key}")
            else:
                print(f"Icon file not found: {path}")
        except Exception as e:
            print(f"Failed to load icon {filename}: {e}")

    # Draw Nodes as Icons
    ax = plt.gca()
    for node in G.nodes():
        x, y = pos[node]
        node_type = G.nodes[node].get("type", "device")
        details = G.nodes[node].get("details", {})
        
        # Determine Icon Key
        icon_key = "unknown"
        if node_type == "server":
            icon_key = "server"
        else:
            device_raw_type = str(details.get("device_type") or details.get("deviceType") or "Unknown")
            
            # Logic to match device type to icon
            lower_type = device_raw_type.lower()
            if "router" in lower_type: icon_key = "router"
            elif "firewall" in lower_type: icon_key = "firewall"
            elif "printer" in lower_type: icon_key = "printer"
            elif "laptop" in lower_type or "windows" in lower_type or "linux" in lower_type: 
                if "server" in lower_type: icon_key = "server"
                else: icon_key = "laptop" 
            elif "switch" in lower_type: icon_key = "switch"
            elif "iot" in lower_type: icon_key = "iot"
            elif "server" in lower_type: icon_key = "server"
            else: icon_key = "desktop" # Default to desktop if generic
            
        # Create Annotation Box with Icon
        if icon_key in loaded_icons:
            image = loaded_icons[icon_key]
            # Zoom level controls size. The generated images are 64x64. 
            # Zoom 0.5 makes them 32x32 which is a good size for the map.
            im = OffsetImage(image, zoom=0.6) 
            ab = AnnotationBbox(im, (x, y), frameon=False, pad=0)
            ax.add_artist(ab)
        else:
            # Fallback to a simple circle if icon missing
            circle = plt.Circle((x, y), 0.05, color='gray')
            ax.add_artist(circle)

    # Draw Labels with simplified content (Hostname + IP)
    # Using matplotlib.text directly for better control than nx.draw_networkx_labels
    for node, (x, y) in pos.items():
        label_text = G.nodes[node].get('label', node)
        # Add basic OS info if available in details
        details = G.nodes[node].get("details", {})
        os_info = details.get("os_name", "") or details.get("os", "")
        if os_info:
             # Truncate long OS names
             if len(os_info) > 15: os_info = os_info[:12] + "..."
             label_text += f"\n[{os_info}]"
             
        plt.text(x, y - 0.25, label_text, 
                 fontsize=8, ha='center', va='top', fontweight='bold',
                 bbox=dict(boxstyle='round,pad=0.2', facecolor='white', alpha=0.6, edgecolor='none'))

    subnet_count_str = f" across {num_subnets} subnet(s)" if num_subnets > 1 else ""
    plt.title(f"Network Topology - Discovered Devices ({len(devices)}{subnet_count_str})", fontsize=15)
    plt.axis('off')
    plt.xlim(-2.5, 2.5)
    plt.ylim(-2.5, 2.5)
    
    # Save Image
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    plt.close()
    
    print(f"Graph image saved to: {os.path.abspath(output_file)}")
    return os.path.abspath(output_file)

if __name__ == "__main__":
    generate_network_graph()
