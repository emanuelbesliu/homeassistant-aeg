"""WebSocket client for real-time appliance updates from OCP API.

Connects to wss://ws.ocp.electrolux.one with auth headers and receives
real-time state changes for registered appliances.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any

import aiohttp

from .const import WS_BASE_URL, WS_HEARTBEAT_INTERVAL, WS_RECONNECT_DELAY

_LOGGER = logging.getLogger(__name__)


class OcpWebSocket:
    """WebSocket client for OCP real-time appliance updates."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        access_token: str,
        api_key: str,
        appliance_ids: list[str],
        on_message: Callable[[dict[str, Any]], None],
        on_disconnect: Callable[[], None] | None = None,
    ) -> None:
        """Initialize the WebSocket client.

        Args:
            session: aiohttp session.
            access_token: OCP bearer token.
            api_key: Brand-specific API key.
            appliance_ids: List of appliance IDs to subscribe to.
            on_message: Callback for incoming messages.
            on_disconnect: Callback when connection is lost.
        """
        self._session = session
        self._access_token = access_token
        self._api_key = api_key
        self._appliance_ids = appliance_ids
        self._on_message = on_message
        self._on_disconnect = on_disconnect

        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._listen_task: asyncio.Task | None = None
        self._heartbeat_task: asyncio.Task | None = None
        self._running = False

    @property
    def connected(self) -> bool:
        """Check if WebSocket is connected."""
        return self._ws is not None and not self._ws.closed

    def update_token(self, access_token: str) -> None:
        """Update the access token for reconnection.

        Args:
            access_token: New bearer token.
        """
        self._access_token = access_token

    def update_appliances(self, appliance_ids: list[str]) -> None:
        """Update the list of appliance IDs to subscribe to.

        Args:
            appliance_ids: New list of appliance IDs.
        """
        self._appliance_ids = appliance_ids

    async def connect(self) -> None:
        """Establish WebSocket connection and start listening."""
        if self.connected:
            return

        self._running = True

        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "x-api-key": self._api_key,
            "appliances": json.dumps(
                [{"applianceId": aid} for aid in self._appliance_ids]
            ),
            "version": "2",
        }

        try:
            self._ws = await self._session.ws_connect(
                WS_BASE_URL,
                headers=headers,
                heartbeat=WS_HEARTBEAT_INTERVAL,
            )
            _LOGGER.debug(
                "OCP WebSocket connected, watching %d appliances",
                len(self._appliance_ids),
            )

            # Start listener and heartbeat tasks
            self._listen_task = asyncio.create_task(self._listen())
            self._heartbeat_task = asyncio.create_task(self._heartbeat())

        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            _LOGGER.warning("OCP WebSocket connection failed: %s", err)
            self._running = False
            raise

    async def disconnect(self) -> None:
        """Disconnect and stop all tasks."""
        self._running = False

        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None

        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
            self._listen_task = None

        if self._ws and not self._ws.closed:
            await self._ws.close()
            self._ws = None

        _LOGGER.debug("OCP WebSocket disconnected")

    async def _listen(self) -> None:
        """Listen for messages on the WebSocket."""
        try:
            async for msg in self._ws:
                if not self._running:
                    break

                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        self._on_message(data)
                    except json.JSONDecodeError:
                        _LOGGER.warning(
                            "Invalid JSON from WebSocket: %s",
                            msg.data[:200],
                        )
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    _LOGGER.error(
                        "WebSocket error: %s", self._ws.exception()
                    )
                    break
                elif msg.type in (
                    aiohttp.WSMsgType.CLOSE,
                    aiohttp.WSMsgType.CLOSING,
                    aiohttp.WSMsgType.CLOSED,
                ):
                    _LOGGER.debug("WebSocket closed by server")
                    break

        except asyncio.CancelledError:
            raise
        except Exception:
            _LOGGER.exception("Unexpected error in WebSocket listener")
        finally:
            if self._running and self._on_disconnect:
                self._on_disconnect()

    async def _heartbeat(self) -> None:
        """Send periodic heartbeat to keep connection alive."""
        try:
            while self._running and self.connected:
                await asyncio.sleep(WS_HEARTBEAT_INTERVAL)
                if self.connected:
                    await self._ws.ping()
                    _LOGGER.debug("WebSocket heartbeat sent")
        except asyncio.CancelledError:
            raise
        except Exception:
            _LOGGER.debug("WebSocket heartbeat failed", exc_info=True)
