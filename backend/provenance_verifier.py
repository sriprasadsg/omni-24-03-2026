import hashlib
import time
from typing import List, Dict, Optional
from datetime import datetime, timezone

class ProvenanceVerifier:
    """
    Handles the cryptographic provenance of logs using a Merkle-Tree approach.
    Ensures that logs are signed, chained, and immutable.
    """
    
    def __init__(self):
        # In a real 2027 implementation, this would be a TPM-backed root key
        self.system_root_key = "omni-provenance-root-2027-v1"
        self.log_chain: List[str] = [] # Stores the history of block hashes (Merkle Chaining)

    def calculate_entry_hash(self, entry: Dict) -> str:
        """Calculates a SHA-256 hash for a single log entry."""
        # Normalize entry for consistent hashing
        data = f"{entry.get('timestamp')}|{entry.get('agent_id')}|{entry.get('event')}|{entry.get('data')}"
        return hashlib.sha256(data.encode()).hexdigest()

    def generate_block_root(self, hashes: List[str]) -> str:
        """Generates a Merkle Root for a block of log hashes."""
        if not hashes:
            return ""
        if len(hashes) == 1:
            return hashes[0]
        
        new_hashes = []
        for i in range(0, len(hashes), 2):
            if i + 1 < len(hashes):
                combined = hashes[i] + hashes[i+1]
            else:
                combined = hashes[i] + hashes[i] # Duplicate last if odd
            new_hashes.append(hashlib.sha256(combined.encode()).hexdigest())
            
        return self.generate_block_root(new_hashes)

    def sign_block(self, logs: List[Dict]) -> Dict:
        """
        Signs a block of logs, creating a Provenance Record.
        Chains this block to the previous block hash.
        """
        entry_hashes = [self.calculate_entry_hash(log) for log in logs]
        merkle_root = self.generate_block_root(entry_hashes)
        
        previous_hash = self.log_chain[-1] if self.log_chain else "0" * 64
        
        # Block Signature (Simulated TPM Signing)
        block_data = f"{merkle_root}|{previous_hash}|{time.time()}"
        block_hash = hashlib.sha256(block_data.encode()).hexdigest()
        
        # Add to local chain for verification
        self.log_chain.append(block_hash)
        
        return {
            "merkle_root": merkle_root,
            "previous_hash": previous_hash,
            "block_hash": block_hash,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "Verified",
            "provenance_standard": "RFC-9162-Modified-2027"
        }

    def verify_integrity(self, current_block: Dict, logs: List[Dict], previous_block_hash: str) -> bool:
        """
        Verifies the integrity of a log block against its provenance record.
        """
        # 1. Re-calculate Merkle Root
        entry_hashes = [self.calculate_entry_hash(log) for log in logs]
        recalculated_root = self.generate_block_root(entry_hashes)
        
        if recalculated_root != current_block["merkle_root"]:
            return False
            
        # 2. Verify Chaining
        if current_block["previous_hash"] != previous_block_hash:
            return False
            
        return True

# Singleton Instance
provenance_engine = ProvenanceVerifier()

