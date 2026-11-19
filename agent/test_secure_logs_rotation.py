"""The agent's encrypted log rolls over instead of growing without bound (agent.log reached ~1 GB)."""
import logging

from secure_logs import EncryptedFileHandler


class _Reverse:
    def encrypt_data(self, text):
        return text[::-1]


def test_the_encrypted_log_rolls_over_and_keeps_a_bounded_number_of_files(tmp_path):
    log = tmp_path / "agent.log"
    handler = EncryptedFileHandler(str(log), _Reverse(), max_bytes=400, backup_count=2)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger = logging.getLogger("rotation-test")
    logger.propagate = False
    logger.addHandler(handler)
    try:
        for i in range(60):
            logger.warning("event %03d %s", i, "x" * 20)
    finally:
        logger.removeHandler(handler)
        handler.close()
    files = sorted(p.name for p in tmp_path.iterdir())
    assert files == ["agent.log", "agent.log.1", "agent.log.2"]
    for name in files:
        lines = (tmp_path / name).read_text().splitlines()
        assert lines and all(line.startswith("ENC:") for line in lines)
        assert (tmp_path / name).stat().st_size <= 400 + 60
    assert "event 059"[::-1] in log.read_text(), "the newest line is in the current file"
