"""Persist finsh alerts and optionally mirror them to Slack."""

import os

import requests

from db import database


def send(message, level="INFO"):
    if level not in {"INFO", "WARN"}:
        raise ValueError("알림 등급은 INFO 또는 WARN이어야 합니다")
    database.add_alert(message, level)
    webhook = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook:
        return True
    try:
        response = requests.post(webhook, json={"text": message}, timeout=5)
        response.raise_for_status()
    except requests.RequestException:
        # The durable DB alert is authoritative. Never log the webhook URL.
        database.log("notify", result="FAIL", message="Slack 전송 실패; DB 알림은 저장됨")
        return False
    return True
