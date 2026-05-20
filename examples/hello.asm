.org 0
_start:
    MOV SP, #STACK_TOP
    MOV R0, #hello
    CALL puts
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

.org 0x0200
hello:
    .cstr "Hello, world!\n"

