from __future__ import annotations

import argparse
import ast
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from lab4.isa import (
    OPCODE_BY_NAME,
    REGISTER_NAMES,
    WORD_BYTES,
    Instruction,
    Operand,
    OperandKind,
    default_symbols,
    format_instruction,
    instruction_words,
    pack_words,
)


class AssemblerError(ValueError):
    pass


@dataclass(frozen=True)
class SourceLine:
    text: str
    line_no: int
    file: str


@dataclass(frozen=True)
class Statement:
    address: int
    kind: str
    text: str
    line: SourceLine


@dataclass(frozen=True)
class ProgramImage:
    binary: bytes
    listing: str
    symbols: dict[str, int]


_LABEL_RE = re.compile(r"^([A-Za-z_.][\w.]*)\s*:\s*(.*)$")
_CONST_RE = re.compile(r"^(?:\.const|\.equ|%define)\s+([A-Za-z_][\w.]*)\s+(.+)$", re.IGNORECASE)


def strip_comment(line: str) -> str:
    quoted = False
    escaped = False
    result: list[str] = []
    for char in line:
        if escaped:
            result.append(char)
            escaped = False
            continue
        if char == "\\" and quoted:
            result.append(char)
            escaped = True
            continue
        if char == '"':
            quoted = not quoted
            result.append(char)
            continue
        if char == ";" and not quoted:
            break
        result.append(char)
    return "".join(result).strip()


def split_operands(text: str) -> list[str]:
    operands: list[str] = []
    current: list[str] = []
    quoted = False
    escaped = False
    bracket_depth = 0
    for char in text:
        if escaped:
            current.append(char)
            escaped = False
            continue
        if char == "\\" and quoted:
            current.append(char)
            escaped = True
            continue
        if char == '"':
            quoted = not quoted
            current.append(char)
            continue
        if not quoted:
            if char == "[":
                bracket_depth += 1
            elif char == "]":
                bracket_depth -= 1
            elif char == "," and bracket_depth == 0:
                operand = "".join(current).strip()
                if operand:
                    operands.append(operand)
                current.clear()
                continue
        current.append(char)
    tail = "".join(current).strip()
    if tail:
        operands.append(tail)
    return operands


def unescape_string(text: str) -> bytes:
    try:
        value = ast.literal_eval(text)
    except (SyntaxError, ValueError) as error:
        raise AssemblerError(f"invalid string literal {text!r}") from error
    if not isinstance(value, str):
        raise AssemblerError(f"expected string literal, got {text!r}")
    return value.encode("utf-8")


def eval_expr(expr: str, symbols: dict[str, int]) -> int:
    expr = expr.strip()
    if not expr:
        raise AssemblerError("empty expression")
    try:
        node = ast.parse(expr, mode="eval")
    except SyntaxError as error:
        raise AssemblerError(f"invalid expression {expr!r}") from error

    def visit(current: ast.AST) -> int:
        if isinstance(current, ast.Expression):
            return visit(current.body)
        if isinstance(current, ast.Constant) and isinstance(current.value, int):
            return int(current.value)
        if isinstance(current, ast.Name):
            if current.id not in symbols:
                raise AssemblerError(f"unknown symbol {current.id!r} in {expr!r}")
            return symbols[current.id]
        if isinstance(current, ast.UnaryOp):
            value = visit(current.operand)
            if isinstance(current.op, ast.USub):
                return -value
            if isinstance(current.op, ast.UAdd):
                return value
            if isinstance(current.op, ast.Invert):
                return ~value
        if isinstance(current, ast.BinOp):
            left = visit(current.left)
            right = visit(current.right)
            if isinstance(current.op, ast.Add):
                return left + right
            if isinstance(current.op, ast.Sub):
                return left - right
            if isinstance(current.op, ast.Mult):
                return left * right
            if isinstance(current.op, ast.FloorDiv):
                return left // right
            if isinstance(current.op, ast.Mod):
                return left % right
            if isinstance(current.op, ast.LShift):
                return left << right
            if isinstance(current.op, ast.RShift):
                return left >> right
            if isinstance(current.op, ast.BitOr):
                return left | right
            if isinstance(current.op, ast.BitAnd):
                return left & right
            if isinstance(current.op, ast.BitXor):
                return left ^ right
        if isinstance(current, ast.Compare) and len(current.ops) == 1 and len(current.comparators) == 1:
            left = visit(current.left)
            right = visit(current.comparators[0])
            op = current.ops[0]
            if isinstance(op, ast.Eq):
                return int(left == right)
            if isinstance(op, ast.NotEq):
                return int(left != right)
            if isinstance(op, ast.Lt):
                return int(left < right)
            if isinstance(op, ast.LtE):
                return int(left <= right)
            if isinstance(op, ast.Gt):
                return int(left > right)
            if isinstance(op, ast.GtE):
                return int(left >= right)
        raise AssemblerError(f"unsupported expression {expr!r}")

    return visit(node)


class Preprocessor:
    def __init__(self) -> None:
        self.constants = default_symbols()
        self.macros: dict[str, tuple[list[str], list[str]]] = {}

    def process(self, path: Path) -> list[SourceLine]:
        raw_lines = [
            SourceLine(strip_comment(text), index, str(path))
            for index, text in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        ]
        return self.process_lines(raw_lines)

    def process_lines(self, lines: list[SourceLine]) -> list[SourceLine]:
        output: list[SourceLine] = []
        active_stack = [True]
        macro_name: str | None = None
        macro_params: list[str] = []
        macro_body: list[str] = []

        for line in lines:
            text = line.text
            if not text:
                continue
            lowered = text.lower()

            if macro_name is not None:
                if lowered == ".endm":
                    self.macros[macro_name] = (macro_params, macro_body)
                    macro_name = None
                    macro_params = []
                    macro_body = []
                else:
                    macro_body.append(text)
                continue

            if lowered.startswith(".ifdef "):
                name = text.split(maxsplit=1)[1].strip()
                active_stack.append(active_stack[-1] and name in self.constants)
                continue
            if lowered.startswith(".ifndef "):
                name = text.split(maxsplit=1)[1].strip()
                active_stack.append(active_stack[-1] and name not in self.constants)
                continue
            if lowered.startswith(".if "):
                expr = text.split(maxsplit=1)[1]
                active_stack.append(active_stack[-1] and bool(eval_expr(expr, self.constants)))
                continue
            if lowered == ".else":
                if len(active_stack) == 1:
                    raise AssemblerError(f"{line.file}:{line.line_no}: .else without .if")
                parent_active = active_stack[-2]
                active_stack[-1] = parent_active and not active_stack[-1]
                continue
            if lowered == ".endif":
                if len(active_stack) == 1:
                    raise AssemblerError(f"{line.file}:{line.line_no}: .endif without .if")
                active_stack.pop()
                continue

            if not active_stack[-1]:
                continue

            const_match = _CONST_RE.match(text)
            if const_match:
                self.constants[const_match.group(1)] = eval_expr(const_match.group(2), self.constants)
                continue

            if lowered.startswith(".macro "):
                parts = text.split()
                if len(parts) < 2:
                    raise AssemblerError(f"{line.file}:{line.line_no}: macro name is required")
                macro_name = parts[1]
                macro_params = parts[2:]
                macro_body = []
                continue

            name = text.split(maxsplit=1)[0]
            if name in self.macros:
                params, body = self.macros[name]
                actuals = split_operands(text[len(name) :].strip())
                if len(actuals) != len(params):
                    raise AssemblerError(
                        f"{line.file}:{line.line_no}: macro {name} expects {len(params)} args, got {len(actuals)}"
                    )
                bindings = dict(zip(params, actuals, strict=True))
                for template in body:
                    expanded = template
                    for param, actual in bindings.items():
                        expanded = expanded.replace(f"\\{param}", actual)
                        expanded = expanded.replace(f"{{{param}}}", actual)
                    output.append(SourceLine(expanded, line.line_no, line.file))
                continue

            output.append(line)

        if len(active_stack) != 1:
            raise AssemblerError("unclosed conditional block")
        if macro_name is not None:
            raise AssemblerError(f"unclosed macro {macro_name}")
        return output


class Assembler:
    def __init__(self) -> None:
        self.symbols = default_symbols()
        self.statements: list[Statement] = []

    def assemble_file(self, path: Path) -> ProgramImage:
        preprocessor = Preprocessor()
        lines = preprocessor.process(path)
        self.symbols.update(preprocessor.constants)
        return self.assemble_lines(lines)

    def assemble_lines(self, lines: list[SourceLine]) -> ProgramImage:
        self._first_pass(lines)
        return self._second_pass()

    def _first_pass(self, lines: list[SourceLine]) -> None:
        pc = 0
        for line in lines:
            text = line.text
            while True:
                match = _LABEL_RE.match(text)
                if match is None:
                    break
                self.symbols[match.group(1)] = pc
                text = match.group(2).strip()
                if not text:
                    break
            if not text:
                continue
            lowered = text.lower()
            if lowered.startswith((".section ", ".text", ".data")):
                continue
            if lowered.startswith(".org "):
                pc = eval_expr(text.split(maxsplit=1)[1], self.symbols)
                continue
            statement = Statement(pc, "directive" if text.startswith(".") else "instruction", text, line)
            self.statements.append(statement)
            pc += self._statement_size(text)

    def _statement_size(self, text: str) -> int:
        lowered = text.lower()
        if lowered.startswith(".word "):
            return WORD_BYTES * len(split_operands(text.split(maxsplit=1)[1]))
        if lowered.startswith(".byte "):
            return len(self._parse_byte_values(text.split(maxsplit=1)[1]))
        if lowered.startswith(".zero "):
            return eval_expr(text.split(maxsplit=1)[1], self.symbols)
        if lowered.startswith(".cstr "):
            return len(unescape_string(text.split(maxsplit=1)[1])) + 1
        if lowered.startswith(".align "):
            align = eval_expr(text.split(maxsplit=1)[1], self.symbols)
            if align <= 0:
                raise AssemblerError(".align expects positive value")
            current = self.statements[-1].address if self.statements else 0
            return (align - (current % align)) % align
        if text.startswith("."):
            raise AssemblerError(f"unknown directive {text!r}")
        _, operands = self._parse_instruction_head(text)
        return WORD_BYTES * (1 + len(operands))

    def _second_pass(self) -> ProgramImage:
        memory: dict[int, int] = {}
        listing_lines: list[str] = []
        max_address = 0
        for statement in self.statements:
            encoded = self._encode_statement(statement)
            for offset, value in enumerate(encoded):
                memory[statement.address + offset] = value
            if encoded:
                max_address = max(max_address, statement.address + len(encoded))
            listing_lines.append(self._listing_line(statement, encoded))
        binary = bytes(memory.get(address, 0) for address in range(max_address))
        return ProgramImage(binary, "\n".join(listing_lines) + "\n", dict(sorted(self.symbols.items())))

    def _encode_statement(self, statement: Statement) -> bytes:
        text = statement.text
        lowered = text.lower()
        if lowered.startswith(".word "):
            values = [eval_expr(item, self.symbols) for item in split_operands(text.split(maxsplit=1)[1])]
            return pack_words(values)
        if lowered.startswith(".byte "):
            return bytes(value & 0xFF for value in self._parse_byte_values(text.split(maxsplit=1)[1]))
        if lowered.startswith(".zero "):
            return bytes(eval_expr(text.split(maxsplit=1)[1], self.symbols))
        if lowered.startswith(".cstr "):
            return unescape_string(text.split(maxsplit=1)[1]) + b"\x00"
        if lowered.startswith(".align "):
            return b"\x00" * self._statement_size(text)
        if text.startswith("."):
            raise AssemblerError(f"unknown directive {text!r}")
        instruction = self._parse_instruction(text, statement.address)
        return pack_words(instruction_words(instruction))

    def _listing_line(self, statement: Statement, encoded: bytes) -> str:
        hex_bytes = encoded.hex(" ").upper()
        return f"{statement.address:08X} - {hex_bytes:<48} - {statement.text}"

    def _parse_byte_values(self, text: str) -> list[int]:
        values: list[int] = []
        for item in split_operands(text):
            item = item.strip()
            if item.startswith('"'):
                values.extend(unescape_string(item))
            else:
                values.append(eval_expr(item, self.symbols))
        return values

    def _parse_instruction_head(self, text: str) -> tuple[str, list[str]]:
        parts = text.split(maxsplit=1)
        mnemonic = parts[0].upper()
        operands = split_operands(parts[1]) if len(parts) == 2 else []
        if mnemonic not in OPCODE_BY_NAME:
            raise AssemblerError(f"unknown instruction {mnemonic!r}")
        return mnemonic, operands

    def _parse_instruction(self, text: str, address: int) -> Instruction:
        mnemonic, raw_operands = self._parse_instruction_head(text)
        opcode = OPCODE_BY_NAME[mnemonic]
        operands = tuple(self._parse_operand(operand) for operand in raw_operands)
        instruction = Instruction(opcode, operands, address, text)
        rendered = format_instruction(instruction)
        if not rendered.startswith(mnemonic):
            raise AssemblerError(f"internal formatting error for {text!r}")
        return instruction

    def _parse_operand(self, text: str) -> Operand:
        text = text.strip()
        upper = text.upper()
        if upper in REGISTER_NAMES:
            return Operand(OperandKind.REG, REGISTER_NAMES[upper])
        if text.startswith("#"):
            return Operand(OperandKind.IMM, eval_expr(text[1:], self.symbols))
        if text.startswith("[") and text.endswith("]"):
            inner = text[1:-1].strip()
            inner_upper = inner.upper()
            if inner_upper in REGISTER_NAMES:
                return Operand(OperandKind.MEM_REG, REGISTER_NAMES[inner_upper])
            return Operand(OperandKind.MEM, eval_expr(inner, self.symbols))
        return Operand(OperandKind.IMM, eval_expr(text, self.symbols))


def assemble_path(source: Path, output: Path, listing: Path | None = None) -> ProgramImage:
    image = Assembler().assemble_file(source)
    output.write_bytes(image.binary)
    if listing is not None:
        listing.write_text(image.listing, encoding="utf-8")
    return image


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Assemble lab4 asm source into binary machine code.")
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--listing", type=Path)
    parser.add_argument("--symbols", type=Path)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    image = assemble_path(args.source, args.output, args.listing)
    if args.symbols is not None:
        lines = [f"{name} = 0x{value:X}" for name, value in image.symbols.items()]
        args.symbols.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
