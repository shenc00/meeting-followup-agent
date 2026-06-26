from __future__ import annotations

import logging
import os
from typing import Optional

import msal

logger = logging.getLogger(__name__)

_CACHE_PATH = "token_cache.bin"


class GraphAuthClient:
    """
    MSAL-based authentication helper for Microsoft Graph.

    Uses PublicClientApplication for delegated (on-behalf-of-user) permissions
    so the agent reads and writes the signed-in user's own mail, calendar, and
    Teams data.  Supports:
      - Silent token acquisition from persistent cache (subsequent runs)
      - Device code flow for headless / terminal environments (first run)
      - Interactive browser flow when a display is available (first run)
    """

    def __init__(
        self,
        tenant_id: str,
        client_id: str,
        client_secret: Optional[str] = None,  # not used for public client; kept for API compat
        scopes: list[str] = None,
        cache_path: str = _CACHE_PATH,
    ) -> None:
        self._scopes = scopes or []
        self._cache_path = cache_path
        self._cache = self._load_cache()
        # PublicClientApplication supports delegated flows (device code, interactive)
        self._app = msal.PublicClientApplication(
            client_id=client_id,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
            token_cache=self._cache,
        )

    def get_token(self) -> str:
        """Return a valid access token, refreshing silently if possible."""
        # 1. Try silent acquisition from cache
        accounts = self._app.get_accounts()
        result = None
        if accounts:
            result = self._app.acquire_token_silent(self._scopes, account=accounts[0])

        # 2. Try interactive browser (works when a GUI is available)
        if not result:
            try:
                result = self._app.acquire_token_interactive(scopes=self._scopes)
            except Exception:
                result = None

        # 3. Fall back to device code flow (always works in terminals)
        if not result:
            flow = self._app.initiate_device_flow(scopes=self._scopes)
            if "user_code" not in flow:
                raise RuntimeError(f"Failed to initiate device flow: {flow}")
            print(
                f"\nAuthentication required.\n"
                f"  1. Open: {flow['verification_uri']}\n"
                f"  2. Enter code: {flow['user_code']}\n"
            )
            result = self._app.acquire_token_by_device_flow(flow)

        if not result or "access_token" not in result:
            raise RuntimeError(
                f"Authentication failed: {result.get('error_description', result) if result else 'no result'}"
            )

        self._save_cache()
        return result["access_token"]

    def _load_cache(self) -> msal.SerializableTokenCache:
        cache = msal.SerializableTokenCache()
        if os.path.exists(self._cache_path):
            with open(self._cache_path, encoding="utf-8") as f:
                cache.deserialize(f.read())
        return cache

    def _save_cache(self) -> None:
        if self._cache.has_state_changed:
            with open(self._cache_path, "w", encoding="utf-8") as f:
                f.write(self._cache.serialize())
