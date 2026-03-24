from app import app
import json

with open("routes.txt", "w") as f:
    for route in app.routes:
        methods = getattr(route, "methods", None)
        f.write(f"{route.path} {methods}\n")
