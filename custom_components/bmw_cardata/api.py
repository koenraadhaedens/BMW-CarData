"""BMW CarData OAuth client."""

from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import secrets
from typing import Any

from aiohttp import ClientResponseError, ClientSession

from .const import (
    DEVICE_CODE_GRANT_TYPE,
    DEVICE_CODE_PATH,
    DEVICE_CODE_RESPONSE_TYPE,
    OAUTH_BASE_URL,
    PKCE_CHALLENGE_METHOD,
    REFRESH_TOKEN_GRANT_TYPE,
    TOKEN_PATH,
)


class BmwCarDataAuthError(Exception):
    """Base auth error."""


class BmwCarDataApiError(BmwCarDataAuthError):
    """Unexpected API error."""


class BmwCarDataOAuthError(BmwCarDataAuthError):
    """Expected OAuth error from endpoint."""

    def __init__(self, error: str, description: str | None = None) -> None:
        """Create OAuth error."""
        super().__init__(description or error)
        self.error = error
        self.description = description


@dataclass(slots=True)
class DeviceCodeResponse:
    """Response from device-code initiation."""

    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int


@dataclass(slots=True)
class TokenResponse:
    """Token response."""

    access_token: str
    token_type: str
    expires_in: int
    refresh_token: str
    scope: str | None
    gcid: str | None
    id_token: str | None


@dataclass(slots=True)
class PkcePair:
    """Generated PKCE verifier/challenge pair."""

    code_verifier: str
    code_challenge: str


class BmwCarDataAuthApi:
    """OAuth client used to authenticate the MQTT connection."""

    def __init__(self, session: ClientSession) -> None:
        """Initialize the OAuth client."""
        self._session = session

    @staticmethod
    def generate_pkce_pair() -> PkcePair:
        """Create a PKCE code verifier and S256 challenge."""
        code_verifier = secrets.token_urlsafe(64)
        digest = hashlib.sha256(code_verifier.encode("utf-8")).digest()
        code_challenge = base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")
        return PkcePair(code_verifier=code_verifier, code_challenge=code_challenge)

    async def request_device_code(
        self,
        *,
        client_id: str,
        scope: str,
        code_challenge: str,
    ) -> DeviceCodeResponse:
        """Initiate the device code flow."""
        data = await self._post_form(
            DEVICE_CODE_PATH,
            {
                "client_id": client_id,
                "response_type": DEVICE_CODE_RESPONSE_TYPE,
                "scope": scope,
                "code_challenge": code_challenge,
                "code_challenge_method": PKCE_CHALLENGE_METHOD,
            },
        )
        return DeviceCodeResponse(
            device_code=data["device_code"],
            user_code=data["user_code"],
            verification_uri=data["verification_uri"],
            expires_in=int(data.get("expires_in", 0)),
            interval=int(data.get("interval", 5)),
        )

    async def request_token_with_device_code(
        self,
        *,
        client_id: str,
        device_code: str,
        code_verifier: str,
    ) -> TokenResponse:
        """Exchange an authorized device code for tokens."""
        data = await self._post_form(
            TOKEN_PATH,
            {
                "client_id": client_id,
                "device_code": device_code,
                "grant_type": DEVICE_CODE_GRANT_TYPE,
                "code_verifier": code_verifier,
            },
        )
        return self._token_response(data)

    async def refresh_token(
        self,
        *,
        client_id: str,
        refresh_token: str,
    ) -> TokenResponse:
        """Refresh MQTT authentication tokens."""
        data = await self._post_form(
            TOKEN_PATH,
            {
                "grant_type": REFRESH_TOKEN_GRANT_TYPE,
                "refresh_token": refresh_token,
                "client_id": client_id,
            },
        )
        return self._token_response(data)

    @staticmethod
    def _token_response(data: dict[str, Any]) -> TokenResponse:
        """Convert an OAuth payload to a token response."""
        return TokenResponse(
            access_token=data["access_token"],
            token_type=data["token_type"],
            expires_in=int(data.get("expires_in", 0)),
            refresh_token=data["refresh_token"],
            scope=data.get("scope"),
            gcid=data.get("gcid"),
            id_token=data.get("id_token"),
        )

    async def _post_form(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Call an OAuth form endpoint and map errors."""
        try:
            async with self._session.post(
                f"{OAUTH_BASE_URL}{path}",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data=payload,
            ) as response:
                data = await response.json(content_type=None)
                if response.status >= 400:
                    error = data.get("error") if isinstance(data, dict) else None
                    description = (
                        data.get("error_description")
                        if isinstance(data, dict)
                        else None
                    )
                    if error:
                        raise BmwCarDataOAuthError(
                            error=error,
                            description=description,
                        )
                    raise BmwCarDataApiError(
                        f"Unexpected response {response.status} from BMW OAuth endpoint"
                    )
                if not isinstance(data, dict):
                    raise BmwCarDataApiError("Unexpected non-JSON object response")
                return data
        except ClientResponseError as err:
            raise BmwCarDataApiError("HTTP client response error") from err
