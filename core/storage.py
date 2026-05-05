"""Supabase Storage helpers — proof file uploads.

Bucket: 'proofs'  (create this in your Supabase dashboard → Storage)
Bucket visibility: Public  (so stored URLs are always viewable without expiry)

Upload path: proofs/{action_id}/{filename}
Public URL:  {SUPABASE_URL}/storage/v1/object/public/proofs/{action_id}/{filename}
"""
from __future__ import annotations

import mimetypes

import requests

from config.settings import get_supabase_config, is_supabase_configured

PROOF_BUCKET = "proofs"


def _storage_base() -> str:
    return get_supabase_config()["url"].rstrip("/") + "/storage/v1"


def _auth_headers(content_type: str = "application/octet-stream") -> dict:
    key = get_supabase_config()["key"]
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": content_type,
    }


def upload_proof(file_bytes: bytes, filename: str, action_id: str) -> str:
    """Upload a proof file to Supabase Storage.

    Returns the public URL on success, or an empty string on failure.
    The bucket must exist and be set to Public in the Supabase dashboard.
    """
    if not is_supabase_configured():
        return ""

    content_type, _ = mimetypes.guess_type(filename)
    content_type = content_type or "application/octet-stream"

    # Sanitise filename — no spaces, safe for URLs
    safe_name = filename.replace(" ", "_")
    object_path = f"{action_id}/{safe_name}"
    url = f"{_storage_base()}/object/{PROOF_BUCKET}/{object_path}"

    headers = _auth_headers(content_type)

    try:
        # First attempt — regular POST
        resp = requests.post(url, headers=headers, data=file_bytes, timeout=60)

        if resp.status_code == 409:
            # File already exists — overwrite with upsert
            headers["x-upsert"] = "true"
            resp = requests.post(url, headers=headers, data=file_bytes, timeout=60)

        if resp.status_code in (200, 201):
            public_url = (
                f"{_storage_base()}/object/public/{PROOF_BUCKET}/{object_path}"
            )
            return public_url

        return ""

    except Exception:
        return ""
