# ACS Lab 4

Вариант:

```text
asm | cisc | neum | mc | tick | binary | stream | mem | cstr | prob2 | superscalar
```

Проект реализует минимальную инструментальную цепочку для лабораторной работы: ассемблер, бинарное представление ISA,
микропрограммную модель процессора, stream I/O через memory-mapped адреса и набор golden tests.

## Структура

- `lab4/assembler.py` -- препроцессор и двухпроходный ассемблер.
- `lab4/isa.py` -- описание машинного слова, регистров, опкодов, операндов и кодирования.
- `lab4/microcode.py` -- память микропрограмм.
- `lab4/machine.py` -- модель процессора и памяти.
- `lab4/golden.py` -- генератор golden-артефактов.
- `examples/` -- программы на разработанном ассемблере.
- `tests/` -- интеграционные и регрессионные тесты.
- `golden/` -- проверяемые golden tests.
- `build/` -- полные бинарники, листинги и журналы выполнения.

## Запуск

```bash
python -m unittest discover -s tests -v
python test_new_examples.py
python check_syntax.py
python -m lab4.golden
ruff format --check lab4 tests test_new_examples.py check_syntax.py
ruff check lab4 tests test_new_examples.py check_syntax.py
mypy lab4 tests test_new_examples.py check_syntax.py
```

Для сборки отдельного примера:

```bash
python -m lab4.assembler examples/prob2.asm build/prob2.bin --listing build/prob2.hex --symbols build/prob2.sym
python -m lab4.machine build/prob2.bin --input build/prob2.in --log build/prob2.log
```

## Язык

Язык программы -- ассемблер. Поддерживаются:

- метки: `label:`;
- директива размещения `.org`;
- секции `.text`, `.data`, `.section`;
- данные `.word`, `.byte`, `.zero`, `.cstr`, `.align`;
- константы `.const`, `.equ`, `%define`;
- макросы `.macro ... .endm`;
- условная компиляция `.if`, `.ifdef`, `.ifndef`, `.else`, `.endif`;
- комментарии после `;`.

Строки варианта `cstr` задаются директивой `.cstr`, которая помещает байты UTF-8 и завершающий `NUL`.

### Формальная Грамматика

```text
<program>      ::= <line>*
<line>         ::= <empty> | <label_line> | <directive> | <instruction>
<label_line>   ::= <label> ":" <line_tail>
<line_tail>    ::= <empty> | <directive> | <instruction>
<label>        ::= <identifier>
<identifier>   ::= <letter_or_underscore> <identifier_char>*

<directive>    ::= ".org" <expr>
                 | ".text" | ".data" | ".section" <identifier>
                 | ".word" <expr_list>
                 | ".byte" <byte_list>
                 | ".zero" <expr>
                 | ".align" <expr>
                 | ".cstr" <string>
                 | (".const" | ".equ" | "%define") <identifier> <expr>
                 | ".macro" <identifier> <macro_params>
                 | ".endm"
                 | (".if" <expr>) | (".ifdef" <identifier>) | (".ifndef" <identifier>)
                 | ".else" | ".endif"

<instruction>  ::= <mnemonic> | <mnemonic> <operand_list>
<operand_list> ::= <operand> | <operand> "," <operand_list>
<operand>      ::= <register>
                 | "#" <expr>
                 | "[" <expr> "]"
                 | "[" <register> "]"
                 | <expr>

<expr>         ::= <integer> | <identifier> | <unary_expr> | <binary_expr> | <compare_expr>
<string>       ::= Python-compatible double quoted string literal
```

Семантика ассемблера:

- метка связывается с текущим адресом сборки;
- `.org` изменяет текущий адрес размещения;
- `.cstr` размещает статическую C-строку в памяти данных;
- макросы раскрываются текстово до первого прохода ассемблера;
- выражения вычисляются во время трансляции;
- все машинные данные в командах и `.word` приводятся к 32-битному машинному слову.

## Память

Архитектура фон Неймана: инструкции, статические данные, стек, буферы программ и memory-mapped I/O находятся в одном
адресном пространстве. Адресация байтовая, машинное слово -- 32 бита, порядок байтов -- little-endian.

Стандартные адреса ввода-вывода:

- `IO_STATUS = 0xFFF0` -- ненулевое значение, если во входном потоке есть байты;
- `IO_IN = 0xFFF4` -- чтение одного байта входного потока;
- `IO_OUT = 0xFFF8` -- запись одного байта в выходной поток.

Стек начинается с `STACK_TOP = 0x8000` и растет вниз. Примеры размещают статические строки и массивы через `.org`, чтобы
данные не пересекались с кодом.

## ISA

Инструкция кодируется переменным числом 32-битных слов. Первое слово -- заголовок:

```text
bits  0..7   opcode
bits  8..15  operand_count
bits 16..31  reserved
```

Каждый операнд занимает отдельное слово:

```text
bits  0..7   operand_kind
bits  8..31  signed payload
```

Виды операндов:

- `REG` -- регистр;
- `IMM` -- непосредственное значение;
- `MEM` -- абсолютный адрес памяти;
- `MEM_REG` -- адрес памяти в регистре.

Регистры: `R0..R7`, `SP`, `BP`, `PC`, `FLAGS`, `ACC`. Флаги: `Z`, `N`, `G`, `C`.

Набор команд включает `MOV`, арифметику `ADD/SUB/MUL/DIV/MOD`, `CMP`, переходы, `PUSH/POP`, `CALL/RET`, `LOADB`,
`STOREB`, управление superscalar-режимом `SSON/SSOFF` и CISC-инструкцию `POLY`. CISC-свойства варианта покрываются
арифметикой с памятью за одну инструкцию, специальными регистрами и переменной длиной инструкции `POLY`.

### Таблица Команд

Число тактов указано для одиночного исполнения без superscalar-слияния. Формула: `FETCH_HEADER + FETCH_OPERAND* +
DECODE + microprogram`.

| Мнемоника | Opcode | Операнды | Такты | Семантика |
|---|---:|---:|---:|---|
| `NOP` | `0x00` | 0 | 3 | Нет операции |
| `HALT` | `0x01` | 0 | 3 | Остановить модель |
| `MOV dst, src` | `0x02` | 2 | 7 | `dst <- src` |
| `ADD dst, src` | `0x03` | 2 | 10 | `dst <- dst + src`, обновить `FLAGS` |
| `SUB dst, src` | `0x04` | 2 | 10 | `dst <- dst - src`, обновить `FLAGS` |
| `MUL dst, src` | `0x05` | 2 | 10 | `dst <- dst * src`, обновить `FLAGS` |
| `DIV dst, src` | `0x06` | 2 | 10 | `dst <- dst / src`, обновить `FLAGS` |
| `MOD dst, src` | `0x07` | 2 | 10 | `dst <- dst % src`, обновить `FLAGS` |
| `CMP left, right` | `0x08` | 2 | 9 | Установить `FLAGS` по `left - right` |
| `JMP target` | `0x09` | 1 | 6 | Безусловный переход |
| `JZ target` | `0x0A` | 1 | 6 | Переход при `Z` |
| `JNZ target` | `0x0B` | 1 | 6 | Переход при отсутствии `Z` |
| `JG target` | `0x0C` | 1 | 6 | Переход при `G` |
| `JGE target` | `0x0D` | 1 | 6 | Переход при `G` или `Z` |
| `JL target` | `0x0E` | 1 | 6 | Переход при `N` |
| `JLE target` | `0x0F` | 1 | 6 | Переход при `N` или `Z` |
| `PUSH src` | `0x10` | 1 | 7 | Записать слово на стек |
| `POP dst` | `0x11` | 1 | 7 | Считать слово со стека |
| `CALL target` | `0x12` | 1 | 8 | Сохранить адрес возврата и перейти |
| `RET` | `0x13` | 0 | 6 | Вернуться из процедуры |
| `LOADB dst, src` | `0x14` | 2 | 7 | Загрузить байт из памяти или I/O |
| `STOREB dst, src` | `0x15` | 2 | 7 | Записать байт в память или I/O |
| `POLY dst, x, c...` | `0x16` | `>=3` | `operands + 8` | Вычислить многочлен `c0 + c1*x + ...` |
| `SSON` | `0x17` | 0 | 4 | Включить superscalar-режим |
| `SSOFF` | `0x18` | 0 | 4 | Выключить superscalar-режим |

## Транслятор

Ассемблер выполняет препроцессинг, первый проход для вычисления адресов и второй проход для генерации бинарного файла.
Результат сборки содержит:

- настоящий бинарный образ `program.bin`;
- текстовый листинг `listing.hex` с адресами, байтами и исходной мнемоникой;
- таблицу символов `symbols.txt`.

## Модель Процессора

Модель выполняется с точностью до микротакта. Метод `step_tick()` выполняет ровно один микрошаг и позволяет остановить
процессор между выборкой заголовка, выборкой операндов, декодированием и исполнением. Метод `step_instruction()`
выполняет микрошаги до завершения очередной инструкции.

Базовый цикл:

```text
FETCH_HEADER -> FETCH_OPERAND* -> DECODE -> microprogram -> COMMIT
```

Память микропрограмм хранится отдельно в `lab4/microcode.py`. Примеры микрошагов:

- `READ_SOURCE`, `WRITE_DESTINATION`;
- `READ_LEFT`, `READ_RIGHT`, `ALU_ADD`, `WRITE_BACK`, `UPDATE_FLAGS`;
- `READ_TARGET`, `EVALUATE_BRANCH`;
- `READ_X`, `READ_COEFFICIENTS`, `CISC_POLY_EVALUATE`;
- `SET_SUPERSCALAR_ON`, `SET_SUPERSCALAR_OFF`.

Журнал процессора содержит номер такта, микропрограммный счетчик, текущий микрошаг, `PC`, `SP`, флаги и часть
регистрового файла.

### Схемы Процессора

Исходники схем для draw.io:

- [DataPath](img/datapath.drawio) -- единая память команд и данных, memory-mapped I/O, регистровый файл, ALU,
  стековый адресатор, блок `POLY` и шины данных/адреса.
- [Control Unit](img/control_unit.drawio) -- микротактовый автомат выборки, декодирования, исполнения микрокоманд,
  выбора микропрограммы и superscalar-выдачи независимой пары команд.

Основные управляющие сигналы: `mem_read_word`, `mem_read_byte`, `mem_write_word`, `mem_write_byte`, `pc_inc`,
`pc_load`, `ir_load`, `reg_read`, `reg_write`, `alu_op`, `flags_write`, `sp_inc`, `sp_dec`, `halt`,
`superscalar_on`, `superscalar_off`. Регистры данных: `R0..R7`, `SP`, `BP`, `PC`, `FLAGS`, `ACC`; служебные
регистры управления: `IR`, `MPC`, буфер операндов и защелка парной инструкции для superscalar-режима.

### Таблица Микропрограмм

| Команды | Микропрограмма |
|---|---|
| `NOP`, `HALT` | `COMMIT` |
| `MOV` | `READ_SOURCE -> WRITE_DESTINATION -> COMMIT` |
| `ADD` | `READ_LEFT -> READ_RIGHT -> ALU_ADD -> WRITE_BACK -> UPDATE_FLAGS -> COMMIT` |
| `SUB` | `READ_LEFT -> READ_RIGHT -> ALU_SUB -> WRITE_BACK -> UPDATE_FLAGS -> COMMIT` |
| `CMP` | `READ_LEFT -> READ_RIGHT -> ALU_SUB -> UPDATE_FLAGS -> COMMIT` |
| `MUL` | `READ_LEFT -> READ_RIGHT -> ALU_MUL -> WRITE_BACK -> UPDATE_FLAGS -> COMMIT` |
| `DIV` | `READ_LEFT -> READ_RIGHT -> ALU_DIV -> WRITE_BACK -> UPDATE_FLAGS -> COMMIT` |
| `MOD` | `READ_LEFT -> READ_RIGHT -> ALU_MOD -> WRITE_BACK -> UPDATE_FLAGS -> COMMIT` |
| `JMP`, `JZ`, `JNZ`, `JG`, `JGE`, `JL`, `JLE` | `READ_TARGET -> EVALUATE_BRANCH -> COMMIT` |
| `PUSH` | `READ_SOURCE -> STACK_DEC -> MEM_WRITE_STACK -> COMMIT` |
| `POP` | `MEM_READ_STACK -> WRITE_DESTINATION -> STACK_INC -> COMMIT` |
| `CALL` | `READ_TARGET -> STACK_DEC -> MEM_WRITE_RETURN -> SET_PC -> COMMIT` |
| `RET` | `MEM_READ_STACK -> STACK_INC -> SET_PC -> COMMIT` |
| `LOADB` | `READ_BYTE_SOURCE -> WRITE_DESTINATION -> COMMIT` |
| `STOREB` | `READ_BYTE_VALUE -> WRITE_BYTE_DESTINATION -> COMMIT` |
| `POLY` | `READ_X -> READ_COEFFICIENTS -> CISC_POLY_EVALUATE -> WRITE_DESTINATION -> UPDATE_FLAGS -> COMMIT` |
| `SSON`, `SSOFF` | `SET_SUPERSCALAR_ON/OFF -> COMMIT` |

Для `CMP` результат вычитания используется только для обновления флагов и не записывается в регистр.

## Superscalar

Модель может параллельно завершать две соседние независимые инструкции. На этапе `DECODE` процессор пробует декодировать
следующую инструкцию, проверяет допустимость опкодов, исключает I/O, косвенную память и зависимости по регистрам,
памяти и `FLAGS`. Если пара подходит, журнал содержит строку вида:

```text
parallel: MOV R1, #1 || MOV R2, #2
```

Тест `test_superscalar_reduces_ticks_for_independent_code` сравнивает scalar и superscalar выполнение программы
`examples/superscalar.asm`.

### Фрагменты Журнала

Обычная выборка команды переменной длины:

```text
TICK=00014 MPC=015 FETCH_HEADER     PC=0x0000001C ... :: addr=0x00000018 header=0x00000516 operands=5
TICK=00015 MPC=016 FETCH_OPERAND    PC=0x00000020 ... :: operand[1]=0x00000000
TICK=00020 MPC=021 DECODE           PC=0x00000030 ... :: POLY R0, R1, #1, #2, #3 ; super=blocked:control-or-io
TICK=00023 MPC=024 CISC_POLY_EVALUATE PC=0x00000030 ... :: CISC_POLY_EVALUATE: POLY R0, R1, #1, #2, #3
TICK=00026 MPC=027 COMMIT           PC=0x00000030 ... FLAGS=G ... :: POLY R0, R1, #1, #2, #3
```

Memory-mapped stream I/O:

```text
TICK=00025 MPC=026 DECODE           PC=0x00000148 ... :: LOADB R1, [0xFFF0] ; super=blocked:control-or-io
TICK=00050 MPC=051 COMMIT           PC=0x00000168 ... R1=49 ... :: LOADB R1, [0xFFF4]
TICK=02395 MPC=2396 DECODE          PC=0x0000012C ... :: STOREB [0xFFF8], #10 ; super=blocked:control-or-io
```

Параллельное завершение двух независимых инструкций:

```text
TICK=00003 MPC=004 DECODE           PC=0x00000018 ... :: MOV R1, #1 || MOV R2, #2
TICK=00006 MPC=007 COMMIT           PC=0x00000018 ... :: parallel: MOV R1, #1 || MOV R2, #2
```

## Алгоритмы

- `hello.asm` -- вывод `Hello, world!`.
- `cat.asm` -- копирование входного потока в выходной.
- `hello_user_name.asm` -- чтение C-строки и приветствие пользователя.
- `sort.asm` -- чтение массива, сортировка и вывод.
- `uint64.asm` -- демонстрация double precision arithmetic на паре 32-битных слов.
- `prob2.asm` -- Project Euler problem 6.
- `poly.asm` -- демонстрация переменной длины CISC-инструкции `POLY`.
- `superscalar.asm` -- демонстрация параллельного исполнения независимых команд.

## Golden Tests

Каждый каталог `golden/<case>/` содержит:

- `source.asm` -- исходная программа;
- `input.txt` -- входной поток;
- `output.txt` -- ожидаемый выход;
- `program.bin` -- бинарный машинный код;
- `listing.hex` -- адреса, байты и мнемоники;
- `symbols.txt` -- таблица символов;
- `trace.log` -- компактный репрезентативный журнал микротактов;
- `metadata.txt` -- исходник, число тактов, число инструкций и причина остановки.

Полные журналы сохраняются в `build/*.log`. Это позволяет держать golden tests читаемыми, но не терять полный след
выполнения.

## Проверки

Основной набор тестов проверяет:

- корректность обязательных программ;
- макросы, `.org` и условную компиляцию;
- CISC-доступ к памяти за одну арифметическую команду;
- переменную длину `POLY`;
- точный вывод `uint64`, включая перенос из младшего слова;
- возможность остановки на произвольном микротакте;
- актуальность `golden/` и `build/` относительно текущих исходников.

CI запускает форматирование, `ruff`, `mypy`, генерацию golden-артефактов, `unittest` и `pytest`.
