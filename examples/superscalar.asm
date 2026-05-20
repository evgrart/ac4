.org 0
_start:
    MOV R1, #1
    MOV R2, #2
    ADD R1, #3
    ADD R2, #4
    MOV [a], R1
    MOV [b], R2
    HALT

.org 0x0200
a:
    .word 0
b:
    .word 0

