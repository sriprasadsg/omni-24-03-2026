import logging
import logging.handlers
import os
from datetime import datetime

class EncryptedFileHandler(logging.handlers.RotatingFileHandler):
    """
    Custom logging handler that encrypts each log line before writing to disk. The file rolls over at max_bytes
    (agent.log -> agent.log.1 ...), keeping backup_count old files: agent.log used to grow without bound (~1 GB).
    """
    def __init__(self, filename, security_mgr, mode='a', encoding=None, delay=False,
                 max_bytes=50 * 1024 * 1024, backup_count=5):
        self.security_mgr = security_mgr
        super().__init__(filename, mode, max_bytes, backup_count, encoding, delay)

    def emit(self, record):
        try:
            if self.shouldRollover(record):
                self.doRollover()
            msg = self.format(record)
            # Add a clear marker for encrypted lines
            encrypted_msg = self.security_mgr.encrypt_data(msg)
            # We append a newline because encrypt_data returns a single block
            stream = self.stream
            stream.write("ENC:" + encrypted_msg + "\n")
            self.flush()
        except Exception:
            self.handleError(record)

def setup_secure_logging(log_file, security_mgr):
    """
    Configures the root logger to use both a console handler (plaintext) 
    and an encrypted file handler.
    """
    root_logger = logging.getLogger()
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        
    root_logger.setLevel(logging.INFO)

    # Console Handler (Plaintext)
    console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # Encrypted File Handler
    file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler = EncryptedFileHandler(log_file, security_mgr)
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    logging.info("Secure encrypted logging initialized.")
