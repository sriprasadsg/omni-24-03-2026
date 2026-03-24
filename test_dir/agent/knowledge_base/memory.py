import json
import time
import logging
from pathlib import Path
from typing import List, Dict

logger = logging.getLogger(__name__)

class AgentMemory:
    """
    Lightweight Knowledge Base for the Agent.
    Stores past experiences to learn from successes and failures.
    Simulates a Vector DB using simple JSON storage for low overhead.
    """
    
    def __init__(self, data_dir="data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        self.memory_file = self.data_dir / "agent_memory.json"
        self.experiences = self._load_memory()

    def _load_memory(self) -> List[Dict]:
        if self.memory_file.exists():
            try:
                return json.loads(self.memory_file.read_text())
            except Exception as e:
                logger.error(f"Failed to load memory: {e}")
                return []
        return []

    def _save_memory(self):
        try:
            self.memory_file.write_text(json.dumps(self.experiences, indent=2))
        except Exception as e:
            logger.error(f"Failed to save memory: {e}")

    def store_experience(self, context: dict, action: str, outcome: dict):
        """
        Record a new experience.
        """
        experience = {
            "id": f"exp_{int(time.time())}",
            "timestamp": time.time(),
            "context_summary": self._summarize_context(context),
            "action": action,
            "outcome": outcome, # e.g. {"success": True/False, "score": 0.9}
        }
        self.experiences.append(experience)
        self._save_memory()
        logger.info(f"Learned new experience: {action} -> Success: {outcome.get('success')}")

    def find_similar_situations(self, current_context: dict) -> List[Dict]:
        """
        Find past experiences that match the current context.
        (Simple keyword matching for now, replacing vector similarity)
        """
        matches = []
        current_summary = self._summarize_context(current_context)
        
        for exp in self.experiences:
            score = self._calculate_similarity(current_summary, exp['context_summary'])
            if score > 0.5: # Threshold
                matches.append(exp)
        
        # Sort by recency and success
        return sorted(matches, key=lambda x: x['timestamp'], reverse=True)[:5]

    def _summarize_context(self, context: dict) -> str:
        # Create a rich text description for embedding
        text = f"System State: CPU {context.get('cpu_usage')}%"
        for alert in context.get('alerts', []):
            text += f", Alert: {alert.get('type')} - {alert.get('details')}"
        return text

    def _get_embedding(self, text: str) -> List[float]:
        """Get vector embedding from Ollama"""
        try:
            import requests
            # Use mxbai-embed-large or similar if available, else standard llama3
            # Attempt to use a known embedding model first
            url = f"http://localhost:11434/api/embeddings"
            payload = {
                "model": "mxbai-embed-large", # Optimized for embeddings
                "prompt": text
            }
            resp = requests.post(url, json=payload, timeout=2)
            if resp.status_code != 200:
                # Fallback to whatever model is loaded/default logic if specific model missing
                return []
            return resp.json().get("embedding", [])
        except:
            return []

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        if not vec1 or not vec2: return 0.0
        
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        magnitude1 = sum(a * a for a in vec1) ** 0.5
        magnitude2 = sum(b * b for b in vec2) ** 0.5
        
        if magnitude1 == 0 or magnitude2 == 0: return 0.0
        return dot_product / (magnitude1 * magnitude2)

    def find_similar_situations(self, current_context: dict) -> List[Dict]:
        """
        Find past experiences using Vector Search (Ollama) or Fallback to Jaccard.
        """
        matches = []
        current_summary = self._summarize_context(current_context)
        current_vec = self._get_embedding(current_summary)
        
        use_vector = len(current_vec) > 0
        
        for exp in self.experiences:
            score = 0.0
            if use_vector and "embedding" in exp:
                 score = self._cosine_similarity(current_vec, exp["embedding"])
            else:
                 # Fallback Jaccard
                 score = self._jaccard_similarity(current_summary, exp.get('context_summary', ''))
            
            if score > 0.6: # Higher threshold for vector
                matches.append(exp)
        
        return sorted(matches, key=lambda x: x['timestamp'], reverse=True)[:5]

    def store_experience(self, context: dict, action: str, outcome: dict):
        summary = self._summarize_context(context)
        embedding = self._get_embedding(summary)
        
        experience = {
            "id": f"exp_{int(time.time())}",
            "timestamp": time.time(),
            "context_summary": summary,
            "embedding": embedding,
            "action": action,
            "outcome": outcome,
        }
        self.experiences.append(experience)
        self._save_memory()
        logger.info(f"Learned new experience: {action}")

    def _jaccard_similarity(self, ctx1: str, ctx2: str) -> float:
        set1 = set(ctx1.split(" "))
        set2 = set(ctx2.split(" "))
        if not set1 or not set2: return 0.0
        return len(set1.intersection(set2)) / len(set1.union(set2))
