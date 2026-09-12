from __future__ import annotations

import smtplib


class FakeSMTPClient:
    created: list[FakeSMTPClient] = []

    def __init__(self, host, port, timeout=None):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.calls = []
        FakeSMTPClient.created.append(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def ehlo(self):
        self.calls.append("ehlo")

    def starttls(self, context=None):
        self.calls.append("starttls")

    def login(self, username, password):
        self.calls.append(("login", username, password))

    def send_message(self, message):
        self.calls.append(("send_message", message))


class RaisingSMTPClient(FakeSMTPClient):
    def login(self, username, password):
        raise smtplib.SMTPAuthenticationError(535, b"bad credentials")
