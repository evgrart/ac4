.const ARRAY_BASE 0x1000

.org 0
_start:
    MOV SP, #STACK_TOP
    CALL read_array_size
    MOV R5, R0        ; R5 = array size
    CALL bubble_sort
    CALL print_array
    HALT

; Read count of numbers from input
read_array_size:
    MOV R0, #0
read_size_loop:
    LOADB R1, [IO_STATUS]
    CMP R1, #0
    JZ read_size_done
    LOADB R1, [IO_IN]
    CMP R1, #LF
    JZ read_size_done
    CMP R1, #CR
    JZ read_size_done
    SUB R1, #48
    MUL R0, #10
    ADD R0, R1
    JMP read_size_loop
read_size_done:
    RET

; Bubble sort: array at ARRAY_BASE, size in R5
bubble_sort:
    PUSH R1
    PUSH R2
    PUSH R3
    PUSH R4
    PUSH R6
    MOV R1, #0        ; i = 0
    
    ; First, read array from input
read_array:
    MOV R2, #0        ; index
read_array_loop:
    CMP R2, R5
    JGE read_array_done
    MOV R0, #0        ; number to read
read_number_loop:
    LOADB R3, [IO_STATUS]
    CMP R3, #0
    JZ read_number_done
    LOADB R3, [IO_IN]
    CMP R3, #32       ; space
    JZ read_number_done
    CMP R3, #LF
    JZ read_number_done
    CMP R3, #CR
    JZ read_number_done
    SUB R3, #48
    MUL R0, #10
    ADD R0, R3
    JMP read_number_loop
read_number_done:
    MOV R3, R2
    MUL R3, #4
    ADD R3, #ARRAY_BASE
    MOV [R3], R0
    ADD R2, #1
    JMP read_array_loop
read_array_done:
    
    ; Bubble sort on loaded array
    MOV R1, #0        ; i = 0
sort_outer:
    CMP R1, R5
    JGE sort_done
    MOV R2, #0        ; j = 0
sort_inner:
    MOV R3, R5
    SUB R3, #1
    CMP R2, R3
    JGE sort_inner_done
    MOV R6, R2
    MUL R6, #4
    ADD R6, #ARRAY_BASE
    MOV R3, [R6]      ; array[j]
    MOV R4, R6
    ADD R4, #4
    MOV R0, [R4]      ; array[j+1]
    CMP R3, R0
    JLE sort_inner_next
    ; Swap: array[j] and array[j+1]
    MOV [R6], R0
    MOV [R4], R3
sort_inner_next:
    ADD R2, #1
    JMP sort_inner
sort_inner_done:
    ADD R1, #1
    JMP sort_outer
sort_done:
    POP R6
    POP R4
    POP R3
    POP R2
    POP R1
    RET

; Print array: size in R5, loads from ARRAY_BASE
print_array:
    PUSH R1
    MOV R1, #0
print_array_loop:
    CMP R1, R5
    JGE print_array_done
    MOV R0, R1
    MUL R0, #4
    ADD R0, #ARRAY_BASE
    MOV R0, [R0]      ; load word from array
    CALL print_uint
    STOREB [IO_OUT], #32  ; space
    ADD R1, #1
    JMP print_array_loop
print_array_done:
    STOREB [IO_OUT], #LF
    POP R1
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

.org ARRAY_BASE
