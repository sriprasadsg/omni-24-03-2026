import requests
import sys

API_URL = "http://127.0.0.1:5000/api/compliance"

def verify_iso_standards():
    try:
        response = requests.get(API_URL)
        if response.status_code != 200:
            print(f"❌ API Error: {response.status_code}")
            sys.exit(1)

        frameworks = response.json()
        iso9001_found = False
        iso31000_found = False

        for fw in frameworks:
            if fw['id'] == 'iso9001_2015':
                iso9001_found = True
                print("✅ Found ISO 9001:2015")
                # Verify controls
                controls = fw.get('controls', [])
                if any(c['id'] == 'iso9001-4.4' for c in controls):
                    print("  ✅ Found Control 4.4")
                else:
                    print("  ❌ Missing Control 4.4")
                
                # Verify manual instruction
                if any('manual_evidence_instructions' in c for c in controls):
                    print("  ✅ Manual Evidence Instructions Present")
                else: 
                     print("  ❌ Manual Evidence Instructions Missing")

            if fw['id'] == 'iso31000_2018':
                iso31000_found = True
                print("✅ Found ISO 31000:2018")
                # Verify controls
                controls = fw.get('controls', [])
                if any(c['id'] == 'iso31000-5.4' for c in controls):
                    print("  ✅ Found Control 5.4")
                else:
                    print("  ❌ Missing Control 5.4")

        if iso9001_found and iso31000_found:
            print("\n🎉 SUCCESS: Both ISO standards verified!")
            sys.exit(0)
        else:
            print("\n❌ FAILURE: One or more standards missing.")
            sys.exit(1)

    except Exception as e:
        print(f"❌ Exception: {e}")
        sys.exit(1)

if __name__ == "__main__":
    verify_iso_standards()
