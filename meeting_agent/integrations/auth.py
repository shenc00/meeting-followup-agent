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

    Supports:
      - Interactive browser login (first-time / token refresh)
      - Silent token acquisition from persistent cache
    """

    def __init__(
        self,
        tenant_id: str,
        client_id: str,
        client_secret: Optional[str],
        scopes: list[str],
        cache_path: str = _CACHE_PATH,
    ) -> None:
        self._scopes = scopes
        self._cache_path = cache_path
        self._cache = self._load_cache()
        self._app = msal.ConfidentialClientApplication(
            client_id=client_id,
            client_credential=client_secret,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
            token_cache=self._cache,
        )

    def get_token(self) -> str:
        """Return a valid access token, refreshing silently if possible."""
        accounts = self._app.get_accounts()
        result = None
        if accounts:
            result = self._app.acquire_token_silent(self._scopes, account=accounts[0])

        if not result:
            # Fallback: device code flow (works in headless/server environments)
            flow = self._app.initiate_device_flow(scopes=self._scopes)
            if "user_code" not in flow:
                raise RuntimeError(f"Failed to initiate device flow: {flow}")
            logger.info("To authenticate, visit %s and enter code: %s", flow["verification_uri"], flow["user_code"])
            print(f"\nAuthentication required.\nVisit: {flow['verification_uri']}\nEnter code: {flow['user_code']}\n")
            result = self._app.acquire_token_by_device_flow(flow)

        if "access_token" not in result:
            raise RuntimeError(f"Authentication failed: {result.get('error_description', result)}")

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
