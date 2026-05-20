.org 0
_start:
    MOV SP, #STACK_TOP
    CALL read_uint
    ; Euler problem 6:
    ; result = (1 + ... + n)^2 - (1^2 + ... + n^2)
    MOV R1, #1       ; i
    MOV R2, #0       ; sum
    MOV R3, #0       ; sum of squares
calc_loop:
    CMP R1, R0
    JG calc_done
    ADD R2, R1
    MOV R4, R1
    MUL R4, R1
    ADD R3, R4
    ADD R1, #1
    JMP calc_loop
calc_done:
    MUL R2, R2
    SUB R2, R3
    MOV R0, R2
    CALL print_uint
    STOREB [IO_OUT], #LF
    HALT

; Read unsigned decimal number from the input stream into R0.
read_uint:
    MOV R0, #0
read_loop:
    LOADB R1, [IO_STATUS]
    CMP R1, #0
    JZ read_done
    LOADB R1, [IO_IN]
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

