"""
One-shot script: revoke the JWT token that was accidentally committed to git.

Run ONCE against your live MongoDB:
    python backend/scripts/revoke_leaked_token.py

The token's JTI is inserted into the revoked_tokens collection, making it
invalid immediately — even before JWT_SECRET_KEY is rotated.

After running this script, also rotate JWT_SECRET_KEY in your secrets manager
to invalidate ALL existing sessions as a belt-and-suspenders measure.
"""

import asyncio
import os
import base64
import json
from datetime import datetime, timezone

LEAKED_TOKEN = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJzdWIiOiJhZG1pbkBleGFmbHVlbmNlLmNvbSIsInJvbGUiOiJUZW5hbnQgQWRtaW4iLCJ0ZW5hbnRfaWQiOiJ0ZW5hbnRfODJkZGEwZjMzYmM0IiwiZXhwIjoxODAxNjkwNjQ1fQ"
    ".SJv2EXw-5-BXJQTVpx2C-8h7p_xCpOMxNf0LJraufvU"
)


def _decode_payload(token: str) -> dict:
    parts = token.split(".")
    payload_b64 = parts[1] + "=="  # re-pad
    payload_bytes = base64.urlsafe_b64decode(payload_b64)
    return json.loads(payload_bytes)


async def main():
    try:
        from motor.motor_asyncio import AsyncIOMotorClient
    except ImportError:
        print("ERROR: motor not installed. Run: pip install motor")
        return

    mongo_url = os.getenv("MONGODB_URL", "mongodb://127.0.0.1:27017")
    db_name = os.getenv("MONGODB_DB_NAME", "omni_platform")

    payload = _decode_payload(LEAKED_TOKEN)
    jti = payload.get("jti")
    if not jti:
        print("WARNING: Token has no JTI claim — cannot revoke by JTI.")
        print("Rotate JWT_SECRET_KEY immediately to invalidate all sessions.")
        return

    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    existing = await db.revoked_tokens.find_one({"jti": jti})
    if existing:
        print(f"Token JTI {jti!r} is already in revoked_tokens — no action needed.")
    else:
        await db.revoked_tokens.insert_one({
            "jti": jti,
            "sub": payload.get("sub"),
            "reason": "leaked_in_git_history",
            "revoked_at": datetime.now(timezone.utc).isoformat(),
        })
        print(f"SUCCESS: Token JTI {jti!r} inserted into revoked_tokens.")
        print("The leaked token is now invalid for all future requests.")

    client.close()
    print("\nNEXT STEPS:")
    print("  1. Rotate JWT_SECRET_KEY in your secrets manager.")
    print("  2. Rotate GEMINI_API_KEY via Google Cloud Console.")
    print("  3. Rotate PAYMENT_ENCRYPTION_KEY and re-encrypt payment gateway secrets.")
    print("  4. Rotate SUPER_ADMIN_PASSWORD.")
    print("  5. Run: git filter-repo --path backend/new_token.txt --invert-paths")
    print("     (repeat for all other cleared key files)")


if __name__ == "__main__":
    asyncio.run(main())
