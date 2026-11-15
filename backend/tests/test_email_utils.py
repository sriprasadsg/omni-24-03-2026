"""email_utils.send_email_async (Phase 86 review IN-04): False, never an exception, and no addresses in the logs."""
import logging
from unittest.mock import AsyncMock

import email_utils


async def test_no_smtp_host_skips_without_connecting(monkeypatch, caplog):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    send = AsyncMock()
    monkeypatch.setattr(email_utils.aiosmtplib, "send", send)

    with caplog.at_level(logging.WARNING):
        assert await email_utils.send_email_async("ann@example.test", "Hi", "<p>x</p>") is False

    send.assert_not_awaited()
    assert "ann@example.test" not in caplog.text


async def test_a_subject_with_a_line_break_returns_false_instead_of_raising(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    send = AsyncMock()
    monkeypatch.setattr(email_utils.aiosmtplib, "send", send)

    assert await email_utils.send_email_async("ann@example.test", "Hi\r\nBcc: x@example.test", "<p>x</p>") is False
    send.assert_not_awaited()


async def test_a_send_logs_the_recipient_count_not_the_addresses(monkeypatch, caplog):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setattr(email_utils.aiosmtplib, "send", AsyncMock())

    with caplog.at_level(logging.INFO):
        assert await email_utils.send_email_async(["ann@example.test", "bo@example.test"], "Hi", "<p>x</p>", "x")

    assert "2 recipient(s)" in caplog.text and "example.test" not in caplog.text
