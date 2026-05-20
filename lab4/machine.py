from __future__ import annotations

import argparse
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from lab4.isa import (
    FLAG_C,
    FLAG_G,
    FLAG_N,
    FLAG_Z,
    IO_IN,
    IO_OUT,
    IO_STATUS,
    REGISTER_NAMES,
    WORD_BYTES,
    Instruction,
    Opcode,
    Operand,
    OperandKind,
    decode_instruction,
    format_instruction,
    to_s32,
    to_u32,
    unpack_word,
)
from lab4.microcode import COMMON_CYCLE, MICROPROGRAMS


class MachineError(RuntimeError):
    pass


class InputExhausted(MachineError):
    pass


@dataclass(frozen=True)
class Decoded:
    instruction: Instruction
    words: list[int]


class Memory:
    def __init__(self, image: bytes, input_text: str = "") -> None:
        self._bytes: dict[int, int] = dict(enumerate(image))
        self.input_buffer = list(input_text.encode("utf-8"))
        self.output_buffer: list[int] = []

    def read_byte(self, address: int) -> int:
        address = to_u32(address)
        if address == IO_STATUS:
            return int(bool(self.input_buffer))
        if address == IO_IN:
            if not self.input_buffer:
                raise InputExhausted("input stream is empty")
            return self.input_buffer.pop(0)
        if address == IO_OUT:
            return 0
        return self._bytes.get(address, 0)

    def write_byte(self, address: int, value: int) -> None:
        address = to_u32(address)
        value &= 0xFF
        if address == IO_OUT:
            self.output_buffer.append(value)
            return
        if address in (IO_STATUS, IO_IN):
            return
        self._bytes[address] = value

    def read_word(self, address: int) -> int:
        address = to_u32(address)
        if address in (IO_STATUS, IO_IN, IO_OUT):
            return self.read_byte(address)
        raw = bytes(self.read_byte(address + offset) for offset in range(WORD_BYTES))
        return unpack_word(raw, 0)

    def write_word(self, address: int, value: int) -> None:
        address = to_u32(address)
        if address == IO_OUT:
            self.write_byte(address, value)
            return
        for offset in range(WORD_BYTES):
            self.write_byte(address + offset, (value >> (8 * offset)) & 0xFF)

    def output_text(self) -> str:
        return bytes(self.output_buffer).decode("utf-8", errors="replace")


class Machine:
    def __init__(
        self,
        image: bytes,
        input_text: str = "",
        *,
        pc: int = 0,
        stack_top: int = 0x8000,
        superscalar: bool = True,
    ) -> None:
        self.memory = Memory(image, input_text)
        self.regs = [0] * 8
        self.pc = pc
        self.sp = stack_top
        self.bp = stack_top
        self.flags = 0
        self.acc = 0
        self.tick_count = 0
        self.instruction_count = 0
        self.superscalar = superscalar
        self.halted = False
        self.halt_reason = ""
        self.ir = 0
        self.mpc = 0
        self.trace: list[str] = []
        self._fetched_header = 0
        self._fetched_address = 0
        self._current: Decoded | None = None
        self._paired: Decoded | None = None
        self._super_note = ""

    def run(self, max_ticks: int = 100_000) -> str:
        while not self.halted and self.tick_count < max_ticks:
            self.step_instruction()
        if self.tick_count >= max_ticks and not self.halted:
            self.halted = True
            self.halt_reason = "max_ticks"
        return self.memory.output_text()

    def step_instruction(self) -> None:
        if self.halted:
            return
        try:
            for micro_op in COMMON_CYCLE:
                self._execute_micro(micro_op)
            current = self._current
            if current is None:
                raise MachineError("decode did not produce instruction")
            for micro_op in MICROPROGRAMS[current.instruction.opcode]:
                self._execute_micro(micro_op)
        except InputExhausted as error:
            self.halted = True
            self.halt_reason = str(error)
            self._log("HALT_INPUT", self.halt_reason)

    def _execute_micro(self, micro_op: str) -> None:
        self.mpc += 1
        details = ""
        if micro_op == "FETCH":
            self._fetched_address = self.pc
            self._fetched_header = self.memory.read_word(self.pc)
            self.ir = self._fetched_header
            self.pc = to_u32(self.pc + WORD_BYTES)
            details = f"addr=0x{self._fetched_address:08X} header=0x{self.ir:08X}"
        elif micro_op == "DECODE":
            self._current = self._decode_from_header(self._fetched_address, self._fetched_header)
            self._paired = self._try_pair(self._current)
            details = format_instruction(self._current.instruction)
            if self._paired is not None:
                details += f" || {format_instruction(self._paired.instruction)}"
            elif self._super_note:
                details += f" ; {self._super_note}"
        else:
            current = self._current
            if current is None:
                raise MachineError("execute without current instruction")
            pair = self._paired
            if pair is not None:
                self._execute_one(current.instruction)
                self._execute_one(pair.instruction)
                self.instruction_count += 2
                left = format_instruction(current.instruction)
                right = format_instruction(pair.instruction)
                details = f"parallel: {left} || {right}"
            else:
                self._execute_one(current.instruction)
                self.instruction_count += 1
                details = format_instruction(current.instruction)
            self._current = None
            self._paired = None
        self._log(micro_op, details)

    def _decode_from_header(self, address: int, header: int) -> Decoded:
        count = (header >> 8) & 0xFF
        words = [header]
        for _ in range(count):
            words.append(self.memory.read_word(self.pc))
            self.pc = to_u32(self.pc + WORD_BYTES)
        instruction = decode_instruction(words, address=address)
        return Decoded(instruction, words)

    def _peek_decode(self, address: int) -> Decoded:
        header = self.memory.read_word(address)
        count = (header >> 8) & 0xFF
        words = [header]
        cursor = address + WORD_BYTES
        for _ in range(count):
            words.append(self.memory.read_word(cursor))
            cursor += WORD_BYTES
        return Decoded(decode_instruction(words, address=address), words)

    def _try_pair(self, current: Decoded) -> Decoded | None:
        self._super_note = ""
        if not self.superscalar:
            self._super_note = "super=off"
            return None
        first = current.instruction
        if not self._is_super_eligible(first):
            self._super_note = "super=blocked:control-or-io"
            return None
        second = self._peek_decode(self.pc)
        if not self._is_super_eligible(second.instruction):
            self._super_note = "super=blocked:next-not-eligible"
            return None
        if not self._independent(first, second.instruction):
            self._super_note = "super=blocked:data-dependency"
            return None
        self.pc = to_u32(self.pc + second.instruction.size)
        self._super_note = "super=issued"
        return second

    def _is_super_eligible(self, instruction: Instruction) -> bool:
        eligible_opcodes = {
            Opcode.MOV,
            Opcode.ADD,
            Opcode.SUB,
            Opcode.MUL,
            Opcode.DIV,
            Opcode.MOD,
            Opcode.LOADB,
        }
        if instruction.opcode not in eligible_opcodes:
            return False
        for operand in instruction.operands:
            if operand.kind == OperandKind.MEM_REG:
                return False
            if operand.kind == OperandKind.MEM and operand.payload in (IO_STATUS, IO_IN, IO_OUT):
                return False
            if operand.kind == OperandKind.REG and operand.payload >= REGISTER_NAMES["SP"]:
                return False
        return True

    def _independent(self, first: Instruction, second: Instruction) -> bool:
        first_reads, first_writes = self._access_sets(first)
        second_reads, second_writes = self._access_sets(second)
        if first_writes & (second_reads | second_writes):
            return False
        return not second_writes & first_reads

    def _access_sets(self, instruction: Instruction) -> tuple[set[str], set[str]]:
        reads: set[str] = set()
        writes: set[str] = set()

        def add_read(operand: Operand) -> None:
            if operand.kind == OperandKind.REG:
                reads.add(f"R{operand.payload}")
            elif operand.kind == OperandKind.MEM:
                reads.add(f"M{operand.payload}")
            elif operand.kind == OperandKind.MEM_REG:
                reads.add(f"R{operand.payload}")
                reads.add("M*")

        def add_write(operand: Operand) -> None:
            if operand.kind == OperandKind.REG:
                writes.add(f"R{operand.payload}")
            elif operand.kind == OperandKind.MEM:
                writes.add(f"M{operand.payload}")
            elif operand.kind == OperandKind.MEM_REG:
                reads.add(f"R{operand.payload}")
                writes.add("M*")

        operands = instruction.operands
        if instruction.opcode == Opcode.MOV and len(operands) == 2:
            add_write(operands[0])
            add_read(operands[1])
        elif instruction.opcode in {Opcode.ADD, Opcode.SUB, Opcode.MUL, Opcode.DIV, Opcode.MOD} and len(operands) == 2:
            add_read(operands[0])
            add_read(operands[1])
            add_write(operands[0])
            writes.add("FLAGS")
        elif instruction.opcode == Opcode.LOADB and len(operands) == 2:
            add_write(operands[0])
            add_read(operands[1])
        else:
            reads.add("*")
            writes.add("*")
        return reads, writes

    def _execute_one(self, instruction: Instruction) -> None:
        operands = instruction.operands
        opcode = instruction.opcode
        if opcode == Opcode.NOP:
            return
        if opcode == Opcode.HALT:
            self.halted = True
            self.halt_reason = "halt instruction"
            return
        if opcode == Opcode.MOV:
            self._expect_count(instruction, 2)
            self._write_operand(operands[0], self._read_operand(operands[1]))
            return
        if opcode in {Opcode.ADD, Opcode.SUB, Opcode.MUL, Opcode.DIV, Opcode.MOD}:
            self._expect_count(instruction, 2)
            left = self._read_operand(operands[0])
            right = self._read_operand(operands[1])
            result = self._alu(opcode, left, right)
            self._write_operand(operands[0], result)
            self._set_flags(result, carry=self._carry_out(opcode, left, right))
            return
        if opcode == Opcode.CMP:
            self._expect_count(instruction, 2)
            self._set_flags(to_s32(self._read_operand(operands[0])) - to_s32(self._read_operand(operands[1])))
            return
        if opcode in {Opcode.JMP, Opcode.JZ, Opcode.JNZ, Opcode.JG, Opcode.JGE, Opcode.JL, Opcode.JLE}:
            self._expect_count(instruction, 1)
            if self._branch_taken(opcode):
                self.pc = self._read_operand(operands[0])
            return
        if opcode == Opcode.PUSH:
            self._expect_count(instruction, 1)
            self.sp = to_u32(self.sp - WORD_BYTES)
            self.memory.write_word(self.sp, self._read_operand(operands[0]))
            return
        if opcode == Opcode.POP:
            self._expect_count(instruction, 1)
            self._write_operand(operands[0], self.memory.read_word(self.sp))
            self.sp = to_u32(self.sp + WORD_BYTES)
            return
        if opcode == Opcode.CALL:
            self._expect_count(instruction, 1)
            self.sp = to_u32(self.sp - WORD_BYTES)
            self.memory.write_word(self.sp, self.pc)
            self.pc = self._read_operand(operands[0])
            return
        if opcode == Opcode.RET:
            self._expect_count(instruction, 0)
            self.pc = self.memory.read_word(self.sp)
            self.sp = to_u32(self.sp + WORD_BYTES)
            return
        if opcode == Opcode.LOADB:
            self._expect_count(instruction, 2)
            self._write_operand(operands[0], self._read_byte_operand(operands[1]))
            return
        if opcode == Opcode.STOREB:
            self._expect_count(instruction, 2)
            self._write_byte_operand(operands[0], self._read_operand(operands[1]))
            return
        if opcode == Opcode.POLY:
            if len(operands) < 3:
                raise MachineError("POLY expects dst, x and at least one coefficient")
            x = self._read_operand(operands[1])
            result = self._read_operand(operands[-1])
            for coeff in reversed(operands[2:-1]):
                result = to_u32(to_s32(result) * to_s32(x) + to_s32(self._read_operand(coeff)))
            self._write_operand(operands[0], result)
            self._set_flags(result)
            return
        if opcode == Opcode.SSON:
            self._expect_count(instruction, 0)
            self.superscalar = True
            return
        if opcode == Opcode.SSOFF:
            self._expect_count(instruction, 0)
            self.superscalar = False
            return
        raise MachineError(f"unsupported opcode {opcode.name}")

    def _read_operand(self, operand: Operand) -> int:
        if operand.kind == OperandKind.IMM:
            return to_u32(operand.payload)
        if operand.kind == OperandKind.REG:
            return self._read_reg(operand.payload)
        if operand.kind == OperandKind.MEM:
            return self.memory.read_word(operand.payload)
        if operand.kind == OperandKind.MEM_REG:
            return self.memory.read_word(self._read_reg(operand.payload))
        raise MachineError(f"unknown operand kind {operand.kind}")

    def _write_operand(self, operand: Operand, value: int) -> None:
        value = to_u32(value)
        if operand.kind == OperandKind.REG:
            self._write_reg(operand.payload, value)
            return
        if operand.kind == OperandKind.MEM:
            self.memory.write_word(operand.payload, value)
            return
        if operand.kind == OperandKind.MEM_REG:
            self.memory.write_word(self._read_reg(operand.payload), value)
            return
        raise MachineError("destination must be register or memory")

    def _read_byte_operand(self, operand: Operand) -> int:
        if operand.kind == OperandKind.MEM:
            return self.memory.read_byte(operand.payload)
        if operand.kind == OperandKind.MEM_REG:
            return self.memory.read_byte(self._read_reg(operand.payload))
        return self._read_operand(operand) & 0xFF

    def _write_byte_operand(self, operand: Operand, value: int) -> None:
        if operand.kind == OperandKind.MEM:
            self.memory.write_byte(operand.payload, value)
            return
        if operand.kind == OperandKind.MEM_REG:
            self.memory.write_byte(self._read_reg(operand.payload), value)
            return
        raise MachineError("byte destination must be memory")

    def _read_reg(self, register: int) -> int:
        if 0 <= register <= 7:
            return self.regs[register]
        if register == REGISTER_NAMES["SP"]:
            return self.sp
        if register == REGISTER_NAMES["BP"]:
            return self.bp
        if register == REGISTER_NAMES["PC"]:
            return self.pc
        if register == REGISTER_NAMES["FLAGS"]:
            return self.flags
        if register == REGISTER_NAMES["ACC"]:
            return self.acc
        raise MachineError(f"unknown register {register}")

    def _write_reg(self, register: int, value: int) -> None:
        value = to_u32(value)
        if 0 <= register <= 7:
            self.regs[register] = value
            return
        if register == REGISTER_NAMES["SP"]:
            self.sp = value
            return
        if register == REGISTER_NAMES["BP"]:
            self.bp = value
            return
        if register == REGISTER_NAMES["PC"]:
            self.pc = value
            return
        if register == REGISTER_NAMES["FLAGS"]:
            self.flags = value
            return
        if register == REGISTER_NAMES["ACC"]:
            self.acc = value
            return
        raise MachineError(f"unknown register {register}")

    def _alu(self, opcode: Opcode, left: int, right: int) -> int:
        if opcode == Opcode.ADD:
            return to_u32(to_s32(left) + to_s32(right))
        if opcode == Opcode.SUB:
            return to_u32(to_s32(left) - to_s32(right))
        if opcode == Opcode.MUL:
            return to_u32(to_s32(left) * to_s32(right))
        if opcode == Opcode.DIV:
            if to_s32(right) == 0:
                raise MachineError("division by zero")
            return to_u32(to_s32(left) // to_s32(right))
        if opcode == Opcode.MOD:
            if to_s32(right) == 0:
                raise MachineError("modulo by zero")
            return to_u32(to_s32(left) % to_s32(right))
        raise MachineError(f"opcode {opcode.name} is not ALU operation")

    def _carry_out(self, opcode: Opcode, left: int, right: int) -> bool:
        if opcode == Opcode.ADD:
            return left + right > 0xFFFF_FFFF
        if opcode == Opcode.SUB:
            return left < right
        return False

    def _set_flags(self, value: int, *, carry: bool = False) -> None:
        signed = to_s32(value)
        flags = 0
        if signed == 0:
            flags |= FLAG_Z
        if signed < 0:
            flags |= FLAG_N
        if signed > 0:
            flags |= FLAG_G
        if carry:
            flags |= FLAG_C
        self.flags = flags

    def _branch_taken(self, opcode: Opcode) -> bool:
        if opcode == Opcode.JMP:
            return True
        if opcode == Opcode.JZ:
            return bool(self.flags & FLAG_Z)
        if opcode == Opcode.JNZ:
            return not bool(self.flags & FLAG_Z)
        if opcode == Opcode.JG:
            return bool(self.flags & FLAG_G)
        if opcode == Opcode.JGE:
            return bool(self.flags & (FLAG_G | FLAG_Z))
        if opcode == Opcode.JL:
            return bool(self.flags & FLAG_N)
        if opcode == Opcode.JLE:
            return bool(self.flags & (FLAG_N | FLAG_Z))
        return False

    def _expect_count(self, instruction: Instruction, count: int) -> None:
        if len(instruction.operands) != count:
            raise MachineError(f"{instruction.opcode.name} expects {count} operands")

    def _log(self, micro_op: str, details: str) -> None:
        regs = " ".join(f"R{index}={to_s32(value)}" for index, value in enumerate(self.regs[:6]))
        flags = "".join(
            name for bit, name in ((FLAG_Z, "Z"), (FLAG_N, "N"), (FLAG_G, "G"), (FLAG_C, "C")) if self.flags & bit
        )
        if not flags:
            flags = "-"
        line = (
            f"TICK={self.tick_count:05d} MPC={self.mpc:03d} {micro_op:<16} "
            f"PC=0x{self.pc:08X} SP=0x{self.sp:08X} FLAGS={flags:<3} {regs} :: {details}"
        )
        self.trace.append(line)
        self.tick_count += 1


def run_binary(
    binary_path: Path,
    input_path: Path | None = None,
    *,
    log_path: Path | None = None,
    superscalar: bool = True,
    max_ticks: int = 100_000,
) -> str:
    input_text = input_path.read_text(encoding="utf-8") if input_path is not None else ""
    machine = Machine(binary_path.read_bytes(), input_text, superscalar=superscalar)
    output = machine.run(max_ticks=max_ticks)
    if log_path is not None:
        log_path.write_text("\n".join(machine.trace) + "\n", encoding="utf-8")
    return output


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run lab4 binary machine code.")
    parser.add_argument("binary", type=Path)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--log", type=Path)
    parser.add_argument("--max-ticks", type=int, default=100_000)
    parser.add_argument("--no-superscalar", action="store_true")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    output = run_binary(
        args.binary,
        args.input,
        log_path=args.log,
        superscalar=not args.no_superscalar,
        max_ticks=args.max_ticks,
    )
    print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
