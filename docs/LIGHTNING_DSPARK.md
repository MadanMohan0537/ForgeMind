# Nemotron 3.5 Lightning NVFP4 + DSpark

ForgeMind's wrapper is `scripts/serve_lightning.sh`. It pairs these two Hugging Face checkpoints:

- Target: [`nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4`](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4)
- Draft: [`nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4-DSpark`](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4-DSpark)

The DSpark checkpoint is only a speculative draft model; do not serve it alone.

## Start on DGX Spark

The wrapper uses a host `vllm` command when available; otherwise it uses Docker with NVIDIA's documented `vllm/vllm-openai:v0.27.1` image:

```bash
cd ~/ForgeMind
bash scripts/serve_lightning.sh
```

The first start downloads the container and both Hugging Face repositories unless they are already cached. To inspect the exact command without loading or downloading model weights:

```bash
bash scripts/serve_lightning.sh --print-command
```

Smoke test:

```bash
curl -fsS http://127.0.0.1:8002/v1/models
curl -fsS http://127.0.0.1:8002/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"lightning","messages":[{"role":"user","content":"Return only: READY"}],"temperature":0,"max_tokens":16,"chat_template_kwargs":{"enable_thinking":false}}'
```

Run ForgeMind against it:

```bash
LLM_BASE_URL=http://127.0.0.1:8002/v1 \
LLM_MODEL=lightning \
LLM_FAST_MODEL=lightning \
LLM_THINK_MODE=kwarg \
bash scripts/start_all.sh
```

Defaults are intentionally limited to 8,192 tokens, two sequences, and `LIGHTNING_GPU_UTIL=0.40` so the unified-memory system keeps headroom for Cosmos and ForgeMind. Avoid keeping the Ollama copy of Lightning loaded at the same time. Override only after checking `free -h` and `nvidia-smi`, for example `LIGHTNING_GPU_UTIL=0.45 LIGHTNING_MAX_NUM_SEQS=4 bash scripts/serve_lightning.sh`.
