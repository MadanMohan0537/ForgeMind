# VSS / Cosmos Setup (P4)

## Preferred path: VSS blueprint

VSS needs an NVIDIA NGC account and a personal API key. On the Spark, run:

```bash
ngc config set
```

Enter the key only at the interactive prompt. Do not paste it into shell
history, documentation, `.env` files, or Git.

Run the VSS blueprint using NVIDIA's DGX Spark VSS playbook. Once it serves an
OpenAI-compatible endpoint, configure perception:

```bash
export VLM_URL="http://127.0.0.1:<vss-port>/v1"
export VLM_MODEL="<vss-model-name>"
```

## Validated fallback: local Cosmos

The tested Spark uses the Cosmos Reason2 8B checkpoint already on disk and the
existing vLLM image. It does not need an NGC key or an additional model pull.

```bash
bash scripts/serve_cosmos.sh
export VLM_URL="http://127.0.0.1:8001/v1"
export VLM_MODEL="cosmos"
```

The container is persistent, bound to loopback only, and restarts unless
stopped. `serve_cosmos.sh` is idempotent and waits for `/v1/models` to respond.

## Verify the wiring

Use a short MP4 clip:

```bash
python -c "
from services.perception.verify import vss_ask_video
print(vss_ask_video('runs/golden.mp4', 'Is there a hand in the robot zone?'))
"
```

Perception reads the same environment variables and emits `VLM_VERIFICATION`
events for uncertain, incomplete, and reinspection results. The registered VSS
alert descriptions are `kit placed in inspection zone` and
`hand in robot zone`.

## Hourly health check

```bash
bash scripts/check_env.sh
```
