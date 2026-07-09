from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import timedelta


@dataclass(frozen=True)
class BitwardenSendResult:
    send_id: str
    access_url: str


class BitwardenSendClient:
    def create_secret_send(self, name: str, secret_text: str, expires_in: timedelta, max_access_count: int = 1) -> BitwardenSendResult:
        days = max(1, int(expires_in.total_seconds() // 86400))
        command = [
            "bw",
            "send",
            "create",
            "--type",
            "text",
            "--name",
            name,
            "--max-access-count",
            str(max_access_count),
            "--expiration-date",
            f"{days}d",
            "--raw",
            secret_text,
        ]
        # The secret is passed only to the Bitwarden CLI process and is never logged.
        completed = subprocess.run(command, check=True, capture_output=True, text=True)
        payload = json.loads(completed.stdout)
        return BitwardenSendResult(send_id=payload["id"], access_url=payload["accessUrl"])
