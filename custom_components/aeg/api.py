"""AEG/Electrolux OCP API client.

Implements the full OCP REST API as used by the AEG iOS app:
  - Client credentials -> Identity providers -> Gigya login -> Token exchange
  - Appliance listing, details, capabilities, commands
  - Token refresh
"""

from __future__ import annotations

import base64
import json
import logging
import time
from typing import Any

import aiohttp

from .const import (
    API_BASE_URL,
    BRANDS,
    BRAND_AEG,
    ENDPOINT_APPLIANCE,
    ENDPOINT_APPLIANCE_CAPABILITIES,
    ENDPOINT_APPLIANCE_COMMAND,
    ENDPOINT_APPLIANCES,
    ENDPOINT_APPLIANCES_INFO,
    ENDPOINT_CURRENT_USER,
    ENDPOINT_IDENTITY_PROVIDERS,
    ENDPOINT_TOKEN,
    GRANT_CLIENT_CREDENTIALS,
    GRANT_REFRESH_TOKEN,
    GRANT_TOKEN_EXCHANGE,
)
from .gigya import GigyaAuthError, GigyaClient, GigyaError

_LOGGER = logging.getLogger(__name__)


class OcpApiError(Exception):
    """Base exception for OCP API errors."""


class OcpAuthError(OcpApiError):
    """Authentication error (invalid credentials or expired tokens)."""


class OcpConnectionError(OcpApiError):
    """Connection error (network, DNS, timeout)."""


class OcpApi:
    """Client for the Electrolux OCP API."""

    def __init__(
        self,
        username: str,
        password: str,
        country_code: str,
        brand: str = BRAND_AEG,
    ) -> None:
        """Initialize the OCP API client.

        Args:
            username: User's email address.
            password: User's password.
            country_code: ISO 3166-1 alpha-2 country code (e.g. "RO").
            brand: Brand name ("AEG" or "Electrolux").
        """
        self._username = username
        self._password = password
        self._country_code = country_code.upper()
        self._brand = brand

        brand_config = BRANDS[brand]
        self._api_key = brand_config["api_key"]
        self._client_id = brand_config["client_id"]
        self._client_secret = brand_config["client_secret"]

        self._session: aiohttp.ClientSession | None = None
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._token_expiry: float = 0

    async def async_init(self) -> None:
        """Create the aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()

    async def async_close(self) -> None:
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    @property
    def is_authenticated(self) -> bool:
        """Check if we have a valid (non-expired) access token."""
        return (
            self._access_token is not None
            and time.time() < self._token_expiry
        )

    def get_tokens(self) -> dict[str, Any]:
        """Return current token state for persistence.

        Returns:
            Dict with access_token, refresh_token, token_expiry.
        """
        return {
            "access_token": self._access_token,
            "refresh_token": self._refresh_token,
            "token_expiry": self._token_expiry,
        }

    def set_tokens(
        self,
        access_token: str,
        refresh_token: str,
        token_expiry: float,
    ) -> None:
        """Restore tokens from persistent storage.

        Args:
            access_token: The bearer token.
            refresh_token: The refresh token.
            token_expiry: Unix timestamp when access_token expires.
        """
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._token_expiry = token_expiry

    async def authenticate(self) -> None:
        """Perform full authentication flow.

        Steps:
          1. Client credentials login (get initial token)
          2. Get identity providers (Gigya config)
          3. Gigya login (get JWT id_token)
          4. Token exchange (get OCP access_token + refresh_token)

        Raises:
            OcpAuthError: If authentication fails.
            OcpConnectionError: If network error occurs.
        """
        self._ensure_session()

        try:
            # Step 1: Client credentials
            cc_token = await self._client_credentials_login()

            # Step 2: Get Gigya config
            gigya_domain, gigya_api_key = await self._get_identity_providers(
                cc_token
            )

            # Step 3: Gigya login -> JWT
            gigya_client = GigyaClient(
                self._session, gigya_api_key, gigya_domain
            )
            id_token = await gigya_client.login(
                self._username, self._password
            )

            # Step 4: Token exchange
            await self._token_exchange(id_token)

            _LOGGER.debug("OCP authentication successful for %s", self._username)

        except GigyaAuthError as err:
            raise OcpAuthError(f"Invalid credentials: {err}") from err
        except GigyaError as err:
            raise OcpApiError(f"Gigya error: {err}") from err
        except aiohttp.ClientError as err:
            raise OcpConnectionError(
                f"Connection error during authentication: {err}"
            ) from err

    async def refresh_access_token(self) -> None:
        """Refresh the access token using the refresh token.

        Raises:
            OcpAuthError: If refresh fails (token expired/revoked).
            OcpConnectionError: If network error occurs.
        """
        self._ensure_session()

        if not self._refresh_token:
            raise OcpAuthError("No refresh token available")

        try:
            url = f"{API_BASE_URL}{ENDPOINT_TOKEN}"
            payload = {
                "grantType": GRANT_REFRESH_TOKEN,
                "clientId": self._client_id,
                "clientSecret": self._client_secret,
                "refreshToken": self._refresh_token,
            }

            async with self._session.post(
                url,
                json=payload,
                headers={"x-api-key": self._api_key},
            ) as resp:
                if resp.status in (401, 403):
                    raise OcpAuthError(
                        "Refresh token expired or revoked"
                    )
                resp.raise_for_status()
                data = await resp.json()

            self._update_tokens(data)
            _LOGGER.debug("OCP token refreshed successfully")

        except aiohttp.ClientResponseError as err:
            if err.status in (401, 403):
                raise OcpAuthError(
                    f"Refresh token rejected: {err}"
                ) from err
            raise OcpConnectionError(
                f"Token refresh failed: {err}"
            ) from err
        except aiohttp.ClientError as err:
            raise OcpConnectionError(
                f"Connection error during token refresh: {err}"
            ) from err

    async def ensure_authenticated(self) -> None:
        """Ensure we have a valid access token, refreshing or re-authenticating.

        Tries refresh first. If refresh fails, does a full re-authentication.
        """
        if self.is_authenticated:
            return

        if self._refresh_token:
            try:
                await self.refresh_access_token()
                return
            except OcpAuthError:
                _LOGGER.debug(
                    "Refresh token expired, performing full authentication"
                )

        await self.authenticate()

    # ---- Appliance API Methods ----

    async def get_appliances(self) -> list[dict[str, Any]]:
        """Get all appliances for the authenticated user.

        Returns:
            List of appliance dicts.
        """
        await self.ensure_authenticated()
        url = f"{API_BASE_URL}{ENDPOINT_APPLIANCES}"
        params = {"includeMetadata": "true"}
        return await self._api_get(url, params=params)

    async def get_appliance(self, appliance_id: str) -> dict[str, Any]:
        """Get a single appliance by ID.

        Args:
            appliance_id: The appliance's unique ID.

        Returns:
            Appliance dict.
        """
        await self.ensure_authenticated()
        url = f"{API_BASE_URL}{ENDPOINT_APPLIANCE.format(appliance_id=appliance_id)}"
        params = {"includeMetadata": "true"}
        return await self._api_get(url, params=params)

    async def get_appliance_capabilities(
        self, appliance_id: str
    ) -> dict[str, Any]:
        """Get capabilities for an appliance.

        Args:
            appliance_id: The appliance's unique ID.

        Returns:
            Capabilities dict.
        """
        await self.ensure_authenticated()
        url = f"{API_BASE_URL}{ENDPOINT_APPLIANCE_CAPABILITIES.format(appliance_id=appliance_id)}"
        return await self._api_get(url)

    async def execute_command(
        self, appliance_id: str, command: dict[str, Any]
    ) -> dict[str, Any]:
        """Send a command to an appliance.

        Args:
            appliance_id: The appliance's unique ID.
            command: Command payload dict.

        Returns:
            Response dict.
        """
        await self.ensure_authenticated()
        url = f"{API_BASE_URL}{ENDPOINT_APPLIANCE_COMMAND.format(appliance_id=appliance_id)}"
        return await self._api_put(url, json=command)

    async def get_appliances_info(
        self, appliance_ids: list[str]
    ) -> list[dict[str, Any]]:
        """Get info for multiple appliances.

        Args:
            appliance_ids: List of appliance IDs.

        Returns:
            List of appliance info dicts.
        """
        await self.ensure_authenticated()
        url = f"{API_BASE_URL}{ENDPOINT_APPLIANCES_INFO}"
        payload = [{"applianceId": aid} for aid in appliance_ids]
        return await self._api_post(url, json=payload)

    async def get_current_user(self) -> dict[str, Any]:
        """Get the current authenticated user's info.

        Returns:
            User info dict.
        """
        await self.ensure_authenticated()
        url = f"{API_BASE_URL}{ENDPOINT_CURRENT_USER}"
        return await self._api_get(url)

    # ---- Internal Auth Flow Methods ----

    async def _client_credentials_login(self) -> str:
        """Step 1: Get a client_credentials token.

        Returns:
            Access token from client_credentials grant.
        """
        url = f"{API_BASE_URL}{ENDPOINT_TOKEN}"
        payload = {
            "grantType": GRANT_CLIENT_CREDENTIALS,
            "clientId": self._client_id,
            "clientSecret": self._client_secret,
            "scope": "",
        }

        async with self._session.post(
            url,
            json=payload,
            headers={"x-api-key": self._api_key},
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()

        return data["accessToken"]

    async def _get_identity_providers(
        self, cc_token: str
    ) -> tuple[str, str]:
        """Step 2: Get Gigya identity provider configuration.

        Args:
            cc_token: Client credentials access token.

        Returns:
            Tuple of (gigya_domain, gigya_api_key).
        """
        url = f"{API_BASE_URL}{ENDPOINT_IDENTITY_PROVIDERS.format(brand=self._brand, country=self._country_code)}"

        async with self._session.get(
            url,
            headers={
                "Authorization": f"Bearer {cc_token}",
                "x-api-key": self._api_key,
            },
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()

        # The response is a list of identity providers
        # Find the Gigya one (typically the first/only one)
        for provider in data:
            if provider.get("type") == "gigya":
                domain = provider.get("domain")
                api_key = provider.get("apiKey")
                if domain and api_key:
                    return domain, api_key

        # Fallback: try first provider
        if data:
            provider = data[0]
            domain = provider.get("domain", "")
            api_key = provider.get("apiKey", "")
            if domain and api_key:
                return domain, api_key

        raise OcpApiError(
            "No suitable identity provider found in response"
        )

    async def _token_exchange(self, id_token: str) -> None:
        """Step 4: Exchange Gigya JWT for OCP tokens.

        The OCP API requires the Origin-Country-Code header, which is
        extracted from the JWT's 'country' claim (e.g. "RO").

        Args:
            id_token: JWT from Gigya getJWT call (must include country claim).
        """
        # Decode JWT to extract country code for required header
        country_code = self._decode_jwt_country(id_token)

        url = f"{API_BASE_URL}{ENDPOINT_TOKEN}"
        payload = {
            "grantType": GRANT_TOKEN_EXCHANGE,
            "clientId": self._client_id,
            "clientSecret": self._client_secret,
            "idToken": id_token,
            "scope": "",
        }

        async with self._session.post(
            url,
            json=payload,
            headers={
                "x-api-key": self._api_key,
                "Origin-Country-Code": country_code,
            },
        ) as resp:
            if resp.status in (401, 403):
                raise OcpAuthError("Token exchange rejected")
            resp.raise_for_status()
            data = await resp.json()

        self._update_tokens(data)

    @staticmethod
    def _decode_jwt_country(id_token: str) -> str:
        """Decode the country claim from a JWT token.

        Args:
            id_token: JWT string.

        Returns:
            Country code string (e.g. "RO"). Falls back to empty string.
        """
        try:
            payload_b64 = id_token.split(".")[1]
            # Add padding for base64 decoding
            payload_b64 += "=" * (4 - len(payload_b64) % 4)
            payload = json.loads(base64.b64decode(payload_b64).decode("utf-8"))
            return payload.get("country", "")
        except (IndexError, ValueError, json.JSONDecodeError) as err:
            _LOGGER.warning("Failed to decode JWT country claim: %s", err)
            return ""

    def _update_tokens(self, data: dict[str, Any]) -> None:
        """Update stored tokens from a token response.

        Args:
            data: Token endpoint response.
        """
        self._access_token = data["accessToken"]
        self._refresh_token = data.get("refreshToken", self._refresh_token)
        expires_in = data.get("expiresIn", 3600)
        # Expire 60 seconds early to avoid edge cases
        self._token_expiry = time.time() + expires_in - 60

    # ---- Internal HTTP Methods ----

    async def _api_get(
        self, url: str, params: dict[str, str] | None = None
    ) -> Any:
        """Make an authenticated GET request.

        Args:
            url: Full URL.
            params: Optional query parameters.

        Returns:
            Parsed JSON response.
        """
        self._ensure_session()
        headers = self._auth_headers()

        async with self._session.get(
            url, headers=headers, params=params
        ) as resp:
            if resp.status in (401, 403):
                raise OcpAuthError(f"API request unauthorized: {resp.status}")
            resp.raise_for_status()
            return await resp.json()

    async def _api_post(
        self, url: str, json: Any = None
    ) -> Any:
        """Make an authenticated POST request.

        Args:
            url: Full URL.
            json: JSON body.

        Returns:
            Parsed JSON response.
        """
        self._ensure_session()
        headers = self._auth_headers()

        async with self._session.post(
            url, headers=headers, json=json
        ) as resp:
            if resp.status in (401, 403):
                raise OcpAuthError(f"API request unauthorized: {resp.status}")
            resp.raise_for_status()
            return await resp.json()

    async def _api_put(
        self, url: str, json: Any = None
    ) -> Any:
        """Make an authenticated PUT request.

        Args:
            url: Full URL.
            json: JSON body.

        Returns:
            Parsed JSON response.
        """
        self._ensure_session()
        headers = self._auth_headers()

        async with self._session.put(
            url, headers=headers, json=json
        ) as resp:
            if resp.status in (401, 403):
                raise OcpAuthError(f"API request unauthorized: {resp.status}")
            resp.raise_for_status()
            return await resp.json()

    def _auth_headers(self) -> dict[str, str]:
        """Build authentication headers."""
        return {
            "Authorization": f"Bearer {self._access_token}",
            "x-api-key": self._api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _ensure_session(self) -> None:
        """Ensure the aiohttp session is available."""
        if self._session is None or self._session.closed:
            raise OcpConnectionError(
                "API session not initialized. Call async_init() first."
            )
