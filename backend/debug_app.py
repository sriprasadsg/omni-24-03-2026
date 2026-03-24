import database
print(f"DEBUG: database file: {database.__file__}")
print(f"DEBUG: database dir: {dir(database)}")
try:
    from database import get_database
    print("Success importing get_database")
except ImportError as e:
    print(f"ImportError: {e}")
