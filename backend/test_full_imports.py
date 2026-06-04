try:
    print("Importing database module...")
    print("Importing connect_to_mongo...")
    print("Importing close_mongo_connection...")
    print("Importing get_database...")
    
    print("Importing auth_utils...")
    print("ALL IMPORTS SUCCESSFUL")
except Exception as e:
    print(f"IMPORT ERROR: {e}")
    import traceback
    traceback.print_exc()
