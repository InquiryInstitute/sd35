#!/usr/bin/env python3
"""
SageMaker inference server for Stable Diffusion 3 Medium.
Same contract as serve.py: GET /ping -> 200; POST /invocations -> JSON { "prompt", "negative_prompt" } -> JSON { "image": "<base64 PNG>" }.
SD3 Medium is faster and more memory-efficient than SD 3.5 models, suitable for ml.g4dn.xlarge (16GB VRAM).
Real-time endpoints must respond within 60s; defaults (768, 20 steps) aim to stay under that. First request loads the model and may timeout.
"""
import base64
import io
import json
import os

from flask import Flask, request, Response

app = Flask(__name__)
PIPELINE = None
MODEL_ID = os.environ.get("HF_MODEL_ID", "stabilityai/stable-diffusion-3.5-large")
DEVICE = os.environ.get("DEVICE", "cuda")
HEIGHT = int(os.environ.get("HEIGHT", "768"))
WIDTH = int(os.environ.get("WIDTH", "768"))
NUM_STEPS = int(os.environ.get("NUM_INFERENCE_STEPS", "20"))
GUIDANCE_SCALE = float(os.environ.get("GUIDANCE_SCALE", "3.5"))
HF_TOKEN = os.environ.get("HF_TOKEN", "").strip() or None


def get_pipeline():
    global PIPELINE
    if PIPELINE is None:
        print(f"Loading pipeline: {MODEL_ID}", flush=True)
        print(f"HF_TOKEN present: {bool(HF_TOKEN)}", flush=True)
        import torch
        from diffusers import StableDiffusion3Pipeline

        dtype = torch.bfloat16 if torch.cuda.is_available() else torch.float32
        kwargs = {"torch_dtype": dtype}
        if HF_TOKEN:
            kwargs["token"] = HF_TOKEN
        print(f"Calling from_pretrained with dtype={dtype}", flush=True)
        PIPELINE = StableDiffusion3Pipeline.from_pretrained(MODEL_ID, **kwargs)
        print("Pipeline loaded, setting up device...", flush=True)
        # Use CPU offload to avoid OOM on 16GB GPU (ml.g4dn.xlarge); full .to("cuda") can exhaust VRAM.
        if torch.cuda.is_available():
            PIPELINE.enable_model_cpu_offload()
            print("Enabled CPU offload", flush=True)
        else:
            PIPELINE = PIPELINE.to("cpu")
            print("Using CPU", flush=True)
        print("Pipeline ready!", flush=True)
    return PIPELINE


@app.route("/ping", methods=["GET"])
def ping():
    return Response("", status=200)


@app.route("/invocations", methods=["POST"])
def invocations():
    try:
        data = request.get_json(force=True, silent=True) or {}
        prompt = (data.get("prompt") or "").strip()
        # negative_prompt accepted for API compatibility but SD3.5 does not use it
        if not prompt:
            return Response(
                json.dumps({"error": "Missing prompt"}),
                status=400,
                mimetype="application/json",
            )
        pipe = get_pipeline()
        out = pipe(
            prompt=prompt,
            height=HEIGHT,
            width=WIDTH,
            num_inference_steps=NUM_STEPS,
            guidance_scale=GUIDANCE_SCALE,
        )
        image = out.images[0]
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        b64 = base64.standard_b64encode(buf.getvalue()).decode("ascii")
        return Response(
            json.dumps({"image": b64}),
            status=200,
            mimetype="application/json",
        )
    except Exception as e:
        import traceback
        error_msg = str(e)
        trace = traceback.format_exc()
        print(f"ERROR in /invocations: {error_msg}", flush=True)
        print(trace, flush=True)
        return Response(
            json.dumps({"error": error_msg}),
            status=500,
            mimetype="application/json",
        )


if __name__ == "__main__":
    port = int(os.environ.get("SAGEMAKER_BIND_TO_PORT", "8080"))
    app.run(host="0.0.0.0", port=port, threaded=True)
