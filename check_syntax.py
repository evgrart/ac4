#!/usr/bin/env python3
"""Assemble example programs to verify syntax."""

from pathlib import Path

from lab4.assembler import Assembler

ROOT = Path(__file__).resolve().parent
EXAMPLES = ("hello_user_name.asm", "sort.asm", "uint64.asm")


def main() -> int:
    ok = True
    for example in EXAMPLES:
        try:
            path = ROOT / "examples" / example
            result = Assembler().assemble_file(path)
            print(f"PASS {example}: {len(result.binary)} bytes")
        except Exception as error:
            ok = False
            print(f"FAIL {example}: {error}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
