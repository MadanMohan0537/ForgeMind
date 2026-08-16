# VSS / Cosmos Setup (P4)

## 1. NGC access

1. Get an API key from https://ngc.nvidia.com (Setup → API Key → Generate Personal Key).
2. On the GN100/Spark:
   ```bash
   export NGC_API_KEY="<your key>"
   ngc config set
   ```

## 2. Preferred path: VSS blueprint

Pull and run the VSS blueprint per NVIDIA's DGX Spark VSS playbook
(build.nvidia.com — search "Video Search and Summarization"). This is a
long, mostly-unattended pull — start it as early as possible.

Once it's serving, point perception at it:
```bash
export VLM_URL="http://127.0.0.1:<vss-port>/v1"
export VLM_MODEL="<vss-model-name>"
```

**Checkpoint at 1:00 AM:** ask VSS a question about a sample clip. If it
answers, keep going. If not, stop fighting it and fall back immediately.

## 3. Fallback: Cosmos

The DGX Spark uses the locally downloaded Cosmos Reason2 8B checkpoint with the existing vLLM container. No additional NGC pull is required.

```bash
bash scripts/serve_cosmos.sh
```

Then:
```bash
export VLM_URL="http://127.0.0.1:8001/v1"
export VLM_MODEL="cosmos"
```

Either path — VSS or Cosmos — gets `services/perception/verify.py`'s
`vss_ask_video()` a working backend; the client code is identical either way.

## 4. Verify the wiring

```bash
python -c "
from services.perception.verify import vss_ask_video
print(vss_ask_video('runs/golden.mp4', 'Is there a hand in the robot zone?'))
"
```

## 5. Hourly health check

```bash
bash scripts/check_env.sh
```
