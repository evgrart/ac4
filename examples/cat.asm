.org 0
_start:
cat_loop:
    LOADB R0, [IO_STATUS]
    CMP R0, #0
    JZ cat_done
    LOADB R0, [IO_IN]
    STOREB [IO_OUT], R0
    JMP cat_loop
cat_done:
    HALT

