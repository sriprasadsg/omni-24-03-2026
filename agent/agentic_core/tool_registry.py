
import logging
import inspect
import json
from typing import Dict, Any, Callable

logger = logging.getLogger(__name__)

class ToolRegistry:
    """
    Central registry for all tools available to the Agentic AI.
    Allows dynamic discovery and execution of functions.
    """
    
    def __init__(self):
        self._tools: Dict[str, Callable] = {}
        self._schemas: Dict[str, dict] = {}

    def register(self, func: Callable):
        """Decorator to register a function as a tool"""
        name = func.__name__
        doc = func.__doc__ or "No description provided."
        
        # Simple schema generation from type hints
        sig = inspect.signature(func)
        parameters = {
            "type": "object",
            "properties": {},
            "required": []
        }
        
        for param_name, param in sig.parameters.items():
            if param_name == "self": continue
            param_type = "string" # default
            if param.annotation == int: param_type = "integer"
            if param.annotation == bool: param_type = "boolean"
            
            parameters["properties"][param_name] = {
                "type": param_type,
                "description": f"Parameter {param_name}"
            }
            if param.default == inspect.Parameter.empty:
                parameters["required"].append(param_name)

        schema = {
            "name": name,
            "description": doc.strip(),
            "parameters": parameters
        }

        self._tools[name] = func
        self._schemas[name] = schema
        logger.debug(f"Registered tool: {name}")
        return func

    def get_tool(self, name: str) -> Callable:
        return self._tools.get(name)

    def get_all_schemas(self) -> list:
        return list(self._schemas.values())

    def execute(self, tool_name: str, arguments: dict, retries: int = 2) -> Any:
        """Execute a registered tool with retry on transient failures.

        Raises on persistent failure so callers can detect errors rather than
        silently receiving an error string that looks like a valid result.
        """
        func = self._tools.get(tool_name)
        if not func:
            raise ValueError(f"Tool '{tool_name}' not found in registry")

        last_exc: Exception = RuntimeError("unreachable")
        for attempt in range(retries + 1):
            try:
                logger.info("Executing tool '%s' (attempt %d) args=%s", tool_name, attempt + 1, arguments)
                return func(**arguments)
            except Exception as e:
                last_exc = e
                logger.warning("Tool '%s' attempt %d failed: %s", tool_name, attempt + 1, e)

        logger.error("Tool '%s' failed after %d attempts: %s", tool_name, retries + 1, last_exc)
        raise last_exc

# Global Registry Instance
registry = ToolRegistry()
