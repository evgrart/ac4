"""ISA definition and instruction representation for ACS Lab 4.

Defines:
- Instruction encoding format with variable-length support
- Register and operand types
- Opcode definitions
- Constants for I/O addressing and memory layout
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import IntEnum

WORD_BITS = 32
WORD_BYTES = 4
U32_MASK = (1 << WORD_BITS) - 1
S32_SIGN = 1 << (WORD_BITS - 1)
S24_SIGN = 1 << 23
U24_MASK = (1 << 24) - 1

IO_STATUS = 0xFFF0
IO_IN = 0xFFF4
IO_OUT = 0xFFF8
DEFAULT_STACK_TOP = 0x8000


class Opcode(IntEnum):
    NOP = 0x00
    HALT = 0x01
    MOV = 0x02
    ADD = 0x03
    SUB = 0x04
    MUL = 0x05
    DIV = 0x06
    MOD = 0x07
    CMP = 0x08
    JMP = 0x09
    JZ = 0x0A
    JNZ = 0x0B
    JG = 0x0C
    JGE = 0x0D
    JL = 0x0E
    JLE = 0x0F
    PUSH = 0x10
    POP = 0x11
    CALL = 0x12
    RET = 0x13
    LOADB = 0x14
    STOREB = 0x15
    POLY = 0x16
    SSON = 0x17
    SSOFF = 0x18


OPCODE_BY_NAME = {opcode.name: opcode for opcode in Opcode}


class OperandKind(IntEnum):
    REG = 0
    IMM = 1
    MEM = 2
    MEM_REG = 3


REGISTER_NAMES: dict[str, int] = {
    "R0": 0,
    "R1": 1,
    "R2": 2,
    "R3": 3,
    "R4": 4,
    "R5": 5,
    "R6": 6,
    "R7": 7,
    "SP": 8,
    "BP": 9,
    "PC": 10,
    "FLAGS": 11,
    "ACC": 12,
}

REGISTER_BY_ID = {number: name for name, number in REGISTER_NAMES.items()}

FLAG_Z = 1 << 0
FLAG_N = 1 << 1
FLAG_G = 1 << 2
FLAG_C = 1 << 3


@dataclass(frozen=True)
class Operand:
    """Single operand in an instruction."""

    kind: OperandKind
    payload: int


@dataclass(frozen=True)
class Instruction:
    """Decoded instruction with opcode and operands."""

    opcode: Opcode
    operands: tuple[Operand, ...]
    address: int = 0
    source: str = ""

    @property
    def size(self) -> int:
        """Size in bytes including header and all operands."""
        return WORD_BYTES * (1 + len(self.operands))


def to_u32(value: int) -> int:
    """Convert to 32-bit unsigned integer."""
    return value & U32_MASK


def to_s32(value: int) -> int:
    """Convert to 32-bit signed integer (two's complement)."""
    value &= U32_MASK
    if value & S32_SIGN:
        return value - (1 << WORD_BITS)
    return value


def encode_s24(value: int) -> int:
    """Encode 24-bit signed operand payload."""
    if not -(1 << 23) <= value < (1 << 24):
        raise ValueError(f"operand payload out of 24-bit range: {value}")
    return value & U24_MASK


def decode_s24(value: int) -> int:
    """Decode 24-bit signed operand payload (two's complement)."""
    value &= U24_MASK
    if value & S24_SIGN:
        return value - (1 << 24)
    return value


def encode_operand(operand: Operand) -> int:
    return int(operand.kind) | (encode_s24(operand.payload) << 8)


def decode_operand(word: int) -> Operand:
    kind = OperandKind(word & 0xFF)
    payload = decode_s24((word >> 8) & U24_MASK)
    return Operand(kind, payload)


def instruction_words(instruction: Instruction) -> list[int]:
    if len(instruction.operands) > 255:
        raise ValueError("too many operands")
    header = int(instruction.opcode) | (len(instruction.operands) << 8)
    return [header, *(encode_operand(operand) for operand in instruction.operands)]


def decode_instruction(words: list[int], address: int = 0, source: str = "") -> Instruction:
    if not words:
        raise ValueError("empty instruction word list")
    header = words[0]
    opcode = Opcode(header & 0xFF)
    count = (header >> 8) & 0xFF
    if len(words) != count + 1:
        raise ValueError(f"expected {count} operands, got {len(words) - 1}")
    operands = tuple(decode_operand(word) for word in words[1:])
    return Instruction(opcode, operands, address, source)


def pack_words(words: Iterable[int]) -> bytes:
    return b"".join(to_u32(word).to_bytes(WORD_BYTES, "little") for word in words)


def unpack_word(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + WORD_BYTES], "little")


def format_operand(operand: Operand) -> str:
    if operand.kind == OperandKind.REG:
        return REGISTER_BY_ID.get(operand.payload, f"R?{operand.payload}")
    if operand.kind == OperandKind.IMM:
        return f"#{operand.payload}"
    if operand.kind == OperandKind.MEM:
        return f"[0x{operand.payload:04X}]"
    if operand.kind == OperandKind.MEM_REG:
        return f"[{REGISTER_BY_ID.get(operand.payload, f'R?{operand.payload}')}]"
    raise AssertionError(f"unknown operand kind: {operand.kind}")


def format_instruction(instruction: Instruction) -> str:
    operands = ", ".join(format_operand(operand) for operand in instruction.operands)
    if operands:
        return f"{instruction.opcode.name} {operands}"
    return instruction.opcode.name


def default_symbols() -> dict[str, int]:
    return {
        "IO_STATUS": IO_STATUS,
        "IO_IN": IO_IN,
        "IO_OUT": IO_OUT,
        "STACK_TOP": DEFAULT_STACK_TOP,
        "NUL": 0,
        "LF": 10,
        "CR": 13,
        "TRUE": 1,
        "FALSE": 0,
    }
