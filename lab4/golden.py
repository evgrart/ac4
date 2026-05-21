from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from lab4.assembler import Assembler, ProgramImage
from lab4.machine import Machine

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class GoldenCase:
    name: str
    source: str
    input_text: str
    expected_output: str
    include_scalar_trace: bool = False


GOLDEN_CASES: tuple[GoldenCase, ...] = (
    GoldenCase("hello", "hello.asm", "", "Hello, world!\n"),
    GoldenCase("cat", "cat.asm", "abc\n", "abc\n"),
    GoldenCase("hello_user_name", "hello_user_name.asm", "Alice\n", "What is your name?\nHello, Alice!\n"),
    GoldenCase("sort", "sort.asm", "3\n3 1 2\n", "1 2 3 \n"),
    GoldenCase("uint64", "uint64.asm", "100000 200000\n", "300000\n"),
    GoldenCase("prob2", "prob2.asm", "10\n", "2640\n"),
    GoldenCase("poly", "poly.asm", "", "17\n"),
    GoldenCase("superscalar", "superscalar.asm", "", "", include_scalar_trace=True),
)


def symbols_text(image: ProgramImage) -> str:
    return "".join(f"{name} = 0x{value:X}\n" for name, value in image.symbols.items())


def write_case(case: GoldenCase, *, golden_root: Path, build_root: Path) -> None:
    source_path = ROOT / "examples" / case.source
    image = Assembler().assemble_file(source_path)
    machine = Machine(image.binary, case.input_text)
    output = machine.run()
    if output != case.expected_output:
        raise ValueError(f"{case.name}: expected {case.expected_output!r}, got {output!r}")

    case_dir = golden_root / case.name
    case_dir.mkdir(parents=True, exist_ok=True)
    build_root.mkdir(parents=True, exist_ok=True)

    (case_dir / "source.asm").write_text(source_path.read_text(encoding="utf-8"), encoding="utf-8")
    (case_dir / "input.txt").write_text(case.input_text, encoding="utf-8")
    (case_dir / "output.txt").write_text(output, encoding="utf-8")
    (case_dir / "program.bin").write_bytes(image.binary)
    (case_dir / "listing.hex").write_text(image.listing, encoding="utf-8")
    (case_dir / "symbols.txt").write_text(symbols_text(image), encoding="utf-8")
    (case_dir / "trace.log").write_text("\n".join(machine.trace) + "\n", encoding="utf-8")
    (case_dir / "metadata.txt").write_text(
        f"source = {case.source}\n"
        f"ticks = {machine.tick_count}\n"
        f"instructions = {machine.instruction_count}\n"
        f"halt_reason = {machine.halt_reason}\n",
        encoding="utf-8",
    )

    (build_root / f"{case.name}.bin").write_bytes(image.binary)
    (build_root / f"{case.name}.hex").write_text(image.listing, encoding="utf-8")
    (build_root / f"{case.name}.sym").write_text(symbols_text(image), encoding="utf-8")
    (build_root / f"{case.name}.in").write_text(case.input_text, encoding="utf-8")
    (build_root / f"{case.name}.out").write_text(output, encoding="utf-8")
    (build_root / f"{case.name}.log").write_text("\n".join(machine.trace) + "\n", encoding="utf-8")
    if case.name == "prob2":
        (build_root / "prob2.verify.log").write_text("\n".join(machine.trace) + "\n", encoding="utf-8")

    if case.include_scalar_trace:
        scalar = Machine(image.binary, case.input_text, superscalar=False)
        scalar.run()
        (case_dir / "trace.scalar.log").write_text("\n".join(scalar.trace) + "\n", encoding="utf-8")
        (build_root / f"{case.name}.scalar.log").write_text("\n".join(scalar.trace) + "\n", encoding="utf-8")


def generate_golden(*, golden_root: Path, build_root: Path) -> None:
    for case in GOLDEN_CASES:
        write_case(case, golden_root=golden_root, build_root=build_root)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate golden test artifacts for lab4 examples.")
    parser.add_argument("--golden-root", type=Path, default=ROOT / "golden")
    parser.add_argument("--build-root", type=Path, default=ROOT / "build")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    generate_golden(golden_root=args.golden_root, build_root=args.build_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
