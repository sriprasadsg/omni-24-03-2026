
import os
import sys

# Ensure we can import from current directory
sys.path.append(os.getcwd())

try:
    from visualize_network import generate_network_graph
    
    print("Running generate_network_graph()...")
    output_path = generate_network_graph()
    
    print(f"Output path: {output_path}")
    
    if os.path.exists(output_path):
        size = os.path.getsize(output_path)
        print(f"File size: {size} bytes")
        if size > 0:
            print("VERIFICATION_SUCCESS")
        else:
            print("VERIFICATION_FAILURE: File is empty")
    else:
        print("VERIFICATION_FAILURE: File not found")
        
except Exception as e:
    print(f"VERIFICATION_FAILURE: Exception occurred: {e}")
    import traceback
    traceback.print_exc()
