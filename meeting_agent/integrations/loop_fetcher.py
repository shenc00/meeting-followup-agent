"""
loop_fetcher.py
---------------
Fetches Microsoft Loop meeting notes directly from OneDrive / SharePoint
via Microsoft Graph API using delegated permissions (no admin consent needed).

Required Graph scope (add to config.yaml):
  https://graph.microsoft.com/Files.Read.All   — delegated, no admin consent

Run once to authenticate:
  meeting-agent auth
"""
from __future__ import annotations

import logging
import re
from typing import Optional

import requests

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


class LoopFetcher:
    """
    Searches for Microsoft Loop (.loop) files via Graph API and extracts
    plain-text content from the Fluid Framework binary format.
    """

    def __init__(self, tenant_id: str, client_id: str, scopes: list[str],
                 cache_path: str = "token_cache.bin") -> None:
        self._tenant_id  = tenant_id
        self._client_id  = client_id
        self._scopes     = scopes
        self._cache_path = cache_path

    # ── Public API ────────────────────────────────────────────────────────────

    def fetch_latest(self, title: Optional[str] = None) -> tuple[Optional[str], Optional[str]]:
        """
        Returns (page_title, notes_text) for the most-recently modified
        .loop file whose name contains `title` (or any .loop file if None).

        Returns (None, None) if nothing is found.
        """
        token = self._get_token()
        if not token:
            logger.error("Loop: could not obtain Graph token. Run 'meeting-agent auth' first.")
            return None, None

        items = self._search_loop_files(token, title)
        if not items:
            logger.warning("Loop: no .loop files found matching '%s'", title)
            return None, None

        # Pick most recently modified
        items.sort(key=lambda x: x.get("lastModifiedDateTime", ""), reverse=True)
        best = items[0]
        page_title = best.get("name", "").removesuffix(".loop")

        logger.info("Loop: downloading '%s'", best.get("name"))
        content = self._download_item(token, best)
        if not content:
            return page_title, ""

        text = self._extract_text(content)
        logger.info("Loop: extracted %d chars from '%s'", len(text), best.get("name"))
        return page_title, text

    # ── Local file extraction (no auth required) ──────────────────────────────

    @classmethod
    def extract_from_local_file(cls, file_path: str) -> str:
        """
        Extract plain text from a .loop file on the local file system.
        No authentication required — works directly from the OneDrive sync folder.
        """
        with open(file_path, "rb") as f:
            data = f.read()
        return cls._extract_text(data)

    # ── Graph search ──────────────────────────────────────────────────────────

    def _search_loop_files(self, token: str, title: Optional[str]) -> list[dict]:
        """Search across all accessible OneDrive/SharePoint for .loop files."""
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        # Build KQL query
        kql = f'"{title}" AND fileExtension:loop' if title else "fileExtension:loop"

        # Use /search/query to search across all accessible drives (personal + SharePoint)
        payload = {
            "requests": [{
                "entityTypes": ["driveItem"],
                "query": {"queryString": kql},
                "from": 0,
                "size": 10,
                "fields": ["name", "lastModifiedDateTime", "id",
                           "parentReference", "webUrl", "size"],
                "sortProperties": [{"name": "lastModifiedDateTime", "isDescending": True}],
            }]
        }

        resp = requests.post(f"{GRAPH_BASE}/search/query", headers=headers, json=payload, timeout=15)

        if resp.status_code == 403:
            logger.warning("Loop: Files.Read.All permission not granted. "
                           "Run 'meeting-agent auth' after adding the scope to config.yaml.")
            return []

        if not resp.ok:
            logger.warning("Loop: search failed %s — %s", resp.status_code, resp.text[:200])
            return []

        hits = []
        for result in resp.json().get("value", []):
            for hit in result.get("hitsContainers", []):
                for h in hit.get("hits", []):
                    resource = h.get("resource", {})
                    if resource.get("name", "").endswith(".loop"):
                        hits.append(resource)
        return hits

    # ── Content download ─────────────────────────────────────────────────────

    def _download_item(self, token: str, item: dict) -> Optional[bytes]:
        """Download the raw bytes of a drive item."""
        headers = {"Authorization": f"Bearer {token}"}

        # Prefer the pre-signed download URL if present
        dl_url = item.get("@microsoft.graph.downloadUrl")
        if dl_url:
            resp = requests.get(dl_url, timeout=20)
        else:
            item_id = item.get("id")
            parent  = item.get("parentReference", {})
            drive_id = parent.get("driveId", "")
            if drive_id:
                url = f"{GRAPH_BASE}/drives/{drive_id}/items/{item_id}/content"
            else:
                url = f"{GRAPH_BASE}/me/drive/items/{item_id}/content"
            resp = requests.get(url, headers=headers, timeout=20)

        if not resp.ok:
            logger.warning("Loop: download failed %s", resp.status_code)
            return None
        return resp.content

    # ── Text extraction ───────────────────────────────────────────────────────

    @staticmethod
    def _extract_text(data: bytes) -> str:
        """
        Extract readable text from a Fluid Framework .loop binary.

        Scans for runs of printable ASCII / UTF-16-LE strings then filters
        out DRM metadata, base64, GUIDs, URLs and other noise so only
        human-readable meeting content remains.
        """
        results: list[str] = []

        # --- UTF-8 / ASCII printable runs ---
        for m in re.findall(rb'[\x20-\x7E\t\n\r]{12,}', data):
            try:
                s = m.decode("utf-8").strip()
                if s and not _looks_like_metadata(s):
                    results.append(s)
            except Exception:
                pass

        # --- UTF-16-LE runs ---
        try:
            decoded = data.decode("utf-16-le", errors="ignore")
            for chunk in re.findall(r'[\x20-\x7E\t\n\r]{12,}', decoded):
                s = chunk.strip()
                if s and not _looks_like_metadata(s):
                    results.append(s)
        except Exception:
            pass

        # Deduplicate preserving order, prefer longer strings
        seen: set[str] = set()
        unique: list[str] = []
        for s in sorted(results, key=len, reverse=True):
            if s not in seen:
                seen.add(s)
                unique.append(s)

        return "\n".join(unique)

    # ── Auth helper ───────────────────────────────────────────────────────────

    def _get_token(self) -> Optional[str]:
        """
        Authenticate for Loop/Files access.

        Uses the Microsoft Graph Command Line Tools app (14d82eec-...) as the
        default client — it is a Microsoft-owned first-party app pre-trusted by
        most enterprise tenants and does NOT require admin consent for delegated
        Files.Read.All.

        Falls back to the custom client_id if set in config.
        """
        # Microsoft Graph Command Line Tools — pre-trusted in most M365 tenants
        MSFT_GRAPH_CLI_CLIENT = "14d82eec-204b-4c2f-b7e8-296a70dab67e"

        # Use custom client if configured, otherwise use the Microsoft app
        client_id = self._client_id or MSFT_GRAPH_CLI_CLIENT

        from meeting_agent.integrations.auth import GraphAuthClient
        # Scopes for Loop/Files access only (not the full mail/calendar set)
        loop_scopes = ["https://graph.microsoft.com/Files.Read.All"]
        auth = GraphAuthClient(
            tenant_id=self._tenant_id,
            client_id=client_id,
            scopes=loop_scopes,
            cache_path="token_cache_loop.bin",   # separate cache so Loop auth doesn't conflict
        )
        return auth.get_token()


def _looks_like_metadata(s: str) -> bool:
    """Filter out base64, GUIDs, URLs, XML/DRM noise, and binary garbage."""
    if re.fullmatch(r'[A-Za-z0-9+/=]{20,}', s):          return True   # base64
    if re.fullmatch(r'[0-9a-fA-F\-]{32,}', s):           return True   # GUID/hash
    if s.startswith(("http", "{", "[", "\\", "data:")):  return True   # URL/JSON
    if re.search(r'[^\x20-\x7E\s]', s):                  return True   # non-ASCII
    # XML / DRM specific patterns
    if re.search(r'<[A-Z][A-Z]+[ />]|XrML|PUBLICKEY|ALGORITHM|ISSUEDTIME'
                 r'|encoding=|xmlns|DESCRIPTOR|aadrm\.com|\.svc\.ms', s):
        return True
    # Very long lines with no spaces are likely binary/base64
    words = s.split()
    if len(words) == 1 and len(s) > 40:                  return True
    return False
