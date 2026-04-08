"""Meta WhatsApp Cloud API adapter.

Docs: https://developers.facebook.com/docs/whatsapp/cloud-api/reference/messages

Environment variables:

* ``ALDER_WHATSAPP_PHONE_NUMBER_ID`` — the business number's phone-number-id
* ``ALDER_WHATSAPP_ACCESS_TOKEN``    — permanent system user token
* ``ALDER_WHATSAPP_API_VERSION``     — default ``v19.0``
* ``ALDER_WHATSAPP_TIMEOUT_SECS``    — HTTP timeout, default 10

Failure mode: exceptions are caught by the caller (the TaskRunner). This
module is safe to call from a background thread.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Optional

import httpx

log = logging.getLogger(__name__)


class WhatsAppError(RuntimeError):
    pass


class WhatsAppCloudClient:
    def __init__(
        self,
        phone_number_id: Optional[str] = None,
        access_token: Optional[str] = None,
        api_version: Optional[str] = None,
        timeout_secs: Optional[float] = None,
        max_retries: int = 3,
    ) -> None:
        self._phone_number_id = phone_number_id or os.getenv(
            "ALDER_WHATSAPP_PHONE_NUMBER_ID", ""
        )
        self._token = access_token or os.getenv("ALDER_WHATSAPP_ACCESS_TOKEN", "")
        self._version = api_version or os.getenv(
            "ALDER_WHATSAPP_API_VERSION", "v19.0"
        )
        self._timeout = timeout_secs or float(
            os.getenv("ALDER_WHATSAPP_TIMEOUT_SECS", "10")
        )
        self._max_retries = max_retries

    def _endpoint(self) -> str:
        return (
            f"https://graph.facebook.com/{self._version}/"
            f"{self._phone_number_id}/messages"
        )

    def send_text(self, phone_e164: str, body: str) -> None:
        if not (self._phone_number_id and self._token):
            log.warning(
                "WhatsApp credentials are unset — skipping send to %s. Body: %s",
                phone_e164,
                body,
            )
            return

        # Meta expects the recipient *without* the leading '+'.
        to = phone_e164.lstrip("+")

        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": body},
        }
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

        last_err: Optional[Exception] = None
        for attempt in range(1, self._max_retries + 1):
            try:
                with httpx.Client(timeout=self._timeout) as client:
                    r = client.post(self._endpoint(), json=payload, headers=headers)
                if r.status_code >= 500:
                    raise WhatsAppError(
                        f"WhatsApp API {r.status_code}: {r.text[:200]}"
                    )
                if r.status_code >= 400:
                    # 4xx are caller errors — no point retrying.
                    log.error(
                        "WhatsApp send to %s failed: %s %s",
                        phone_e164,
                        r.status_code,
                        r.text[:200],
                    )
                    return
                log.info("WhatsApp message sent to %s", phone_e164)
                return
            except (httpx.TimeoutException, WhatsAppError, httpx.TransportError) as e:
                last_err = e
                backoff = 0.5 * (2 ** (attempt - 1))
                log.warning(
                    "WhatsApp attempt %s/%s to %s failed: %s — retrying in %.2fs",
                    attempt,
                    self._max_retries,
                    phone_e164,
                    e,
                    backoff,
                )
                time.sleep(backoff)

        assert last_err is not None
        raise WhatsAppError(
            f"Failed to send WhatsApp message after {self._max_retries} attempts"
        ) from last_err
