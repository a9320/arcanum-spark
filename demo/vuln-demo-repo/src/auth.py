import hashlib


def hash_password(pw: str) -> str:
    """Hash password with SHA-256 (demo only)."""
    return hashlib.sha256(pw.encode()).hexdigest()
