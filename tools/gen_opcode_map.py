#!/usr/bin/env python3
"""Generate the 6502E opcode maps (docs/6502E-opcode-map.md).

The opcode tables below are the single source of truth for the maps. They
follow docs/6502E-design.md. Run from the repository root:

    python3 tools/gen_opcode_map.py
"""

import os
import sys

# Instruction length in bytes for each addressing mode.
MODE_BYTES = {
    "": 1, "A": 1, "B": 1,
    "#": 2, "zp": 2, "zp,X": 2, "zp,Y": 2, "(zp,X)": 2, "(zp),Y": 2, "rel": 2,
    "abs": 3, "abs,X": 3, "abs,Y": 3, "(abs)": 3,
}

# Kinds of entry, used for the legend and for checking.
NMOS = "nmos"         # documented NMOS 6502 instruction, unchanged
UNDOC = "undoc"       # NMOS undocumented opcode, behaviour kept
NEW_B = "b"           # new direct B instruction
PREFIX = "prefix"     # 6502E prefix byte
RESERVED = "reserved" # reserved (still JAM on the base page)
NEW = "new"           # new instruction on a prefixed page


class Op:
    def __init__(self, mnem, mode, cycles, kind, nbytes=None):
        self.mnem = mnem
        self.mode = mode
        self.cycles = cycles
        self.kind = kind
        self.nbytes = MODE_BYTES[mode] if nbytes is None else nbytes


# --------------------------------------------------------------------------
# Base page
# --------------------------------------------------------------------------

# ALU group, aaa bbb 01 (A) and aaa bbb 11 (B). Mode order follows bbb.
ALU_MODES = ["(zp,X)", "zp", "#", "abs", "(zp),Y", "zp,X", "abs,Y", "abs,X"]
ALU_CYCLES = ["6", "3", "2", "4", "5*", "4", "4*", "4*"]
STORE_CYCLES = ["6", "3", None, "4", "6", "4", "5", "5"]
ALU_A = ["ORA", "AND", "EOR", "ADC", "STA", "LDA", "CMP", "SBC"]
ALU_B = ["ORB", "ANDB", "EORB", "ADCB", "STB", "LDB", "CMPB", "SBCB"]

base = {}


def put(table, code, op):
    assert code not in table, "opcode $%02X defined twice" % code
    table[code] = op


for aaa in range(8):
    for bbb in range(8):
        cyc = (STORE_CYCLES if aaa == 4 else ALU_CYCLES)[bbb]
        if cyc is None:
            continue  # STA #, STB #: handled below
        put(base, aaa << 5 | bbb << 2 | 1, Op(ALU_A[aaa], ALU_MODES[bbb], cyc, NMOS))
        put(base, aaa << 5 | bbb << 2 | 3, Op(ALU_B[aaa], ALU_MODES[bbb], cyc, NEW_B))

# Read-modify-write group (cc = 10) and the other documented instructions.
NMOS_OTHER = {
    0x00: ("BRK", "", "7"), 0x08: ("PHP", "", "3"), 0x10: ("BPL", "rel", "2†"),
    0x18: ("CLC", "", "2"), 0x20: ("JSR", "abs", "6"), 0x24: ("BIT", "zp", "3"),
    0x28: ("PLP", "", "4"), 0x2C: ("BIT", "abs", "4"), 0x30: ("BMI", "rel", "2†"),
    0x38: ("SEC", "", "2"), 0x40: ("RTI", "", "6‡"), 0x48: ("PHA", "", "3"),
    0x4C: ("JMP", "abs", "3"), 0x50: ("BVC", "rel", "2†"), 0x58: ("CLI", "", "2"),
    0x60: ("RTS", "", "6"), 0x68: ("PLA", "", "4"), 0x6C: ("JMP", "(abs)", "5"),
    0x70: ("BVS", "rel", "2†"), 0x78: ("SEI", "", "2"), 0x84: ("STY", "zp", "3"),
    0x86: ("STX", "zp", "3"), 0x88: ("DEY", "", "2"), 0x8A: ("TXA", "", "2"),
    0x8C: ("STY", "abs", "4"), 0x8E: ("STX", "abs", "4"), 0x90: ("BCC", "rel", "2†"),
    0x94: ("STY", "zp,X", "4"), 0x96: ("STX", "zp,Y", "4"), 0x98: ("TYA", "", "2"),
    0x9A: ("TXS", "", "2"), 0xA0: ("LDY", "#", "2"), 0xA2: ("LDX", "#", "2"),
    0xA4: ("LDY", "zp", "3"), 0xA6: ("LDX", "zp", "3"), 0xA8: ("TAY", "", "2"),
    0xAA: ("TAX", "", "2"), 0xAC: ("LDY", "abs", "4"), 0xAE: ("LDX", "abs", "4"),
    0xB0: ("BCS", "rel", "2†"), 0xB4: ("LDY", "zp,X", "4"), 0xB6: ("LDX", "zp,Y", "4"),
    0xB8: ("CLV", "", "2"), 0xBA: ("TSX", "", "2"), 0xBC: ("LDY", "abs,X", "4*"),
    0xBE: ("LDX", "abs,Y", "4*"), 0xC0: ("CPY", "#", "2"), 0xC4: ("CPY", "zp", "3"),
    0xC8: ("INY", "", "2"), 0xCA: ("DEX", "", "2"), 0xCC: ("CPY", "abs", "4"),
    0xD0: ("BNE", "rel", "2†"), 0xD8: ("CLD", "", "2"), 0xE0: ("CPX", "#", "2"),
    0xE4: ("CPX", "zp", "3"), 0xE8: ("INX", "", "2"), 0xEA: ("NOP", "", "2"),
    0xEC: ("CPX", "abs", "4"), 0xF0: ("BEQ", "rel", "2†"), 0xF8: ("SED", "", "2"),
}
for code, (m, mode, cyc) in NMOS_OTHER.items():
    put(base, code, Op(m, mode, cyc, NMOS))

RMW = {0x00: "ASL", 0x20: "ROL", 0x40: "LSR", 0x60: "ROR", 0xC0: "DEC", 0xE0: "INC"}
for hi, m in RMW.items():
    put(base, hi | 0x06, Op(m, "zp", "5", NMOS))
    put(base, hi | 0x0E, Op(m, "abs", "6", NMOS))
    put(base, hi | 0x16, Op(m, "zp,X", "6", NMOS))
    put(base, hi | 0x1E, Op(m, "abs,X", "7", NMOS))
    if hi < 0x80:
        put(base, hi | 0x0A, Op(m, "A", "2", NMOS))

# Direct B forms of the remaining A instructions (design §3.2).
B_OTHER = {
    0x1A: ("ASLB", "", "2"), 0x3A: ("ROLB", "", "2"), 0x5A: ("LSRB", "", "2"),
    0x7A: ("RORB", "", "2"), 0x34: ("BITB", "zp", "3"), 0x3C: ("BITB", "abs", "4"),
    0xDA: ("PHB", "", "3"), 0xFA: ("PLB", "", "4"), 0x8B: ("TXB", "", "2"),
    0x92: ("TYB", "", "2"), 0xB2: ("TBX", "", "2"), 0xD2: ("TBY", "", "2"),
}
for code, (m, mode, cyc) in B_OTHER.items():
    put(base, code, Op(m, mode, cyc, NEW_B))

# NMOS undocumented opcodes outside the reused slots keep their behaviour.
for code in (0x80, 0x82, 0x89, 0xC2, 0xE2):
    put(base, code, Op("NOP", "#", "2", UNDOC))
for code in (0x04, 0x44, 0x64):
    put(base, code, Op("NOP", "zp", "3", UNDOC))
for code in (0x14, 0x54, 0x74, 0xD4, 0xF4):
    put(base, code, Op("NOP", "zp,X", "4", UNDOC))
put(base, 0x0C, Op("NOP", "abs", "4", UNDOC))
for code in (0x1C, 0x5C, 0x7C, 0xDC, 0xFC):
    put(base, code, Op("NOP", "abs,X", "4*", UNDOC))
put(base, 0x9C, Op("SHY", "abs,X", "5", UNDOC))
put(base, 0x9E, Op("SHX", "abs,Y", "5", UNDOC))

# Prefixes and reserved JAM slots.
put(base, 0x12, Op("WX", "", "+1", PREFIX))
put(base, 0x22, Op("EX", "", "+1", PREFIX))
put(base, 0x32, Op("BP", "", "+1", PREFIX))
for code in (0x02, 0x42, 0x52, 0x62, 0x72, 0xF2):
    put(base, code, Op("—", "", "", RESERVED))

# --------------------------------------------------------------------------
# WX page ($12 xx): 16-bit forms of base-page instructions (design §3.4)
# --------------------------------------------------------------------------

WIDE_NAME = {
    "ORA": "ORD", "AND": "ANDD", "EOR": "EORD", "ADC": "ADCD", "STA": "STD",
    "LDA": "LDD", "CMP": "CMPD", "SBC": "SBCD", "BIT": "BITD",
    "TAX": "TDX", "TAY": "TDY", "TXA": "TXD", "TYA": "TYD",
    "PHA": "PHD", "PLA": "PLD",
}
WIDE_MEM = {"LDX", "LDY", "STX", "STY", "CPX", "CPY",
            "INC", "DEC", "ASL", "LSR", "ROL", "ROR"}
WIDE_RMW = {"INC", "DEC", "ASL", "LSR", "ROL", "ROR"}


def add_cycles(cyc, n):
    star = cyc.endswith("*")
    return str(int(cyc.rstrip("*")) + n) + ("*" if star else "")


wide = {}
for code, op in base.items():
    if op.kind != NMOS:
        continue
    m = op.mnem
    if m in WIDE_NAME:
        name = WIDE_NAME[m]
    elif m in WIDE_MEM:
        if op.mode == "A":
            name = m + "D"  # ASL A -> ASLD
        else:
            name = m + ".W"
    else:
        continue
    extra = 3 if (m in WIDE_RMW and op.mode != "A") else 2
    # Prefix byte, plus a second immediate byte for 16-bit immediates.
    nbytes = op.nbytes + 1 + (1 if op.mode == "#" else 0)
    mode = "" if op.mode == "A" else op.mode
    put(wide, code, Op(name, mode, add_cycles(op.cycles, extra), NEW, nbytes))

# --------------------------------------------------------------------------
# EX page ($22 xx): extended instructions (design §5)
# --------------------------------------------------------------------------

ext = {}
EXT = {
    0x03: ("TAB", "", "3"), 0x13: ("TBA", "", "3"), 0xEB: ("XAB", "", "4"),
    0x33: ("SEX", "", "3"), 0x43: ("MUL", "", "≈11"), 0x0B: ("TAZ", "", "3"),
    0x1B: ("TZA", "", "3"), 0x2B: ("LDZ", "#", "3"), 0x3B: ("PHZ", "", "4"),
    0x4B: ("PLZ", "", "5"), 0xDA: ("PHX", "", "4/5"), 0xFA: ("PLX", "", "5/6"),
    0x5A: ("PHY", "", "4/5"), 0x7A: ("PLY", "", "5/6"), 0x9B: ("TXY", "", "3"),
    0xBB: ("TYX", "", "3"), 0x3A: ("ABX", "", "3"), 0x1A: ("ADX", "", "3"),
    0xFB: ("XCE", "", "3"),
}
for code, (m, mode, cyc) in EXT.items():
    put(ext, code, Op(m, mode, cyc, NEW, MODE_BYTES[mode] + 1))

# --------------------------------------------------------------------------
# BP page ($32 xx): bit operations (design §6)
# --------------------------------------------------------------------------

BIT_OPS = ["BTST", "BSET", "BCLR", "BCHG"]
BIT_MODES = ["A", "B", "zp", "zp,X", "abs", "abs,X", "abs,Y", "(zp),Y"]
BIT_BYTES = [2, 2, 3, 3, 4, 4, 4, 3]
BTST_CYCLES = ["3", "3", "4", "5", "5", "5*", "5*", "6*"]
BRMW_CYCLES = ["3", "3", "6", "7", "7", "8", "8", "9"]

bitp = {}
for o in range(4):
    for m in range(8):
        for n in range(8):
            cyc = (BTST_CYCLES if o == 0 else BRMW_CYCLES)[m]
            put(bitp, o << 6 | m << 3 | n,
                Op(BIT_OPS[o], "#%d,%s" % (n, BIT_MODES[m]), cyc, NEW, BIT_BYTES[m]))

# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------


def cell(op):
    if op is None:
        return ""
    if op.kind == RESERVED:
        return "*res*"
    if op.kind == PREFIX:
        return "**%s**<br>prefix" % op.mnem
    name = op.mnem
    if op.kind in (NEW_B, NEW):
        name = "**%s**" % name
    elif op.kind == UNDOC:
        name = "*%s*" % name
    mode = op.mode.replace("|", "\\|")
    top = name + (" " + mode if mode else "")
    return "%s<br>%d · %s" % (top, op.nbytes, op.cycles)


def grid(table, prefix=""):
    lines = ["| | " + " | ".join("x%X" % lo for lo in range(16)) + " |",
             "|---" * 17 + "|"]
    for hi in range(16):
        row = [cell(table.get(hi << 4 | lo)) for lo in range(16)]
        lines.append("| **%s%Xx** | " % (prefix, hi) + " | ".join(row) + " |")
    return "\n".join(lines)


def count(table, kind):
    return sum(1 for op in table.values() if op.kind == kind)


def main():
    assert len(base) == 256, "base page has %d entries" % len(base)
    assert len(bitp) == 256
    out = []
    w = out.append
    w("# 6502E opcode maps")
    w("")
    w("Generated by `tools/gen_opcode_map.py` from the tables in that script,")
    w("which follow [the design spec](6502E-design.md). Do not edit by hand.")
    w("")
    w("## Legend")
    w("")
    w("Each cell shows the mnemonic and addressing mode, then")
    w("**bytes · cycles**. Byte counts include any prefix byte.")
    w("")
    w("| Marking | Meaning |")
    w("|---|---|")
    w("| `LDA` (plain) | NMOS 6502 instruction, unchanged |")
    w("| **`LDB`** (bold) | New 6502E instruction |")
    w("| *`NOP`* (italic) | NMOS undocumented opcode, behaviour kept |")
    w("| *res* | Reserved. On the base page these still lock up the CPU (JAM) |")
    w("| `*` | +1 cycle if a page boundary is crossed |")
    w("| `†` | Branch: +1 cycle if taken, +1 more if the target is in another page |")
    w("| `‡` | Native mode: +1 cycle (Z is pulled as well) |")
    w("| `a/b` | Emulation mode / native mode (X and Y are 16-bit in native mode) |")
    w("")
    w("Modes: `#` immediate, `zp` zero page (in page Z), `abs` absolute,")
    w("`rel` relative, `A` accumulator. A blank mode means implied.")
    w("")
    w("## Base page")
    w("")
    w("| Kind | Count |")
    w("|---|---|")
    w("| NMOS documented | %d |" % count(base, NMOS))
    w("| New B instructions | %d |" % count(base, NEW_B))
    w("| NMOS undocumented, kept | %d |" % count(base, UNDOC))
    w("| Prefixes (`$12` WX, `$22` EX, `$32` BP) | %d |" % count(base, PREFIX))
    w("| Reserved | %d |" % count(base, RESERVED))
    w("")
    w(grid(base))
    w("")
    w("In native mode `JMP (abs)` does not have the NMOS page-boundary bug.")
    w("Zero-page modes use page Z, and indexed modes use 16-bit X/Y in native")
    w("mode (design §4).")
    w("")
    w("## WX page (`$12 xx`): 16-bit operations")
    w("")
    w("The second byte is a base-page opcode. The result works on D instead of")
    w("A, or on a 16-bit memory word or immediate. %d opcodes are valid; every"
      % len(wide))
    w("empty cell is reserved.")
    w("")
    w("Cycles are the base instruction's count +2 (prefix and the high byte),")
    w("or +3 for memory read-modify-write (prefix, and the high byte read and")
    w("written). A 16-bit immediate is one byte longer.")
    w("")
    w("In emulation mode X and Y stay 8-bit. `LDX.W` and `LDY.W` read both")
    w("bytes but keep the high byte of the register at `$00`, and `STX.W` and")
    w("`STY.W` store `$00` as the high byte.")
    w("")
    w(grid(wide, "$12 "))
    w("")
    w("## EX page (`$22 xx`): extended instructions")
    w("")
    w("%d opcodes are assigned. Every empty cell is reserved." % len(ext))
    w("")
    w(grid(ext, "$22 "))
    w("")
    w("## BP page (`$32 xx`): bit operations")
    w("")
    w("The second byte is `op mode bit` (bits 7–6, 5–3, 2–0). All 256 opcodes")
    w("are used. Each sets the Z flag from the bit's previous value (design §6).")
    w("")
    w("| Rows | Operation |")
    w("|---|---|")
    w("| `$0x`–`$3x` | `BTST` test |")
    w("| `$4x`–`$7x` | `BSET` test and set |")
    w("| `$8x`–`$Bx` | `BCLR` test and clear |")
    w("| `$Cx`–`$Fx` | `BCHG` test and invert |")
    w("")
    w(grid(bitp, "$32 "))
    w("")

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, "docs", "6502E-opcode-map.md")
    with open(path, "w") as f:
        f.write("\n".join(out))
    print("wrote %s" % path)
    print("base: %d nmos, %d B, %d undoc, %d prefix, %d reserved" % (
        count(base, NMOS), count(base, NEW_B), count(base, UNDOC),
        count(base, PREFIX), count(base, RESERVED)))
    print("wx: %d, ex: %d, bp: %d" % (len(wide), len(ext), len(bitp)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
