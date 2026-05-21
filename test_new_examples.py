#!/usr/bin/env python3
"""Quick manual checks for the added example programs."""

from pathlib import Path

from lab4.assembler import Assembler
from lab4.machine import Machine

ROOT = Path(__file__).resolve().parent


def assemble_example(name: str) -> bytes:
    return Assembler().assemble_file(ROOT / "examples" / name).binary


def run_example(name: str, input_text: str = "", *, superscalar: bool = True) -> Machine:
    machine = Machine(assemble_example(name), input_text, superscalar=superscalar)
    machine.run()
    return machine


def check_exact(name: str, input_text: str, expected: str) -> bool:
    machine = run_example(name, input_text)
    output = machine.memory.output_text()
    test_name = Path(name).stem
    if output == expected:
        print(f"PASS {test_name}")
        return True
    print(f"FAIL {test_name}")
    print(f"  Expected: {expected!r}")
    print(f"  Got:      {output!r}")
    return False


def main() -> int:
    ok = True
    ok &= check_exact("hello_user_name.asm", "Alice\n", "What is your name?\nHello, Alice!\n")
    ok &= check_exact("sort.asm", "3\n3 1 2\n", "1 2 3 \n")
    ok &= check_exact("uint64.asm", "100000 200000\n", "300000\n")
    ok &= check_exact("uint64.asm", "4294967295 1\n", "1:0\n")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
