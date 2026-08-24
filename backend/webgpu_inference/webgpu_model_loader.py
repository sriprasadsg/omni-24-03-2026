"""WebGPU Model Loader — compiles ONNX models to WebGPU shaders.

Loads ONNX models, validates ops compatibility, and generates WebGPU
compute shaders for GPU-accelerated inference.
"""

import hashlib
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


@dataclass
class ModelSpec:
    """Compiled WebGPU model specification."""
    model_id: str
    name: str
    onnx_path: str
    wgsl_shaders: Dict[str, str]  # kernel_name -> WGSL source
    input_shapes: Dict[str, List[int]]
    output_shapes: Dict[str, List[int]]
    buffer_sizes: Dict[str, int]  # tensor_name -> bytes
    created_at: float = field(default_factory=time.time)
    ops_count: int = 0


@dataclass
class CompilationResult:
    """Result of ONNX to WebGPU compilation."""
    success: bool
    model_spec: Optional[ModelSpec] = None
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class WebGPUModelLoader:
    """Compiles and loads ONNX models for WebGPU execution."""

    SUPPORTED_OPS = {
        "Conv", "Gemm", "MatMul", "Add", "Mul", "Relu", "Sigmoid",
        "Tanh", "MaxPool", "AveragePool", "GlobalAveragePool",
        "Concat", "Split", "Reshape", "Transpose", "Flatten",
        "BatchNormalization", "Dropout", "Softmax", "LayerNormalization",
    }

    def __init__(self, model_dir: str = "./models"):
        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.loaded_models: Dict[str, ModelSpec] = {}

    def load_onnx(self, model_path: str) -> Dict[str, Any]:
        """Parse ONNX model and extract graph structure."""
        try:
            import onnx
            model = onnx.load(model_path)
            onnx.checker.check_model(model)

            graph = model.graph
            nodes = []
            for node in graph.node:
                nodes.append({
                    "name": node.name,
                    "op_type": node.op_type,
                    "inputs": list(node.input),
                    "outputs": list(node.output),
                    "attributes": {attr.name: onnx.helper.get_attribute_value(attr) for attr in node.attribute},
                })

            inputs = []
            for inp in graph.input:
                shape = [dim.dim_value if dim.dim_value > 0 else -1 for dim in inp.type.tensor_type.shape.dim]
                inputs.append({"name": inp.name, "shape": shape})

            outputs = []
            for out in graph.output:
                shape = [dim.dim_value if dim.dim_value > 0 else -1 for dim in out.type.tensor_type.shape.dim]
                outputs.append({"name": out.name, "shape": shape})

            return {
                "name": graph.name,
                "nodes": nodes,
                "inputs": inputs,
                "outputs": outputs,
                "opset": model.opset_import[0].version if model.opset_import else 0,
            }
        except ImportError:
            logger.error("onnx package not installed")
            return {"error": "onnx not available"}
        except Exception as e:
            logger.error("ONNX load failed: %s", e)
            return {"error": str(e)}

    def validate_ops(self, nodes: List[Dict[str, Any]]) -> List[str]:
        """Check if all ops are supported for WebGPU."""
        unsupported = []
        for node in nodes:
            if node["op_type"] not in self.SUPPORTED_OPS:
                unsupported.append(f"{node['name']} ({node['op_type']})")
        return unsupported

    def generate_wgsl(self, graph: Dict[str, Any]) -> Dict[str, str]:
        """Generate WGSL compute shaders from ONNX graph (simplified)."""
        shaders = {}
        for node in graph["nodes"]:
            op = node["op_type"]
            if op in ("Conv", "Gemm", "MatMul"):
                shader = self._generate_matrix_shader(node)
            elif op in ("Add", "Mul", "Relu", "Sigmoid", "Tanh"):
                shader = self._generate_elementwise_shader(node)
            elif op in ("MaxPool", "AveragePool"):
                shader = self._generate_pool_shader(node)
            else:
                shader = self._generate_passthrough_shader(node)
            shaders[node["name"]] = shader
        return shaders

    def _generate_matrix_shader(self, node: Dict[str, Any]) -> str:
        """Generate WGSL for matrix multiplication / convolution."""
        name = node["name"].replace("/", "_")
        return f"""
// {node['op_type']} kernel: {name}
@group(0) @binding(0) var<storage, read> input: array<f32>;
@group(0) @binding(1) var<storage, read> weight: array<f32>;
@group(0) @binding(2) var<storage, write> output: array<f32>;

@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {{
    // Simplified matrix multiply
    let idx = gid.x;
    if (idx >= arrayLength(&output)) {{ return; }}
    output[idx] = 0.0; // Placeholder
}}
"""

    def _generate_elementwise_shader(self, node: Dict[str, Any]) -> str:
        """Generate WGSL for element-wise operations."""
        name = node["name"].replace("/", "_")
        op_map = {
            "Add": "a + b",
            "Mul": "a * b",
            "Relu": "max(a, 0.0)",
            "Sigmoid": "1.0 / (1.0 + exp(-a))",
            "Tanh": "tanh(a)",
        }
        body = op_map.get(node["op_type"], "a")
        return f"""
// {node['op_type']} kernel: {name}
@group(0) @binding(0) var<storage, read> input: array<f32>;
@group(0) @binding(1) var<storage, read> other: array<f32>;
@group(0) @binding(2) var<storage, write> output: array<f32>;

@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {{
    let idx = gid.x;
    if (idx >= arrayLength(&output)) {{ return; }}
    let a = input[idx];
    let b = other[idx];
    output[idx] = {body};
}}
"""

    def _generate_pool_shader(self, node: Dict[str, Any]) -> str:
        """Generate WGSL for pooling operations."""
        name = node["name"].replace("/", "_")
        return f"""
// {node['op_type']} kernel: {name}
@group(0) @binding(0) var<storage, read> input: array<f32>;
@group(0) @binding(1) var<storage, write> output: array<f32>;

@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {{
    let idx = gid.x;
    if (idx >= arrayLength(&output)) {{ return; }}
    output[idx] = input[idx]; // Placeholder
}}
"""

    def _generate_passthrough_shader(self, node: Dict[str, Any]) -> str:
        """Generate WGSL for reshape/transpose/split/concat."""
        name = node["name"].replace("/", "_")
        return f"""
// {node['op_type']} kernel: {name}
@group(0) @binding(0) var<storage, read> input: array<f32>;
@group(0) @binding(1) var<storage, write> output: array<f32>;

@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {{
    let idx = gid.x;
    if (idx >= arrayLength(&output)) {{ return; }}
    output[idx] = input[idx]; // Placeholder
}}
"""

    def compile_model(self, onnx_path: str, name: str = "") -> CompilationResult:
        """Compile ONNX model to WebGPU shaders."""
        if not os.path.exists(onnx_path):
            return CompilationResult(success=False, errors=[f"File not found: {onnx_path}"])

        graph = self.load_onnx(onnx_path)
        if "error" in graph:
            return CompilationResult(success=False, errors=[graph["error"]])

        unsupported = self.validate_ops(graph["nodes"])
        if unsupported:
            return CompilationResult(
                success=False,
                errors=[f"Unsupported ops: {', '.join(unsupported)}"],
            )

        shaders = self.generate_wgsl(graph)
        model_id = f"wgpu_{hashlib.md5(f'{name}{time.time()}'.encode()).hexdigest()[:10]}"

        spec = ModelSpec(
            model_id=model_id,
            name=name or Path(onnx_path).stem,
            onnx_path=onnx_path,
            wgsl_shaders=shaders,
            input_shapes={inp["name"]: inp["shape"] for inp in graph["inputs"]},
            output_shapes={out["name"]: out["shape"] for out in graph["outputs"]},
            buffer_sizes={},  # computed at runtime
            ops_count=len(graph["nodes"]),
        )

        self.loaded_models[model_id] = spec
        logger.info("Model compiled: %s (%d shaders)", model_id, len(shaders))

        return CompilationResult(success=True, model_spec=spec)

    def get_model(self, model_id: str) -> Optional[ModelSpec]:
        """Get compiled model by ID."""
        return self.loaded_models.get(model_id)

    def list_models(self) -> List[Dict[str, Any]]:
        """List all loaded models."""
        return [
            {
                "model_id": m.model_id,
                "name": m.name,
                "onnx_path": m.onnx_path,
                "shader_count": len(m.wgsl_shaders),
                "ops_count": m.ops_count,
                "created_at": m.created_at,
            }
            for m in self.loaded_models.values()
        ]

    def unload_model(self, model_id: str) -> bool:
        """Remove model from memory."""
        if model_id in self.loaded_models:
            del self.loaded_models[model_id]
            return True
        return False


# Singleton loader
webgpu_model_loader = WebGPUModelLoader()