
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

    def execute(self, tool_name: str, arguments: dict) -> Any:
        func = self._tools.get(tool_name)
        if not func:
            raise ValueError(f"Tool '{tool_name}' not found")
        
        try:
            logger.info(f"Executing tool: {tool_name} with args: {arguments}")
            return func(**arguments)
        except Exception as e:
            logger.error(f"Tool execution failed: {e}")
            return f"Error: {str(e)}"

# Global Registry Instance
registry = ToolRegistry()
