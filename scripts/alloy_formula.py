"""Parse alloy names such as 'Al0.5CoCrFeNi', '(FeCoNi)86-Al8Ti6' or '(TiZrNbTa)95Mo5' into mole fractions.

parse(name) returns {element: fraction} summing to 1, or None when the name cannot be read with confidence
(e.g. weight-% 'balance' notation like 'Co–33Cr–9W–0.35N–0.01C').
"""
import re

ELEMENTS = {"Al", "Co", "Cr", "Fe", "Ni", "Cu", "Mn", "Ti", "V", "Nb", "Mo", "Zr", "Hf", "Ta", "W", "C", "Mg",
            "Zn", "Si", "Re", "N", "Sc", "Li", "Sn", "Be"}
TOKEN = re.compile(r"\(([^()]*)\)(\d*\.?\d*)|([A-Z][a-z]?)(\d*\.?\d*)")


def _flat(text):
    out = {}
    pos = 0
    for m in re.finditer(r"([A-Z][a-z]?)(\d*\.?\d*)", text):
        if text[pos:m.start()].strip(" -"):
            return None
        el, num = m.group(1), m.group(2)
        if el not in ELEMENTS:
            return None
        out[el] = out.get(el, 0) + (float(num) if num else 1.0)
        pos = m.end()
    if text[pos:].strip(" -"):
        return None
    return out


def parse(name):
    s = name.strip().replace(" ", "")
    if "–" in s or "wt" in s.lower() or "%" in s:
        return None
    total = {}
    pos = 0
    for m in TOKEN.finditer(s):
        if s[pos:m.start()].strip("-"):
            return None
        if m.group(1) is not None:  # parenthesised group, scaled to its multiplier
            inner = _flat(m.group(1))
            if not inner:
                return None
            mult = float(m.group(2)) if m.group(2) else 1.0
            ssum = sum(inner.values())
            for el, v in inner.items():
                total[el] = total.get(el, 0) + v / ssum * mult
        else:
            el, num = m.group(3), m.group(4)
            if el not in ELEMENTS:
                return None
            total[el] = total.get(el, 0) + (float(num) if num else 1.0)
        pos = m.end()
    if s[pos:].strip("-") or not total:
        return None
    z = sum(total.values())
    return {el: v / z for el, v in total.items()}


def key(comp, digits=3):
    """Order-independent identity of a composition, so 'AlCrFeCoNi' and 'AlCoCrFeNi' compare equal."""
    return "|".join(f"{el}{round(v, digits)}" for el, v in sorted(comp.items()) if round(v, digits) > 0)
