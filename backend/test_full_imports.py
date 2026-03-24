try:
    print("Importing database module...")
    import database
    print("Importing connect_to_mongo...")
    from database import connect_to_mongo
    print("Importing close_mongo_connection...")
    from database import close_mongo_connection
    print("Importing get_database...")
    from database import get_database
    
    print("Importing auth_utils...")
    from auth_utils import hash_password, verify_password
    print("ALL IMPORTS SUCCESSFUL")
except Exception as e:
    print(f"IMPORT ERROR: {e}")
    import traceback
    traceback.print_exc()
