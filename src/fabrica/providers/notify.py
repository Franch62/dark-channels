"""Avisos de andamento (Telegram quando configurado, senão só o log)."""
from __future__ import annotations

import logging
import os
from typing import Protocol

import httpx

log = logging.getLogger("fabrica")


class Notifier(Protocol):
    def send(self, text: str) -> None: ...


class LogNotifier:
    def send(self, text: str) -> None:
        log.info("aviso: %s", text)


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str):
        self.url = f"https://api.telegram.org/bot{token}/sendMessage"
        self.chat_id = chat_id

    def send(self, text: str) -> None:
        try:
            httpx.post(self.url, json={"chat_id": self.chat_id, "text": text}, timeout=15).raise_for_status()
        except httpx.HTTPError as e:  # aviso nunca derruba o pipeline
            log.warning("falha ao enviar Telegram: %s", e)


def make_notifier() -> Notifier:
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    return TelegramNotifier(token, chat) if token and chat else LogNotifier()
