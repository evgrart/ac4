.const DATA_BASE 0x1000

.org 0
_start:
    MOV SP, #STACK_TOP
    ; Demonstration of 64-bit arithmetic.
    ; Input contains two unsigned 32-bit values. They are widened to
    ; high:low word pairs, added as a 64-bit value, then printed.
    CALL read_uint
    MOV [num1_low], R0
    MOV [num1_high], #0

    CALL read_uint
    MOV [num2_low], R0
    MOV [num2_high], #0

    MOV R0, [num1_low]
    MOV R1, [num1_high]
    MOV R2, [num2_low]
    MOV R3, [num2_high]

    ADD R0, R2
    MOV R4, FLAGS
    ADD R1, R3
    CMP R4, #8
    JL add_no_carry
    ADD R1, #1
add_no_carry:
    MOV [result_low], R0
    MOV [result_high], R1

    MOV R0, [result_high]
    CMP R0, #0
    JZ print_low_only
    CALL print_uint
    STOREB [IO_OUT], #58
print_low_only:
    MOV R0, [result_low]
    CALL print_uint
    STOREB [IO_OUT], #LF
    HALT

; Read unsigned decimal token from input stream into R0.
read_uint:
    MOV R0, #0
read_loop:
    LOADB R1, [IO_STATUS]
    CMP R1, #0
    JZ read_done
    LOADB R1, [IO_IN]
    CMP R1, #32
    JZ read_done
    CMP R1, #LF
    JZ read_done
    CMP R1, #CR
    JZ read_done
    SUB R1, #48
    MUL R0, #10
    ADD R0, R1
    JMP read_loop
read_done:
    RET

; Print unsigned integer from R0.
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

.org DATA_BASE
num1_high:
    .word 0
num1_low:
    .word 0
num2_high:
    .word 0
num2_low:
    .word 0
result_high:
    .word 0
result_low:
    .word 0
