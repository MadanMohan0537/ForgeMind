# Spark story + performance numbers (Part 4 fills this in; every blank becomes a sentence in the video/README)

| Measure | Value | How measured |
|---|---|---|
| Nemotron 3 Super tokens/s (single stream) | ___ | `[llm]` lines in logs/core.log (completion tokens / seconds) |
| Super time to hypotheses (thinking on) | ___ s | same |
| Action-loop decision latency (propose_action) | ___ ms | same, `ActionProposal` lines |
| VLM verify latency (Cosmos / VSS) | ___ s | perception log / VLM_VERIFICATION events |
| Perception fps @ 960px | ___ | /state |
| Kit-arrival → decision (hold/release) | ___ s | KIT_ARRIVED.ts → KIT_HELD/RELEASED.ts |
| Memory in use (`free -h`, nvidia-smi) with everything up | ___ / 128 GB | check_env.sh |
| Wi-Fi off test | what kept working: ___ | do it once before recording |

Talking points: unified memory holds the 120B reasoner (NVFP4), the VLM, the video ring buffer, and the entire run history in context at once; nothing leaves the site; the governor and verification keep working offline; VLM verification is local so the second opinion costs seconds not a cloud round trip.
