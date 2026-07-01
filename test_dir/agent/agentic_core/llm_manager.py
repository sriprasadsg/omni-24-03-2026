
import logging
import requests
import json
import time

logger = logging.getLogger(__name__)

class LLMManager:
    """
    Manages the local LLM instance (Ollama).
    Ensures the service is reachable and the required model is pulled.
    """
    
    def __init__(self, base_url="http://localhost:11434", model="llama3.2:3b"):
        self.base_url = base_url
        self.model = model

    def is_ollama_running(self) -> bool:
        """Check if Ollama service is running"""
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=2)
            return resp.status_code == 200
        except:
            return False

    def ensure_model_available(self) -> bool:
        """
        Check if model exists, pull if missing.
        Returns True if model is ready.
        """
        if not self.is_ollama_running():
            logger.warning("Ollama is not running. Cannot manage LLM models.")
            return False

        if self._check_model_exists():
            logger.info(f"Model {self.model} is already available.")
            return True
            
        logger.info(f"Model {self.model} not found. Pulling... (This may take time)")
        return self._pull_model()

    def _check_model_exists(self) -> bool:
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                for m in models:
                    if m.get("name") == self.model or m.get("name") == f"{self.model}:latest":
                        return True
            return False
        except Exception as e:
            logger.error(f"Error checking models: {e}")
            return False

    def _pull_model(self) -> bool:
        try:
            url = f"{self.base_url}/api/pull"
            # Stream the pull to avoid timeouts
            with requests.post(url, json={"name": self.model}, stream=True, timeout=600) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if line:
                        try:
                            status = json.loads(line)
                            if "status" in status:
                                # Log progress occasionally?
                                pass
                        except:
                            pass
            logger.info(f"Successfully pulled model {self.model}")
            return True
        except Exception as e:
            logger.error(f"Failed to pull model {self.model}: {e}")
            return False
