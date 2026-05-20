#!/usr/bin/env python3
"""Assemble new examples to verify syntax."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

from lab4.assembler import Assembler

ROOT = Path(__file__).parent

examples = ["hello_user_name.asm", "sort.asm", "uint64.asm"]

for example in examples:
    try:
        path = ROOT / "examples" / example
        result = Assembler().assemble_file(path)
        print(f"✓ {example}: {len(result.binary)} bytes")
    except Exception as e:
        print(f"✗ {example}: {e}")
        import traceback
        traceback.print_exc()
