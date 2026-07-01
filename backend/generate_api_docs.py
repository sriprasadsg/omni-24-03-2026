import re
import os

def generate_api_docs():
    app_path = "backend/app.py"
    if not os.path.exists(app_path):
        print(f"Error: {app_path} not found.")
        return

    with open(app_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Find all router inclusions
    # app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
    router_matches = re.findall(r'app\.include_router\([^,)]+,\s*prefix="([^"]+)"(?:,\s*tags=\[([^\]]+)\])?', content)

    doc_content = "# Enterprise Omni-Agent Platform — API Reference\n\n"
    doc_content += f"Total Integrated Modules: {len(router_matches)}\n\n"
    doc_content += "| Tag | Prefix |\n"
    doc_content += "| --- | --- |\n"

    for prefix, tags in router_matches:
        tags = tags.replace('"', '').replace("'", "") if tags else "General"
        doc_content += f"| {tags} | `{prefix}` |\n"

    # Add common endpoints from app.py
    doc_content += "\n## Global System Endpoints\n"
    doc_content += "- `GET /health`: System health check\n"
    doc_content += "- `GET /api/status`: Platform operational status\n"
    doc_content += "- `POST /api/telemetry`: Agent telemetry ingestion\n"

    os.makedirs("docs", exist_ok=True)
    with open("docs/api-reference.md", "w", encoding="utf-8") as f:
        f.write(doc_content)
    
    print("DONE: API Reference generated in docs/api-reference.md")

if __name__ == "__main__":
    generate_api_docs()
