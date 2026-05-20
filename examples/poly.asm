.org 0
_start:
    MOV SP, #STACK_TOP
    MOV R1, #2
    ; CISC variable-length instruction:
    ; R0 = 1 + 2*x + 3*x^2, x = 2, result = 17.
    POLY R0, R1, #1, #2, #3
    CALL print_uint
    STOREB [IO_OUT], #LF
    HALT

print_uint:
    PUSH R1
    PUSH R2
    CMP R0, #0
    JNZ print_split
    STOREB [IO_OUT], #48
    JMP print_done
print_split:
    MOV R1, #0
print_split_loop:
    CMP R0, #0
    JZ print_emit
    MOV R2, R0
    MOD R2, #10
    ADD R2, #48
    PUSH R2
    ADD R1, #1
    DIV R0, #10
    JMP print_split_loop
print_emit:
    CMP R1, #0
    JZ print_done
    POP R2
    STOREB [IO_OUT], R2
    SUB R1, #1
    JMP print_emit
print_done:
    POP R2
    POP R1
    RET

