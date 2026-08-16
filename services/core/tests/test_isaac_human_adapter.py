import threading
import time

from services.robot.adapters import IsaacHumanArm


def test_isaac_human_arm_waits_for_external_operator():
    instructions = []
    arm = IsaacHumanArm(lambda _step: None, instructions.append)
    worker = threading.Thread(target=arm.run_add_part, args=("black_wheel", "wheel_bin", "inspection_zone"))
    worker.start()
    deadline = time.time() + 1
    while not instructions and time.time() < deadline:
        time.sleep(0.01)
    assert worker.is_alive()
    assert "External operator" in instructions[-1]
    arm.operator_complete()
    worker.join(1)
    assert not worker.is_alive()
    assert instructions[-1] is None


def test_isaac_human_arm_can_be_cancelled():
    errors = []
    arm = IsaacHumanArm(lambda _step: None, lambda _instruction: None)
    worker = threading.Thread(target=lambda: _capture(errors, arm))
    worker.start()
    time.sleep(0.03)
    arm.operator_cancel()
    worker.join(1)
    assert errors and "cancelled by operator" in str(errors[0])


def _capture(errors, arm):
    try:
        arm.run_add_part("black_wheel", "wheel_bin", "inspection_zone")
    except Exception as ex:  # expected test path
        errors.append(ex)
