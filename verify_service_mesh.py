import requests
import json
import sys

BASE_URL = "http://localhost:5000/api/mesh"

def verify_service_mesh():
    print(f"Testing Service Mesh Endpoints at {BASE_URL}...")
    
    # 1. Get Services
    try:
        response = requests.get(f"{BASE_URL}/services")
        if response.status_code == 200:
            services = response.json()
            print("\n[SUCCESS] GET /services")
            print(f"Count: {len(services)}")
            if len(services) > 0:
                print(json.dumps(services[0], indent=2))
        else:
            print(f"\n[FAILURE] GET /services - Status: {response.status_code}")
    except Exception as e:
        print(f"\n[ERROR] GET /services: {e}")

    # 2. Get Metrics
    try:
        response = requests.get(f"{BASE_URL}/metrics")
        if response.status_code == 200:
            metrics = response.json()
            print("\n[SUCCESS] GET /metrics")
            print(f"Count: {len(metrics)}")
            if len(metrics) > 0:
                print(json.dumps(metrics[0], indent=2))
        else:
            print(f"\n[FAILURE] GET /metrics - Status: {response.status_code}")
    except Exception as e:
        print(f"\n[ERROR] GET /metrics: {e}")

    # 3. Get Graph
    try:
        response = requests.get(f"{BASE_URL}/graph")
        if response.status_code == 200:
            graph = response.json()
            print("\n[SUCCESS] GET /graph")
            print(f"Nodes: {len(graph.get('nodes', []))}")
            print(f"Edges: {len(graph.get('edges', []))}")
        else:
            print(f"\n[FAILURE] GET /graph - Status: {response.status_code}")
    except Exception as e:
         print(f"\n[ERROR] GET /graph: {e}")

if __name__ == "__main__":
    verify_service_mesh()
