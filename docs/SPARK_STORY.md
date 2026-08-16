# Spark Story (P4)

Local-compute narrative for the GB10 Grace Blackwell Superchip demo.
Fill every blank below with a real measured number before recording —
no placeholders in the final take.

## Model

- Reasoning model: Nemotron 3.5 Lightning (local, Ollama)
- VLM verification: Cosmos Reason2 8B (local, vLLM fallback)

## Numbers to fill in

| Metric | Value |
|---|---|
| Nemotron 3.5 Lightning tokens/s | 68.69 observed (256 tokens / 3.727 s) |
| VLM verification latency (per clip) | 6.26 s on a 2 s, 640x480 MP4 |
| Perception pipeline fps | Not measurable yet: no FPS counter is implemented |
| Memory before Cosmos load | 33 GiB used |
| Memory with Nemotron and Cosmos loaded | 82 GiB used; 38 GiB available |

## Wi-Fi-off test

- [ ] Verified locally before claiming on camera
- What kept working:
- What broke (if anything):

## Checkpoint log (hourly `check_env.sh`)

| Time | Notes |
|---|---|
