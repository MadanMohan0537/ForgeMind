# Spark Story (P4)

Measured local-compute record for the GB10 Grace Blackwell Superchip demo.
Unverified items are labelled explicitly and must not be claimed on camera.

## Model

- Reasoning model: Nemotron 3.5 Lightning (local, Ollama)
- VLM verification: Cosmos Reason2 8B (local, vLLM fallback)

## Measurements

| Metric | Value |
|---|---|
| Nemotron 3.5 Lightning tokens/s | 68.69 observed (256 tokens / 3.727 s) |
| VLM verification latency (per clip) | 6.26 s on the original 2 s, 640x480 sample; 2.45 s independent synthetic smoke test |
| VLM image latency | 5.02 s on a synthetic 640x480 JPEG |
| Perception pipeline fps | Pending a camera/replay measurement; live value is exposed by `/state` |
| Memory before Cosmos load | 33 GiB used |
| Memory with Nemotron and Cosmos loaded | 82 GiB used; 38 GiB available |
| Kit-inspect-to-decision latency | Pending an end-to-end instrumented run |

## Wi-Fi-off test

- [ ] Must be verified physically on the Spark before claiming on camera
- Expected to keep working: loopback services, local models, perception, core, and robot simulator
- Not remotely tested: removing Wi-Fi would terminate the current SSH session, so this cannot be certified remotely

## Checkpoint log (hourly `check_env.sh`)

| Time | Notes |
|---|---|
