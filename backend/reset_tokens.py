"""Password-reset and invite links kept in ``password_reset_tokens``.

The link carries the token; the stored row keeps only ``tokenHash`` (hex SHA-256), so reading the
collection hands nobody a working link. Shared by the reset routes, ``partner_invites`` and the user
routes. Setting a password by any route ends every link still open for that address.
"""
import hashlib


def token_hash(token: str) -> str:
    """The only form of a link token the database keeps."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def by_token(token: str) -> dict:
    """The ``password_reset_tokens`` filter that finds a link's row."""
    return {"tokenHash": token_hash(token)}


async def end_open_links(raw_db, email: str) -> None:
    """Delete every reset or invite link still open for ``email`` (a password was just set)."""
    if email:
        await raw_db.password_reset_tokens.delete_many({"email": email})
