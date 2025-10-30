import socket  # Add at the top with other imports
from .settings import Settings
import httpx
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
import hmac
import hashlib
import mimetypes
from pathlib import Path
import time
import asyncio


logger = logging.getLogger(__name__)

# -----------------------------
# Response dataclasses
# -----------------------------
@dataclass(frozen=True)
class MessageResponse:
    success: bool
    message_id: Optional[str] = None
    error_message: Optional[str] = None
    error_code: Optional[int] = None
    error_type: Optional[str] = None
    error_user_msg: Optional[str] = None
    raw_response: Optional[Dict[str, Any]] = field(default=None, repr=False)
    extra: Dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_api_response(cls, response: Dict[str, Any]) -> "MessageResponse":
        if "messages" in response:
            return cls(
                success=True,
                message_id=response["messages"][0].get("id"),
                raw_response=response,
                extra={k: v for k, v in response.items() if k not in {"messages", "contacts"}}
            )
        if "error" in response:
            err = response["error"]
            return cls(
                success=False,
                error_message=err.get("message"),
                error_code=err.get("code"),
                error_type=err.get("type"),
                error_user_msg=err.get("error_user_msg"),
                raw_response=response,
                extra={k: v for k, v in err.items() if k not in {"message", "code", "type", "error_user_msg"}}
            )
        return cls(success=False, error_message="Unknown response format", raw_response=response)

    @classmethod
    def from_success(cls, message_id: str, raw_response: Optional[Dict[str, Any]] = None) -> "MessageResponse":
        return cls(success=True, message_id=message_id, raw_response=raw_response)

    @classmethod
    def from_error(cls, error_message: str, code: Optional[int] = None,
                   raw_response: Optional[Dict[str, Any]] = None) -> "MessageResponse":
        return cls(success=False, error_message=error_message, error_code=code, raw_response=raw_response)

    def is_success(self) -> bool:
        return self.success

    def is_error(self) -> bool:
        return not self.success


@dataclass
class MediaUploadResponse:
    success: bool
    media_id: Optional[str] = None
    error_message: Optional[str] = None


# -----------------------------
# WhatsApp API Client
# -----------------------------
class WhatsAppClient:
    MAX_RETRIES = 3
    RETRY_DELAY = 2  # seconds

    def __init__(self):
        self.base_url = f"{Settings.GRAPH_API_URL}/{Settings.WHATSAPP_PHONE_ID}/messages"
        self.media_url = f"{Settings.GRAPH_API_URL}/{Settings.WHATSAPP_PHONE_ID}/media"
        self.headers = Settings.headers()
        Settings.validate()
        self.client_limits = httpx.Limits(max_connections=10, max_keepalive_connections=5)

    # -----------------------------
    # Helper to execute POST requests with retry
    # -----------------------------
    def _post(self, url: str, json: Optional[Dict[str, Any]] = None, data: Optional[Dict[str, Any]] = None,
              files: Optional[Dict[str, Any]] = None, timeout: float = 10.0) -> MessageResponse:

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                with httpx.Client(timeout=timeout, headers=self.headers, limits=self.client_limits) as client:
                    response = client.post(url, json=json, data=data, files=files)
                    response.raise_for_status()
                    return MessageResponse.from_api_response(response.json())

            except httpx.HTTPStatusError as exc:
                logger.error(f"HTTP error {exc.response.status_code}: {exc.response.text}", exc_info=True)
                return MessageResponse.from_error(f"HTTP {exc.response.status_code}: {exc.response.text}")
            except (httpx.RequestError, socket.gaierror) as exc:
                logger.warning(f"Network error on attempt {attempt}/{self.MAX_RETRIES}: {exc}", exc_info=True)
                if attempt < self.MAX_RETRIES:
                    time.sleep(self.RETRY_DELAY)
                    continue
                return MessageResponse.from_error(str(exc))
            except Exception as exc:
                logger.error(f"Unexpected error on POST request: {exc}", exc_info=True)
                return MessageResponse.from_error(str(exc))

    # -----------------------------
    # Message send
    # -----------------------------
    def send(self, payload: dict) -> MessageResponse:
        return self._post(self.base_url, json=payload, timeout=Settings.DEFAULT_TIMEOUT)

    async def asend(self, payload: dict) -> MessageResponse:
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=Settings.DEFAULT_TIMEOUT, headers=self.headers, limits=self.client_limits) as client:
                    response = await client.post(self.base_url, json=payload)
                    response.raise_for_status()
                    return MessageResponse.from_api_response(response.json())
            except httpx.HTTPStatusError as exc:
                logger.error(f"HTTP error: {exc.response.status_code} - {exc.response.text}", exc_info=True)
                return MessageResponse.from_error(f"HTTP {exc.response.status_code}: {exc.response.text}")
            except (httpx.RequestError, socket.gaierror) as exc:
                logger.warning(f"Async network error on attempt {attempt}/{self.MAX_RETRIES}: {exc}", exc_info=True)
                if attempt < self.MAX_RETRIES:
                    await asyncio.sleep(self.RETRY_DELAY)
                    continue
                return MessageResponse.from_error(str(exc))
            except Exception as exc:
                logger.error(f"Async send unexpected error: {exc}", exc_info=True)
                return MessageResponse.from_error(str(exc))

    # -----------------------------
    # Media upload
    # -----------------------------
    def upload_media(self, file_path: str, mime_type: Optional[str] = None) -> MediaUploadResponse:
        path = Path(file_path)
        if not path.exists():
            return MediaUploadResponse(success=False, error_message=f"File not found: {file_path}")

        if not mime_type:
            mime_type, _ = mimetypes.guess_type(file_path)
            if not mime_type:
                return MediaUploadResponse(success=False, error_message="Could not determine MIME type")

        files = {"file": (path.name, open(path, "rb"), mime_type)}
        data = {"messaging_product": "whatsapp"}
        response = self._post(self.media_url, data=data, files=files, timeout=60.0)
        files["file"][1].close()
        if response.success:
            return MediaUploadResponse(success=True, media_id=response.raw_response.get("id"))
        return MediaUploadResponse(success=False, error_message=response.error_message)

    async def upload_media_async(self, file_path: str, mime_type: Optional[str] = None) -> MediaUploadResponse:
        path = Path(file_path)
        if not path.exists():
            return MediaUploadResponse(success=False, error_message=f"File not found: {file_path}")

        if not mime_type:
            mime_type, _ = mimetypes.guess_type(file_path)
            if not mime_type:
                return MediaUploadResponse(success=False, error_message="Could not determine MIME type")

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=60.0, headers=self.headers, limits=self.client_limits) as client:
                    with open(path, "rb") as f:
                        files = {"file": (path.name, f, mime_type)}
                        data = {"messaging_product": "whatsapp"}
                        response = await client.post(self.media_url, data=data, files=files)
                        response.raise_for_status()
                        return MediaUploadResponse(success=True, media_id=response.json().get("id"))
            except (httpx.RequestError, socket.gaierror) as exc:
                logger.warning(f"Async media upload network error attempt {attempt}/{self.MAX_RETRIES}: {exc}", exc_info=True)
                if attempt < self.MAX_RETRIES:
                    await asyncio.sleep(self.RETRY_DELAY)
                    continue
                return MediaUploadResponse(success=False, error_message=str(exc))
            except Exception as exc:
                logger.error(f"Async media upload unexpected error: {exc}", exc_info=True)
                return MediaUploadResponse(success=False, error_message=str(exc))

    # -----------------------------
    # Mark message as read
    # -----------------------------
    def mark_as_read(self, message_id: str) -> MessageResponse:
        payload = {"messaging_product": "whatsapp", "status": "read", "message_id": message_id}
        return self._post(self.base_url, json=payload, timeout=10.0)

    # -----------------------------
    # Utility methods
    # -----------------------------
    @staticmethod
    def validate_webhook_signature(payload: str, signature: str) -> bool:
        if not Settings.WHATSAPP_APP_SECRET:
            logger.warning("WHATSAPP_APP_SECRET not set, skipping validation")
            return True
            
        expected_signature = hmac.new(
            Settings.WHATSAPP_APP_SECRET.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(f"sha256={expected_signature}", signature)

    @staticmethod
    def validate_phone_number(phone: str) -> tuple[bool, str]:
        cleaned = phone.replace(" ", "").replace("-", "")
        digits = cleaned[1:]
        if not digits.isdigit():
            return False, "Phone number must contain only digits"
        if not (7 <= len(digits) <= 15):
            return False, "Phone number must be 7-15 digits long"
        return True, cleaned


# Shared client instance
WHATSAPP_CLIENT = WhatsAppClient()
