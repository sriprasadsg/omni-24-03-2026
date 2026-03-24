import os
import gc
import json
import logging
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime, timezone

# We will load torch and transformers only when needed to save memory
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline

logger = logging.getLogger("ai_auditor")
logging.basicConfig(level=logging.INFO)

class LocalAIAuditor:
    def __init__(self, model_id: str = "HuggingFaceTB/SmolLM-135M-Instruct"):
        """
        Initializes the local AI auditor.
        Using a very small model by default for speed/memory on local dev machines.
        For production quality, we would use Meta-Llama-3-8B-Instruct or Phi-3-mini-4k-instruct.
        """
        self.model_id = model_id
        self.pipeline = None
        self.tokenizer = None
        self._load_model()

    def _load_model(self):
        logger.info(f"Loading local model weights for {self.model_id}...")
        try:
            # Determine best device
            device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info(f"Using device: {device}")

            self.tokenizer = AutoTokenizer.from_pretrained(self.model_id)
            model = AutoModelForCausalLM.from_pretrained(
                self.model_id,
                torch_dtype=torch.float16 if device == "cuda" else torch.float32,
                device_map="auto" if device == "cuda" else None,
                low_cpu_mem_usage=True
            )
            
            self.pipeline = pipeline(
                "text-generation",
                model=model,
                tokenizer=self.tokenizer,
                device_map="auto" if device == "cuda" else None,
                device=-1 if device == "cpu" else None
            )
            logger.info("Model loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load model {self.model_id}: {e}")
            self.pipeline = None

    def evaluate_evidence(self, framework_name: str, control_desc: str, evidence_text: str) -> Dict[str, Any]:
        """Runs the LLM inference to act as an auditor."""
        if not self.pipeline:
            return {
                "verified": False,
                "reasoning": "AI Model failed to load locally on this server.",
                "evaluatedAt": datetime.now(timezone.utc).isoformat()
            }

        messages = [
            {"role": "system", "content": "You are a strict technical auditor. You evaluate evidence against a control requirement.\n\nRULES:\n1. Output MUST be exactly two lines.\n2. Line 1 MUST be 'VERDICT: PASS' or 'VERDICT: FAIL'.\n3. Line 2 MUST be 'REASONING: ' followed by a 1-sentence explanation.\n4. DO NOT hallucinate. Base your answer ONLY on the provided evidence.\n\nEXAMPLE INPUT:\nRequirement: Ensure disk encryption is enabled.\nEvidence: BitLocker Drive Encryption: Protection On\n\nEXAMPLE OUTPUT:\nVERDICT: PASS\nREASONING: The evidence explicitly states that BitLocker Drive Encryption Protection is On, satisfying the disk encryption requirement."},
            {"role": "user", "content": f"Requirement: {control_desc}\nEvidence: {evidence_text[:1000]}"}
        ]
        
        try:
            prompt = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            
            outputs = self.pipeline(
                prompt, 
                max_new_tokens=150, 
                temperature=0.1, 
                do_sample=False,
                return_full_text=False
            )
            
            response = outputs[0]['generated_text'].strip()
            
            # Parse output
            lines = response.split('\n')
            verdict = "FAIL"
            reasoning = response
            
            for line in lines:
                if line.startswith("VERDICT:"):
                    verdict = line.replace("VERDICT:", "").strip().upper()
                elif line.startswith("REASONING:"):
                    reasoning = line.replace("REASONING:", "").strip()

            return {
                "verified": "PASS" in verdict,
                "reasoning": reasoning,
                "raw_response": response,
                "evaluatedAt": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Inference failed: {e}")
            return {
                "verified": False,
                "reasoning": f"Local inference error: {str(e)}",
                "evaluatedAt": datetime.now(timezone.utc).isoformat()
            }

# Singleton instance
_auditor_instance = None

def get_auditor() -> LocalAIAuditor:
    global _auditor_instance
    if _auditor_instance is None:
        _auditor_instance = LocalAIAuditor()
    return _auditor_instance

# Test standalone
if __name__ == "__main__":
    auditor = get_auditor()
    res = auditor.evaluate_evidence(
        "CISSP", 
        "Deploy and maintain modern anti-malware and Endpoint Detection and Response (EDR).",
        "AMServiceEnabled: True, RealTimeProtectionEnabled: True, SignatureAge: 1 day"
    )
    print("\n--- TEST RESULT ---")
    print(json.dumps(res, indent=2))
