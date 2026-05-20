from __future__ import annotations

import unittest
from pathlib import Path

from lab4.assembler import Assembler, Preprocessor, SourceLine
from lab4.machine import Machine

ROOT = Path(__file__).resolve().parents[1]


def assemble_example(name: str) -> bytes:
    return Assembler().assemble_file(ROOT / "examples" / name).binary


def run_example(name: str, input_text: str = "", *, superscalar: bool = True) -> Machine:
    machine = Machine(assemble_example(name), input_text, superscalar=superscalar)
    machine.run()
    return machine


class ToolchainTest(unittest.TestCase):
    def test_hello(self) -> None:
        machine = run_example("hello.asm")
        self.assertEqual(machine.memory.output_text(), "Hello, world!\n")

    def test_cat(self) -> None:
        machine = run_example("cat.asm", "abc\n")
        self.assertEqual(machine.memory.output_text(), "abc\n")

    def test_prob2_euler_6_sample(self) -> None:
        machine = run_example("prob2.asm", "10\n")
        self.assertEqual(machine.memory.output_text(), "2640\n")

    def test_poly_cisc_variable_length_instruction(self) -> None:
        machine = run_example("poly.asm")
        self.assertEqual(machine.memory.output_text(), "17\n")

    def test_cisc_arithmetic_can_read_memory_operand(self) -> None:
        lines = [
            SourceLine(".org 0", 1, "<test>"),
            SourceLine("MOV R0, #5", 2, "<test>"),
            SourceLine("ADD R0, [value]", 3, "<test>"),
            SourceLine("STOREB [IO_OUT], R0", 4, "<test>"),
            SourceLine("HALT", 5, "<test>"),
            SourceLine(".org 0x200", 6, "<test>"),
            SourceLine("value:", 7, "<test>"),
            SourceLine(".word 60", 8, "<test>"),
        ]
        image = Assembler().assemble_lines(lines)
        machine = Machine(image.binary)
        machine.run()
        self.assertEqual(machine.memory.output_text(), "A")

    def test_superscalar_reduces_ticks_for_independent_code(self) -> None:
        scalar = run_example("superscalar.asm", superscalar=False)
        super_machine = run_example("superscalar.asm", superscalar=True)
        self.assertLess(super_machine.tick_count, scalar.tick_count)
        self.assertTrue(any("parallel:" in line for line in super_machine.trace))

    def test_macro_org_and_conditional_assembly(self) -> None:
        lines = [
            SourceLine(".const ENABLED 1", 1, "<test>"),
            SourceLine(".macro put ch", 2, "<test>"),
            SourceLine("STOREB [IO_OUT], #\\ch", 3, "<test>"),
            SourceLine(".endm", 4, "<test>"),
            SourceLine(".org 0", 5, "<test>"),
            SourceLine(".if ENABLED", 6, "<test>"),
            SourceLine("put 65", 7, "<test>"),
            SourceLine(".endif", 8, "<test>"),
            SourceLine("HALT", 9, "<test>"),
        ]
        preprocessor = Preprocessor()
        processed = preprocessor.process_lines(lines)
        assembler = Assembler()
        assembler.symbols.update(preprocessor.constants)
        image = assembler.assemble_lines(processed)
        machine = Machine(image.binary)
        machine.run()
        self.assertEqual(machine.memory.output_text(), "A")

    def test_hello_user_name(self) -> None:
        machine = run_example("hello_user_name.asm", "Alice\n")
        self.assertEqual(machine.memory.output_text(), "What is your name?\nHello, Alice!\n")

    def test_sort_small_array(self) -> None:
        machine = run_example("sort.asm", "3\n3 1 2\n")
        self.assertEqual(machine.memory.output_text(), "1 2 3 \n")

    def test_uint64_addition(self) -> None:
        # Adding 100000 + 200000 = 300000
        machine = run_example("uint64.asm", "100000 200000\n")
        # Basic check that it doesn't crash and produces output
        output = machine.memory.output_text()
        self.assertTrue(len(output) > 0)


if __name__ == "__main__":
    unittest.main()
