from __future__ import annotations

from lab4.isa import Opcode

COMMON_CYCLE = ("FETCH", "DECODE")

MICROPROGRAMS: dict[Opcode, tuple[str, ...]] = {
    Opcode.NOP: ("EXEC_NOP",),
    Opcode.HALT: ("EXEC_HALT",),
    Opcode.MOV: ("EXEC_MOVE",),
    Opcode.ADD: ("EXEC_ALU_ADD",),
    Opcode.SUB: ("EXEC_ALU_SUB",),
    Opcode.MUL: ("EXEC_ALU_MUL",),
    Opcode.DIV: ("EXEC_ALU_DIV",),
    Opcode.MOD: ("EXEC_ALU_MOD",),
    Opcode.CMP: ("EXEC_COMPARE",),
    Opcode.JMP: ("EXEC_BRANCH",),
    Opcode.JZ: ("EXEC_BRANCH",),
    Opcode.JNZ: ("EXEC_BRANCH",),
    Opcode.JG: ("EXEC_BRANCH",),
    Opcode.JGE: ("EXEC_BRANCH",),
    Opcode.JL: ("EXEC_BRANCH",),
    Opcode.JLE: ("EXEC_BRANCH",),
    Opcode.PUSH: ("EXEC_STACK_WRITE",),
    Opcode.POP: ("EXEC_STACK_READ",),
    Opcode.CALL: ("EXEC_CALL",),
    Opcode.RET: ("EXEC_RET",),
    Opcode.LOADB: ("EXEC_LOAD_BYTE",),
    Opcode.STOREB: ("EXEC_STORE_BYTE",),
    Opcode.POLY: ("EXEC_CISC_POLY",),
    Opcode.SSON: ("EXEC_SUPER_ON",),
    Opcode.SSOFF: ("EXEC_SUPER_OFF",),
}

