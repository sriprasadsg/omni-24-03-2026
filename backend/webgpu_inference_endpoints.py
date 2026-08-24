"""WebGPU Inference REST API endpoints."""

from __future__ import annotations

import base64
import time
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

from authentication_service import get_current_user
from webgpu_inference.webgpu_model_loader import webgpu_model_loader, ModelSpec, CompilationResult
from webgpu_inference.webgpu_runtime import webgpu_runtime, InferenceRequest
from webgpu_inference.performance_monitor import performance_monitor, InferenceMetrics, GPUMetrics

router = APIRouter(prefix="/api/webgpu", tags=["WebGPU Inference"])


# Request/Response Models
class CompileModelRequest(BaseModel):
    onnx_path: str = Field(..., description="Path to ONNX model file")
    name: str = Field(None, description="Optional model name")


class InferenceInput(BaseModel):
    name: str
    data: List[float]  # flat list of float32
    shape: List[int]


class InferenceRequestModel(BaseModel):
    model_id: str
    inputs: List[InferenceInput]
    output_names: List[str]


class GPUMetricsRecord(BaseModel):
    memory_used_mb: float
    memory_total_mb: float
    compute_utilization: float
    temperature_c: float
    power_w: float


# Model Loader Endpoints
@router.post("/models/compile")
async def compile_model(
    request: CompileModelRequest,
    current_user=Depends(get_current_user),
):
    """Compile an ONNX model for WebGPU execution."""
    result = webgpu_model_loader.compile_model(request.onnx_path, request.name)
    if not result.success:
        raise HTTPException(status_code=400, detail=f"Compilation failed: {result.errors}")
    return {"model_id": result.model_spec.model_id, "name": result.model_spec.name}


@router.get("/models")
async def list_webgpu_models(
    current_user=Depends(get_current_user),
):
    """List loaded WebGPU models."""
    return webgpu_model_loader.list_models()


@router.get("/models/{model_id}")
async def get_webgpu_model(
    model_id: str,
    current_user=Depends(get_current_user),
):
    """Get details of a loaded WebGPU model."""
    model = webgpu_model_loader.get_model(model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    # Exclude WGSL source from direct API for brevity
    model_dict = model.__dict__.copy()
    model_dict["wgsl_shaders"] = {"count": len(model.wgsl_shaders), "keys": list(model.wgsl_shaders.keys())}
    return model_dict


@router.delete("/models/{model_id}")
async def unload_webgpu_model(
    model_id: str,
    current_user=Depends(get_current_user),
):
    """Unload a WebGPU model from memory."""
    success = webgpu_model_loader.unload_model(model_id)
    if not success:
        raise HTTPException(status_code=404, detail="Model not found")
    return {"status": "unloaded"}


# Inference Endpoints
@router.post("/inference")
async def run_inference(
    request: InferenceRequestModel,
    current_user=Depends(get_current_user),
):
    """Run WebGPU accelerated inference."""
    model_spec = webgpu_model_loader.get_model(request.model_id)
    if not model_spec:
        raise HTTPException(status_code=404, detail="Model not loaded")

    inputs_dict = {inp.name: inp.data for inp in request.inputs}

    # In a real implementation, you'd transfer data to GPU buffers,
    # bind them, dispatch compute shaders, and read back results.
    # Here, we simulate using the runtime's execute_inference.

    try:
        start_time = time.perf_counter()
        # Simulate buffer creation and writing for demo purposes
        input_buffers = []
        for inp_data in request.inputs:
            buf_id = webgpu_runtime.create_buffer(len(inp_data.data) * 4, 1, bytes(inp_data.data))
            webgpu_runtime.write_buffer(buf_id, bytes(inp_data.data))
            input_buffers.append(buf_id)

        outputs = await webgpu_runtime.execute_inference(
            request.model_id,
            inputs_dict,
            request.output_names,
        )
        end_time = time.perf_counter()

        # Record performance
        input_size = sum(len(inp.data) for inp in request.inputs) * 4
        output_size = sum(len(outputs.get(o, [])) for o in request.output_names) * 4
        performance_monitor.record_inference(InferenceMetrics(
            model_id=request.model_id,
            latency_ms=(end_time - start_time) * 1000,
            input_size_bytes=input_size,
            output_size_bytes=output_size,
        ))

        return {"model_id": request.model_id, "outputs": outputs}
    except Exception as e:
        performance_monitor.record_inference(InferenceMetrics(
            model_id=request.model_id,
            latency_ms=0.0, input_size_bytes=0, output_size_bytes=0,
            success=False, error=str(e)
        ))
        raise HTTPException(status_code=500, detail=f"Inference failed: {e}")


# Performance Monitoring Endpoints
@router.post("/metrics/gpu")
async def record_gpu_metrics(
    metrics: GPUMetricsRecord,
    current_user=Depends(get_current_user),
):
    """Record GPU device metrics."""
    performance_monitor.record_gpu_metrics(GPUMetrics(**metrics.dict()))
    return {"status": "recorded"}


@router.get("/metrics/inference")
async def get_inference_metrics(
    model_id: str = "",
    current_user=Depends(get_current_user),
):
    """Get aggregated inference metrics."""
    return performance_monitor.get_model_stats(model_id)


@router.get("/metrics/inference/history")
async def get_inference_history(
    model_id: str = "",
    limit: int = 100,
    current_user=Depends(get_current_user),
):
    """Get recent raw inference call records."""
    return performance_monitor.get_recent_inferences(model_id, limit)


@router.get("/metrics/gpu")
async def get_gpu_metrics(
    limit: int = 60,
    current_user=Depends(get_current_user),
):
    """Get recent GPU usage metrics."""
    return performance_monitor.get_gpu_usage(limit)


@router.get("/metrics/summary")
async def get_performance_summary(
    current_user=Depends(get_current_user),
):
    """Get overall WebGPU performance summary."""
    return performance_monitor.get_summary()