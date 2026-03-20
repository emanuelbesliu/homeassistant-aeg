"""Gigya authentication client for AEG/Electrolux OCP API.

Implements the Gigya (SAP Customer Data Cloud) OAuth1 HMAC-SHA1 auth flow
as used by the AEG OneApp:
  1. socialize.getIDs -> get gmid, ucid
  2. accounts.login -> get sessionToken, sessionSecret
  3. accounts.getJWT -> get id_token (JWT with country claim)

The identity-providers API returns a base domain (e.g. "eu1.gigya.com").
Gigya endpoints use subdomains:
  - socialize.eu1.gigya.com  (for socialize.getIDs)
  - accounts.eu1.gigya.com   (for accounts.login, accounts.getJWT)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import random
import time
import urllib.parse
from math import floor

import aiohttp

_LOGGER = logging.getLogger(__name__)


class GigyaError(Exception):
    """Base exception for Gigya errors."""


class GigyaAuthError(GigyaError):
    """Authentication failed (invalid credentials)."""


class GigyaClient:
    """Client for Gigya (SAP Customer Data Cloud) authentication."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        api_key: str,
        domain: str,
    ) -> None:
        """Initialize the Gigya client.

        Args:
            session: aiohttp session to use for requests.
            api_key: Gigya API key (from identity-providers endpoint).
            domain: Gigya base domain (e.g. "eu1.gigya.com") from the
                identity-providers API. The accounts/socialize subdomains
                are constructed automatically.
        """
        self._session = session
        self._api_key = api_key
        # Store base domain without any subdomain prefix
        self._domain = domain.removeprefix("accounts.").removeprefix("socialize.")
        self._accounts_url = f"https://accounts.{self._domain}"
        self._socialize_url = f"https://socialize.{self._domain}"

    async def login(self, username: str, password: str) -> str:
        """Perform full Gigya login and return a JWT id_token.

        Flow: socialize.getIDs -> accounts.login -> accounts.getJWT

        Args:
            username: User's email.
            password: User's password.

        Returns:
            JWT id_token string (with country claim) for OCP token exchange.

        Raises:
            GigyaAuthError: If credentials are invalid.
            GigyaError: If any Gigya API call fails.
        """
        # Step 1: socialize.getIDs (get gmid + ucid for tracking)
        gmid, ucid = await self._socialize_get_ids()

        # Step 2: accounts.login
        session_token, session_secret = await self._accounts_login(
            username, password, gmid, ucid
        )

        # Step 3: accounts.getJWT (with fields=country)
        id_token = await self._accounts_get_jwt(
            session_token, session_secret, gmid, ucid
        )

        return id_token

    async def _socialize_get_ids(self) -> tuple[str, str]:
        """Call socialize.getIDs to get gmid and ucid.

        These identifiers are used for device tracking/analytics by Gigya.
        The login and getJWT calls work without them, but we include them
        to match the real app behavior and avoid potential blocks.

        Returns:
            Tuple of (gmid, ucid).
        """
        url = f"{self._socialize_url}/socialize.getIDs"
        data = {
            "apiKey": self._api_key,
            "format": "json",
            "httpStatusCodes": "true",
            "nonce": self._generate_nonce(),
            "sdk": "Android_6.2.1",
            "targetEnv": "mobile",
        }

        _LOGGER.debug("Gigya socialize.getIDs: %s", url)

        async with self._session.post(url, data=data) as resp:
            # Gigya returns text/javascript content type
            result = await resp.json(content_type=None)

        error_code = result.get("errorCode", 0)
        if error_code != 0:
            _LOGGER.warning(
                "Gigya socialize.getIDs failed (%s): %s (non-fatal)",
                error_code,
                result.get("errorMessage", "unknown"),
            )
            # Non-fatal — return empty strings, login may still work
            return "", ""

        gmid = result.get("gmid", "")
        ucid = result.get("ucid", "")
        _LOGGER.debug("Gigya getIDs: gmid=%s..., ucid=%s...", gmid[:12], ucid[:12])
        return gmid, ucid

    async def _accounts_login(
        self, username: str, password: str, gmid: str, ucid: str
    ) -> tuple[str, str]:
        """Call accounts.login to get session credentials.

        Returns:
            Tuple of (sessionToken, sessionSecret).
        """
        url = f"{self._accounts_url}/accounts.login"
        data = {
            "apiKey": self._api_key,
            "format": "json",
            "gmid": gmid,
            "httpStatusCodes": "true",
            "loginID": username,
            "nonce": self._generate_nonce(),
            "password": password,
            "sdk": "Android_6.2.1",
            "targetEnv": "mobile",
            "ucid": ucid,
        }

        _LOGGER.debug("Gigya accounts.login for %s", username)

        async with self._session.post(url, data=data) as resp:
            # Gigya returns text/javascript content type
            result = await resp.json(content_type=None)

        error_code = result.get("errorCode", 0)
        if error_code != 0:
            error_msg = result.get("errorMessage", "Unknown Gigya error")
            if error_code in (
                403042,  # Invalid loginID
                403043,  # Invalid password
                403044,  # Invalid loginID or password
                403047,  # Account disabled
                403048,  # Account locked
            ):
                raise GigyaAuthError(
                    f"Gigya login failed ({error_code}): {error_msg}"
                )
            raise GigyaError(
                f"Gigya login error ({error_code}): {error_msg}"
            )

        session_info = result.get("sessionInfo", {})
        session_token = session_info.get("sessionToken")
        session_secret = session_info.get("sessionSecret")

        if not session_token or not session_secret:
            raise GigyaError(
                "Gigya login succeeded but no session credentials returned"
            )

        _LOGGER.debug("Gigya login successful, UID=%s...", result.get("UID", "?")[:12])
        return session_token, session_secret

    async def _accounts_get_jwt(
        self,
        session_token: str,
        session_secret: str,
        gmid: str,
        ucid: str,
    ) -> str:
        """Call accounts.getJWT with OAuth1 HMAC-SHA1 signature.

        Args:
            session_token: Gigya session token.
            session_secret: Gigya session secret (base64-encoded).
            gmid: Device tracking ID from socialize.getIDs.
            ucid: Device tracking ID from socialize.getIDs.

        Returns:
            JWT id_token string (includes country claim).
        """
        url = f"{self._accounts_url}/accounts.getJWT"
        nonce = self._generate_nonce()
        timestamp = str(floor(time.time()))

        # Build OAuth1 base params (must include all params for signature)
        params: dict[str, str | bool | int] = {
            "apiKey": self._api_key,
            "fields": "country",
            "format": "json",
            "gmid": gmid,
            "httpStatusCodes": "true",
            "nonce": nonce,
            "oauth_token": session_token,
            "sdk": "Android_6.2.1",
            "targetEnv": "mobile",
            "timestamp": timestamp,
            "ucid": ucid,
        }

        # Generate OAuth1 HMAC-SHA1 signature
        sig = self._calculate_signature(
            "POST", url, params, session_secret
        )
        params["sig"] = sig

        _LOGGER.debug("Gigya accounts.getJWT")

        async with self._session.post(url, data=params) as resp:
            # Gigya returns text/javascript content type
            result = await resp.json(content_type=None)

        error_code = result.get("errorCode", 0)
        if error_code != 0:
            error_msg = result.get("errorMessage", "Unknown error")
            raise GigyaError(
                f"Gigya getJWT failed ({error_code}): {error_msg}"
            )

        id_token = result.get("id_token")
        if not id_token:
            raise GigyaError("Gigya getJWT succeeded but no id_token returned")

        _LOGGER.debug("Gigya JWT obtained (length=%d)", len(id_token))
        return id_token

    @staticmethod
    def _calculate_signature(
        method: str,
        url: str,
        params: dict[str, str | bool | int],
        secret: str,
    ) -> str:
        """Calculate OAuth1 HMAC-SHA1 signature.

        Based on the SAP Gigya SDK signature algorithm.

        Args:
            method: HTTP method (e.g. "POST").
            url: Full request URL.
            params: Request parameters (all types converted to string).
            secret: Base64-encoded session secret.

        Returns:
            Base64-encoded signature.
        """
        # Normalize URL (strip query string)
        parsed = urllib.parse.urlparse(url)
        normalized_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

        # Sort parameters alphabetically and encode
        # Convert all values to strings for encoding
        str_params = {k: str(v) for k, v in sorted(params.items())}
        query_string = urllib.parse.urlencode(
            sorted(str_params.items()), quote_via=urllib.parse.quote
        )

        # Build base string: METHOD&URL&PARAMS (all percent-encoded)
        base_string = "&".join(
            [
                method.upper(),
                urllib.parse.quote(normalized_url, safe=""),
                urllib.parse.quote(query_string, safe=""),
            ]
        )

        # Decode the base64 secret key
        key = base64.b64decode(secret)

        # HMAC-SHA1
        signature = hmac.new(key, base_string.encode("utf-8"), hashlib.sha1)

        return base64.b64encode(signature.digest()).decode("utf-8")

    @staticmethod
    def _generate_nonce() -> str:
        """Generate a nonce for OAuth1 requests."""
        return f"{round(time.time() * 1000)}_{random.randrange(1000000000, 10000000000)}"
