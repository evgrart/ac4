.org 0
_start:
    MOV SP, #STACK_TOP
    MOV R0, #prompt
    CALL puts
    CALL read_cstr
    MOV R1, R0
    MOV R0, #greeting
    CALL puts
    MOV R0, R1
    CALL puts
    STOREB [IO_OUT], #33
    STOREB [IO_OUT], #LF
    HALT

; Print zero-terminated string addressed by R0.
puts:
    PUSH R1
puts_loop:
    LOADB R1, [R0]
    CMP R1, #NUL
    JZ puts_done
    STOREB [IO_OUT], R1
    ADD R0, #1
    JMP puts_loop
puts_done:
    POP R1
    RET

; Read C-string from input into buffer at 0x0400, return address in R0.
read_cstr:
    MOV R0, #0x0400
    MOV R1, R0
read_cstr_loop:
    LOADB R2, [IO_STATUS]
    CMP R2, #0
    JZ read_cstr_done
    LOADB R2, [IO_IN]
    CMP R2, #LF
    JZ read_cstr_done
    CMP R2, #CR
    JZ read_cstr_done
    STOREB [R1], R2
    ADD R1, #1
    JMP read_cstr_loop
read_cstr_done:
    MOV R2, #NUL
    STOREB [R1], R2
    RET

.org 0x0200
prompt:
    .cstr "What is your name?\n"

greeting:
    .cstr "Hello, "

.org 0x0400
