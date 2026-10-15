# 6502E — An Enhanced 6502 CPU

Design specification, draft 0.3

The 6502E is a superset of the NMOS 6502. It adds:

- a second 8-bit accumulator, **B**
- a 16-bit accumulator, **D**, made from A and B together
- 16-bit index registers, **X** and **Y**
- a movable zero page, set by the 8-bit **Z** register

On reset the 6502E runs code that uses only documented 6502 instructions,
unmodified and with the same timing. The 64 opcodes in columns `$x3`, `$x7`,
`$xB`, and `$xF`, which are undocumented on the NMOS 6502, become single-byte B
versions of the A instructions. Every other B instruction also has a
single-byte opcode, taken from NMOS NOP and JAM slots (§3.2). The 16-bit and
extended instructions are reached through two prefixes, which also occupy JAM
slots. A JAM opcode locks up a real 6502, so no working program uses one.

---

## 1. Design principles

1. **Compatibility with documented code.** Every documented NMOS opcode keeps
   its meaning, length, and cycle count. The undocumented opcodes in columns
   `$x3/$x7/$xB/$xF` (SLO, RLA, SRE, RRA, SAX, LAX, DCP, ISC, ANC, ALR, ARR,
   SBX, and the rest) are given up so that B gets full-speed single-byte
   instructions. Software that relies on those opcodes, such as some C64 demos
   and games, will not run. This applies in both modes: there is no
   emulation-mode fallback to the NMOS behaviour, so B is always available.
   Elsewhere, the eight undocumented NOPs listed in §3.2 and five of the JAM
   slots are reused. All other undocumented opcodes keep their NMOS
   behaviour.
2. **The instruction stream never depends on the mode.** The length of an
   instruction is always known from its opcode bytes alone. The 65816 does
   not have this property: there, the length of `LDA #` depends on the M flag.
   On the 6502E, a 16-bit immediate always comes from an explicit prefix, so
   assemblers and disassemblers never need to track processor state.
3. **The mode affects only register width.** The E (emulation) bit decides
   whether X and Y are 8 or 16 bits wide, and which interrupt vectors are
   used. It changes nothing else.
4. **New features cost nothing until used.** B, D, and Z work in both modes.
   Z resets to `$00`, so legacy code sees zero page at `$0000` as usual.

---

## 2. Programmer's model

```
 15            8 7             0
+---------------+---------------+
|       B       |       A       |   D  (16-bit accumulator = B:A)
+---------------+---------------+
|            X (16)             |   X  (high byte is forced to 0 when E=1)
+-------------------------------+
|            Y (16)             |   Y  (high byte is forced to 0 when E=1)
+---------------+---------------+
                |       Z       |   Z  zero-page base: page Z, i.e. $ZZ00-$ZZFF
                +---------------+
                |      SP       |   stack pointer, stack is in page $01 (unchanged)
                +---------------+
|              PC               |
+-------------------------------+
                |N V - B D I Z C|   P  status register (unchanged)
                +---------------+
                              [E]   hidden emulation bit, swapped with C by XCE
```

### 2.1 Why D = B:A (A is the low byte)

The 6502 is little-endian, and A is the register 8-bit code already works
with. Putting A in the low byte of D has two benefits:

- After a 16-bit operation, A already holds the low byte, so 8-bit code can
  continue with no transfer.
- `STD addr` stores A at `addr` and B at `addr+1`, which is the normal 6502
  pointer and word layout.

The 65816 orders its C accumulator the same way. The 6809 does the opposite
(D = A:B, A high), because it is big-endian.

### 2.2 The Z register (movable zero page)

Every zero-page access, including direct, indexed, and indirect pointer
fetches, uses page `Z` instead of page `$00`:

```
effective zp address = (Z << 8) | zp_offset
```

Z is a page number, not a full 16-bit offset as on the 65816. Because only the
high byte of the address changes, the hardware needs a mux, not an adder, and
zero-page instructions keep their 6502 cycle counts. The 65816 adds a cycle
whenever the low byte of its D register is non-zero; this design never does.

Uses:
- each task or interrupt level gets its own zero page, so a context switch
  only has to change Z
- library code can be given a private page of "registers"
- the I/O area can be mapped as zero page, giving short, fast instructions for
  hardware registers

The stack stays in page `$01`. If Z is set to `$01`, zero page and the stack
overlap. This is legal, and the programmer is responsible for it.

> Naming note: the status register already has a Z (zero) flag. In mnemonics
> and documentation, "Z" alone means the register. The flag is always written
> "the Z flag" or `P.Z`.

### 2.3 The E bit and native mode

| | E = 1 (emulation, the reset state) | E = 0 (native) |
|---|---|---|
| X, Y width | 8-bit (high bytes held at `$00`) | 16-bit |
| zp,X / zp,Y / (zp,X) / (zp),Y pointer wrap | wraps within page Z, as on the 6502 | no wrap; carries into the next page |
| `JMP (abs)` page-boundary bug | kept | fixed |
| Interrupt vectors | `$FFFA` / `$FFFC` / `$FFFE` | native vectors (§6) |
| B, D, Z, and new instructions | available | available |

Switching modes: `CLC` then `XCE` enters native mode. `SEC` then `XCE` returns
to emulation mode, which clears the high bytes of X and Y. XCE leaves the old
value of E in C, so code can test which mode it was called in.

---

## 3. Opcode encoding

### 3.1 Direct B instructions (columns `$x3 $x7 $xB $xF`)

The 6502's main ALU group has opcodes of the form `aaa bbb 01`. Here `aaa`
selects the operation (ORA, AND, EOR, ADC, STA, LDA, CMP, SBC) and `bbb`
selects the addressing mode. On the NMOS 6502, the matching `aaa bbb 11`
opcodes are undocumented. On the 6502E they are the same operations with
**B** in place of A:

```
opcode = aaa bbb 01   ->  operation on A
opcode = aaa bbb 11   ->  same operation on B   (bit 1 selects the accumulator)
```

This adds the value 2 to the A opcode: `LDA #` is `$A9`, so `LDB #` is `$AB`.
Each B instruction has the same length, cycle count, page-crossing penalty,
and flag behaviour as its A counterpart, and needs no prefix.

| | (zp,X) | zp | #imm | abs | (zp),Y | zp,X | abs,Y | abs,X |
|---|---|---|---|---|---|---|---|---|
| `ORB`  | `03` | `07` | `0B` | `0F` | `13` | `17` | `1B` | `1F` |
| `ANDB` | `23` | `27` | `2B` | `2F` | `33` | `37` | `3B` | `3F` |
| `EORB` | `43` | `47` | `4B` | `4F` | `53` | `57` | `5B` | `5F` |
| `ADCB` | `63` | `67` | `6B` | `6F` | `73` | `77` | `7B` | `7F` |
| `STB`  | `83` | `87` | *`8B`* | `8F` | `93` | `97` | `9B` | `9F` |
| `LDB`  | `A3` | `A7` | `AB` | `AF` | `B3` | `B7` | `BB` | `BF` |
| `CMPB` | `C3` | `C7` | `CB` | `CF` | `D3` | `D7` | `DB` | `DF` |
| `SBCB` | `E3` | `E7` | `EB` | `EF` | `F3` | `F7` | `FB` | `FF` |

A store to an immediate operand is meaningless (the A-side `$89` is
undocumented too). `$8B` is therefore used for `TXB` (§3.2), next to `TXA`
at `$8A`.

That gives 63 B instructions in this column. Prefixes are not allowed on
them: WX in front of a `$x3/$x7/$xB/$xF` opcode is reserved.

### 3.2 The other B instructions

Every remaining instruction that uses A also gets a single-byte B opcode, so
B never needs a prefix. Where the opcode in the `+$10` position is free, the
B form goes there, directly below the A form in the opcode map. That
position was an NMOS NOP with the same instruction length, so the length rule
still holds.

| A form | B form | Mnemonic | Previous NMOS use | Bytes | Cycles |
|---|---|---|---|---|---|
| `ASL A` `$0A` | `$1A` | `ASLB` | NOP | 1 | 2 |
| `ROL A` `$2A` | `$3A` | `ROLB` | NOP | 1 | 2 |
| `LSR A` `$4A` | `$5A` | `LSRB` | NOP | 1 | 2 |
| `ROR A` `$6A` | `$7A` | `RORB` | NOP | 1 | 2 |
| `BIT zp` `$24` | `$34` | `BITB zp` | NOP zp,X | 2 | 3 |
| `BIT abs` `$2C` | `$3C` | `BITB abs` | NOP abs,X | 3 | 4 |
| `PHA` `$48` | `$DA` | `PHB` | NOP | 1 | 3 |
| `PLA` `$68` | `$FA` | `PLB` | NOP | 1 | 4 |
| `TXA` `$8A` | `$8B` | `TXB` | ANE #imm | 1 | 2 |
| `TYA` `$98` | `$92` | `TYB` | JAM | 1 | 2 |
| `TAX` `$AA` | `$B2` | `TBX` | JAM | 1 | 2 |
| `TAY` `$A8` | `$D2` | `TBY` | JAM | 1 | 2 |

The `+$10` slots for `PHA`, `PLA`, and the transfers are already used by
documented instructions (`CLI`, `SEI`, `TXS`, `TSX`, `CLV`). Those B forms
therefore go to the free NOP slots `$DA`/`$FA`, to `$8B`, and to JAM slots.
`TBX` and `TBY` zero-extend B into X/Y in native mode. `TXB` and `TYB` copy
the low byte. Flags are the same as for the A forms.

### 3.3 Prefixes

The NMOS JAM opcodes are `$02 $12 $22 $32 $42 $52 $62 $72 $92 $B2 $D2 $F2`.
Three of them hold B transfers (§3.2), two become prefixes, and the rest are
reserved.

| Prefix | Name | Effect on the following opcode |
|---|---|---|
| `$12` | **WX** (wide) | Makes the operation 16-bit: A becomes D, X/Y memory operands become 16-bit, and memory read-modify-write becomes 16-bit |
| `$22` | **EX** (extended) | The next byte is an opcode from the extended page (§5) |
| `$02 $32 $42 $52 $62 $72 $F2` | — | Reserved, and still JAM. Possible future uses: bank prefix, second extended page |

Rules:
- Each prefix adds 1 byte and 1 cycle.
- WX combined with EX is reserved. Extended-page instructions choose their
  own width (§5).
- A prefix in front of an opcode it does not apply to is reserved. The intent
  is that this raises an illegal-opcode trap on a future revision, so it must
  not be treated as a NOP.
- An interrupt is never taken between a prefix and the opcode it modifies.

### 3.4 Opcodes WX ($12) applies to

| Group | Effect | Mnemonics |
|---|---|---|
| Accumulator ALU, all modes | Operates on D. An immediate operand is 16-bit. A memory operand is the 16-bit little-endian word at `ea`, `ea+1` | `LDD STD ADCD SBCD ANDD ORD EORD CMPD BITD` |
| Accumulator shifts | 16-bit shift or rotate of D | `ASLD LSRD ROLD RORD` |
| Memory read-modify-write | 16-bit read-modify-write of the word at `ea` | `INC.W DEC.W ASL.W LSR.W ROL.W ROR.W` |
| X/Y load, store, compare | 16-bit operand. `LDX.W #$1234` is 3 bytes plus the prefix | `LDX.W LDY.W STX.W STY.W CPX.W CPY.W` |
| Transfers | `TAX`→`TDX`, `TAY`→`TDY`, `TXA`→`TXD`, `TYA`→`TYD` (all 16-bit) | |
| Stack | `PHA`→`PHD` (pushes B, then A), `PLA`→`PLD` | |

Without WX, the X/Y load, store, and compare instructions keep their 8-bit
operands. In native mode an 8-bit operand is zero-extended: `LDX #$10` sets
X = `$0010`, and `CPX #$10` compares X with `$0010`. `STX` without WX stores
only the low byte. `INX`, `DEX`, `INY`, and `DEY` always act on the full width
of the register in the current mode.

### 3.5 Flags for 16-bit operations

- N is bit 15 of the result. The Z flag is set when all 16 bits are zero.
- C is the carry or borrow out of bit 15.
- V is signed 16-bit overflow. For `BITD`, N and V take bits 15 and 14 of the
  memory word.
- When D = 1, `ADCD` and `SBCD` do 4-digit BCD arithmetic.
- The same rules apply to 16-bit X and Y in native mode, for `INX`, `CPX`,
  `TXD`, and the rest.

---

## 4. Addressing modes

The addressing modes are the same as the 6502's. Only the address calculation
changes:

| Mode | Emulation (E=1) | Native (E=0) |
|---|---|---|
| `zp` | `Z:zp` | `Z:zp` |
| `zp,X` | `Z:((zp+X) & $FF)` | `(Z:zp + X) & $FFFF` |
| `(zp,X)` | pointer at `Z:((zp+X)&$FF)` and the next byte, wrapping in the page | pointer at `Z:zp + X` and `+1`, no wrap |
| `(zp),Y` | pointer at `Z:zp` and `Z:((zp+1)&$FF)`, then add Y | pointer at `Z:zp` and `Z:zp+1`, then add 16-bit Y |
| `abs,X` / `abs,Y` | `abs + X` | `abs + X` (X is 16-bit) |

With 16-bit Y, `(zp),Y` can reach the whole 64 KB from one pointer, so long
copy loops no longer need an outer loop that steps the pointer's high byte.
The page-crossing penalty is the same as on the 6502: one cycle when
`ea` and `base` are in different pages.

---

## 5. Extended page (`$22 xx`)

Where a 6502-family chip already has an equivalent instruction, the second
byte matches that chip's opcode (65C02 or 65816), to make it easier to
remember.

| Encoding | Mnemonic | Operation | Flags | Cycles |
|---|---|---|---|---|
| `$22 03` | `TAB` | B ← A | N Z | 3 |
| `$22 13` | `TBA` | A ← B | N Z | 3 |
| `$22 EB` | `XAB` | swap A and B (65816 `XBA` slot) | N Z (from new A) | 4 |
| `$22 33` | `SEX` | sign-extend A into D: B ← (A.7 ? `$FF` : `$00`) | N Z (from D) | 3 |
| `$22 43` | `MUL` | D ← A × B, unsigned | Z (from D), C ← bit 7 of the result (for rounding, as on the 6809) | ≈ 11 |
| `$22 0B` | `TAZ` | Z ← A | — | 3 |
| `$22 1B` | `TZA` | A ← Z | N Z | 3 |
| `$22 2B nn` | `LDZ #nn` | Z ← nn | — | 3 |
| `$22 3B` | `PHZ` | push Z | — | 4 |
| `$22 4B` | `PLZ` | pull Z | — | 5 |
| `$22 DA` | `PHX` | push X (high byte first in native mode) | — | 4 / 5 |
| `$22 FA` | `PLX` | pull X | N Z | 5 / 6 |
| `$22 5A` | `PHY` | push Y | — | 4 / 5 |
| `$22 7A` | `PLY` | pull Y | N Z | 5 / 6 |
| `$22 9B` | `TXY` | Y ← X (full width) | N Z | 3 |
| `$22 BB` | `TYX` | X ← Y (full width) | N Z | 3 |
| `$22 3A` | `ABX` | X ← X + zero-extended B (as on the 6809) | — | 3 |
| `$22 1A` | `ADX` | X ← X + D, modulo 2^width | — | 3 |
| `$22 FB` | `XCE` | swap C and E | C | 3 |

All other `$22 xx` codes are reserved.

Candidates for later revisions, with no encoding assigned yet: 65C02 extras
(`BRA`, `STZ`, `INC A`, `TRB`/`TSB`), 16-bit relative branches, `DIV`, and a
16-bit stack pointer.

---

## 6. Interrupts and reset

### Reset
E = 1, Z = `$00`, high bytes of X/Y = `$00`, I = 1, D (decimal flag) undefined
(as on NMOS). B is undefined. The CPU fetches the reset vector from `$FFFC`.

### In emulation mode (E = 1)
The CPU behaves exactly as a 6502: it pushes PCH, PCL, and P, and uses the
vectors at `$FFFA` (NMI) and `$FFFE` (IRQ/BRK). Z is **not** changed or saved.
Legacy ROM handlers therefore keep working, as long as the interrupted code
has left Z at `$00`.

### In native mode (E = 0)
The handler cannot know the state of the interrupted code, so the CPU does
more on entry:

1. Push PCH, PCL, **Z**, P (one extra cycle compared with the 6502).
2. Set Z ← `$00`, so the handler always sees the system zero page.
3. Set I and clear D (65C02 behaviour).
4. Fetch the vector from the native table:

| Vector | Address |
|---|---|
| Native BRK | `$FFE6` |
| Native NMI | `$FFEA` |
| Native IRQ | `$FFEE` |

`RTI` in native mode pulls P, then Z, then PCL and PCH.

The handler must save any of B, X, and Y that it uses: `PHB`, `PHX`, `PHY`.
Separate native vectors are needed because a legacy handler that saved X with
`TXA`/`PHA` would lose the high byte of X.

---

## 7. Examples

### 7.1 Copying a block of up to 64 KB

```asm
        clc
        xce                 ; native mode: X and Y are 16-bit
        ldy.w #0
loop:   lda (src),y         ; 16-bit Y: no page stepping
        sta (dst),y
        iny
        cpy.w #LEN
        bne loop
```

The equivalent 6502 code needs an outer loop that increments `src+1` and
`dst+1` and counts pages.

### 7.2 Adding two 16-bit numbers

```asm
        ; 6502: 13 bytes, 20 cycles (zp)
        clc
        lda a_lo
        adc b_lo
        sta r_lo
        lda a_hi
        adc b_hi
        sta r_hi

        ; 6502E: 10 bytes, 17 cycles (zp)
        clc
        ldd a               ; $12 A5 zz
        adcd b              ; $12 65 zz
        std r               ; $12 85 zz
```

### 7.3 8×8 multiply

```asm
        lda #23
        ldb #11             ; $AB 0B
        mul                 ; D = 253
        std result
```

### 7.4 Per-task zero page

```asm
switch: ; X = index of the next task
        phz                 ; save the current task's zero-page base
        ...                 ; save SP and the other registers
        lda task_zp,x
        taz                 ; the new task's zero page is now live
```

---

## 8. Implementation notes

- **Register file:** add B (8 bits), the high bytes XH and YH (8 bits each),
  Z (8 bits), and the E flip-flop. In emulation mode, XH and YH are cleared and
  held at zero.
- **Accumulator select:** for the ALU group (`IR[0] = 1`), opcode bit `IR[1]`
  chooses A (0) or B (1). The rest of the decode for `$x3/$x7/$xB/$xF` is the
  same as for `$x1/$x5/$x9/$xD`, so the direct B instructions cost one mux on
  the accumulator bus and no new timing states. The twelve B opcodes in §3.2
  reuse the timing of their A forms and set the same accumulator-select
  line.
- **Prefix latches:** WIDE and EXT are set by the prefix fetch and cleared at
  the next opcode fetch. While WIDE is set, the decoder inserts a second
  ALU pass that handles the high byte (B, XH, or YH, or `ea+1`) using the
  carry from the first pass.
- **Zero-page high-byte mux:** wherever the 6502 forces ADH to `$00`, drive
  ADH from Z instead. The native-mode no-wrap behaviour lets the carry from the
  ADL adder ripple into ADH. That path already exists for absolute indexed
  addressing.
- **ALU:** stays 8-bit. 16-bit operations take two passes, at one extra cycle
  per extra byte, which keeps the core small. `MUL` uses an 8-step shift-add
  sequence through the existing ALU.
- **Verification target:** in emulation mode with Z = `$00`, the core should
  pass the Klaus Dormann 6502 functional test cycle for cycle. The Wolfgang
  Lorenz suite applies only to its documented-opcode tests, because the
  `$x3/$x7/$xB/$xF` columns now hold the B instructions.

---

## 9. Open questions

1. **Z granularity.** Z is currently a page number (fast). A full 16-bit Z,
   like the 65816 D register, would allow any alignment but adds an adder and
   sometimes a cycle.
2. **Stack.** Should native mode have a 16-bit SP, or an "S page" register
   like Z? With 16-bit indices, a 256-byte stack may become the next limit.
3. **Address space.** Is 64 KB enough, or should a reserved prefix (for
   example `$32`) select a bank register for long addressing?
