"""Actuator adapters. The robot service maps a validated request to ONE tested routine.

Adapters:
  MockArm  - sleeps through the routine, always succeeds (CI / no hardware).
  HumanArm - shows the instruction on the recovery-station screen and waits for the human to tap Done.
             This is the hackathon actuator. Same command, same verification, arm-shaped hole in the code.
  RealArm  - stub. Fill in with your SDK (pymycobot / xArm / pydobot ...). Teach positions into positions.json.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Callable, Optional

POSITIONS_PATH = Path(os.environ.get("ROBOT_POSITIONS", Path(__file__).parent / "positions.json"))


class ArmAdapter:
    name = "base"

    def __init__(self, on_step: Callable[[str], None]):
        self.on_step = on_step
        self._stop = threading.Event()

    # --- routine primitives (each must be fast to abort) -------------------
    def home(self) -> None: ...
    def pick(self, source_bin: str, part: str) -> None: ...
    def place(self, target_zone: str) -> None: ...
    def stop(self) -> None:
        self._stop.set()

    def reset(self) -> None:
        self._stop.clear()

    def check_stop(self) -> None:
        if self._stop.is_set():
            raise RuntimeError("stopped by operator")

    def run_add_part(self, part: str, source_bin: str, target_zone: str) -> None:
        """The one supported routine (Section 4.1)."""
        self.reset()
        self.on_step("home");   self.home();                    self.check_stop()
        self.on_step("pick");   self.pick(source_bin, part);   self.check_stop()
        self.on_step("place");  self.place(target_zone);       self.check_stop()
        self.on_step("home");   self.home()


class MockArm(ArmAdapter):
    name = "mock"
    step_seconds = float(os.environ.get("MOCK_STEP_SECONDS", "1.0"))

    def _sleep(self) -> None:
        for _ in range(int(self.step_seconds * 10)):
            self.check_stop()
            time.sleep(0.1)

    def home(self) -> None: self._sleep()
    def pick(self, source_bin: str, part: str) -> None: self._sleep()
    def place(self, target_zone: str) -> None: self._sleep()


class HumanArm(ArmAdapter):
    """Human-in-the-loop actuator. pick+place block until /robot/human-done is called (or timeout)."""
    name = "human"
    timeout_seconds = float(os.environ.get("HUMAN_TIMEOUT_SECONDS", "120"))

    def __init__(self, on_step, on_instruction: Callable[[Optional[str]], None]):
        super().__init__(on_step)
        self.on_instruction = on_instruction
        self.done = threading.Event()

    def human_done(self) -> None:
        self.done.set()

    def home(self) -> None:
        pass

    def pick(self, source_bin: str, part: str) -> None:
        self.done.clear()
        self._instr = f"Take ONE {part.replace('_', ' ')} from the {source_bin.replace('_', ' ')}"
        self.on_instruction(self._instr)

    def place(self, target_zone: str) -> None:
        self._instr += f", place it inside the kit in the {target_zone.replace('_', ' ')}, then tap DONE."
        self.on_instruction(self._instr)
        t0 = time.time()
        while not self.done.wait(0.2):
            self.check_stop()
            if time.time() - t0 > self.timeout_seconds:
                self.on_instruction(None)
                raise RuntimeError("human actuator timed out")
        self.on_instruction(None)


class RealArm(ArmAdapter):
    """TODO: wire to your SDK. Keep it teach-and-repeat: joint targets live in positions.json.

    positions.json example:
    {"home": [0,0,0,0,0,0], "wheel_bin": [..], "wheel_bin_hover": [..],
     "inspection_zone_hover": [..], "inspection_zone_drop": [..], "speed": 30}
    """
    name = "real"

    def __init__(self, on_step):
        super().__init__(on_step)
        self.pos = json.loads(POSITIONS_PATH.read_text()) if POSITIONS_PATH.exists() else {}
        # e.g. from pymycobot import MyCobot; self.mc = MyCobot(os.environ.get("ROBOT_PORT", "/dev/ttyUSB0"), 115200)
        raise NotImplementedError("RealArm: implement with your arm's SDK, then set ROBOT_ADAPTER=real")

    def _move(self, key: str) -> None:
        # self.mc.send_angles(self.pos[key], self.pos.get("speed", 30)); wait until reached; self.check_stop()
        ...

    def home(self) -> None: self._move("home")
    def pick(self, source_bin: str, part: str) -> None:
        self._move(f"{source_bin}_hover"); self._move(source_bin)  # close gripper / suction on
        self._move(f"{source_bin}_hover")
    def place(self, target_zone: str) -> None:
        self._move(f"{target_zone}_hover"); self._move(f"{target_zone}_drop")  # open gripper / suction off
        self._move(f"{target_zone}_hover")
