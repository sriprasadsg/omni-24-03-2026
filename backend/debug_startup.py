import sys
print("Importing app...")
try:
    from app import app
    print("Imported app successfully.")
except Exception as e:
    print(f"Failed to import app: {e}")
    import traceback
    traceback.print_exc()
except SystemExit as e:
    print(f"SystemExit during import: {e}")
except ImportError as e:
     print(f"ImportError: {e}")
     import traceback
     traceback.print_exc()
