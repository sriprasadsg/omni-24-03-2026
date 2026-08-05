"""ITAM Labels offline-generation proof — Phase 58 Plan 03, Task 2.

This is the executable form of ROADMAP success criterion 3 for the two
generators built so far (Plan 04 adds the third and last, the label-sheet
PDF generator, to this same file). It exists because a transitive
dependency could reach the network even though the top-level
itam_label_service.py module does not import an HTTP client — so the proof
has to be behavioral, over the whole call graph, not a source inspection
(58-RESEARCH.md Common Pitfalls Pitfall 1).
"""
import socket
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

# Imported at module scope, before any patching, so the import-time cost is
# paid outside the blocked window and the test measures generation, not
# import.
import itam_label_service


def block_all_sockets(monkeypatch):
    """Replace socket.socket, socket.create_connection and
    socket.getaddrinfo on the stdlib socket module itself (not at a
    consumer module's bound name) with a function raising AssertionError
    naming label generation as the caller — so any consumer anywhere
    beneath, including inside qrcode, python-barcode, Pillow and their
    transitive imports, is caught.

    Uses monkeypatch.setattr so the patches unwind automatically at test
    teardown and cannot leak into unrelated tests in the same session.
    """
    def _blocked(*args, **kwargs):
        raise AssertionError(
            "label generation attempted a socket operation — the offline "
            "guarantee (ROADMAP success criterion 3) was violated"
        )

    monkeypatch.setattr(socket, "socket", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)
    monkeypatch.setattr(socket, "getaddrinfo", _blocked)


class TestOfflineGeneration:
    """Both generators are proven to complete with every socket entry point
    raising. Plan 04 extends this file with the label-sheet generator, the
    third and last generator in this phase.

    Selectable via -k offline_network_blocked.
    """

    def test_offline_network_blocked_qr_generation_succeeds(self, monkeypatch):
        block_all_sockets(monkeypatch)
        png = itam_label_service.generate_qr_png("IT-0001")
        assert png.startswith(b"\x89PNG\r\n\x1a\n")

    def test_offline_network_blocked_barcode_generation_succeeds(self, monkeypatch):
        block_all_sockets(monkeypatch)
        png = itam_label_service.generate_barcode_png("IT-0001")
        assert png.startswith(b"\x89PNG\r\n\x1a\n")

    def test_offline_network_blocked_negative_control_socket_really_blocked(self, monkeypatch):
        """Negative control: proves the block is real. Without this, a test
        that stops patching correctly would still go green and the offline
        guarantee would quietly stop being verified."""
        block_all_sockets(monkeypatch)
        with pytest.raises(AssertionError):
            socket.socket()
