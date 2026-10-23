"""Build the presentation as an editable .pptx (opens in PowerPoint and Hancom Show).

Usage: python -I build_pptx.py <img_dir> <out.pptx>
Every text box is measured with the real Malgun Gothic metrics; the script fails if any text would overflow.
"""
import re
import sys
from pathlib import Path

from PIL import Image, ImageFont
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

sys.stdout.reconfigure(encoding="utf-8")
IMG, OUT = Path(sys.argv[1]), Path(sys.argv[2])
FONT = "맑은 고딕"
FONT_FILES = {False: r"C:\Windows\Fonts\malgun.ttf", True: r"C:\Windows\Fonts\malgunbd.ttf"}
LINE = 1.38  # Malgun Gothic line height as a multiple of the font size

INK, INK2, MUTED = "0B0B0B", "52514E", "898781"
ACCENT, ACCENT_DARK, ORANGE = "2A78D6", "1C5CAB", "EB6834"
TINT, WARN_TINT, LINE_C, CARD = "EEF4FC", "FDF0EA", "E1E0D9", "F7F7F5"
GOOD, GOOD_TINT, BAD, BAD_TINT, MID_TINT = "006300", "E6F2E6", "B4441A", "FDF0EA", "F0EFEC"

W, H, MX = 13.333, 7.5, 0.6
CW = W - 2 * MX

prs = Presentation()
prs.slide_width, prs.slide_height = Inches(W), Inches(H)
BLANK = prs.slide_layouts[6]
problems = []
_fonts = {}


def font(size, bold):
    key = (round(size * 4), bold)
    if key not in _fonts:
        _fonts[key] = ImageFont.truetype(FONT_FILES[bold], int(size * 4))  # 4 px per pt for precision
    return _fonts[key]


def rgb(h):
    return RGBColor.from_string(h)


# Malgun Gothic has no U+2212 minus or check marks; swap them for glyphs it has so nothing renders as boxes
GLYPH_FIX = {"−": "–", "✓": "", "✗": ""}


def clean(text):
    for a, b in GLYPH_FIX.items():
        text = text.replace(a, b)
    return text


def parse(text):
    """'plain **bold** c_{i}' -> [(segment, is_bold, is_subscript)]"""
    out = []
    for i, part in enumerate(re.split(r"\*\*", clean(text))):
        for j, piece in enumerate(re.split(r"_\{([^}]*)\}", part)):
            if piece:
                out.append((piece, i % 2 == 1, j % 2 == 1))
    return out


def plain(text):
    return re.sub(r"_\{([^}]*)\}", r"\1", clean(text).replace("**", ""))


def text_lines(text, size, width_in, bold=False):
    """Number of wrapped lines for one paragraph, measured with the real font."""
    width_px = width_in * 72 * 4
    lines = 0
    for hard in plain(text).split("\n"):
        line_w, n = 0.0, 1
        for tok in re.findall(r"\S+\s*|\s+", hard):
            tw = font(size, bold).getlength(tok)
            if line_w + tw > width_px and line_w > 0:
                n += 1
                line_w = 0
                if tw > width_px:  # a single long token wraps by characters
                    n += int(tw // width_px)
                    tw = tw % width_px
            line_w += tw
        lines += n
    return lines


def check_fit(label, paras, width_in, height_in):
    """paras: list of (text, size, bold, space_after_pt)."""
    total = 0.0
    for text, size, bold, after, pw in paras:
        total += text_lines(text, size, pw, bold) * size * LINE + after
    need = total / 72
    if need > height_in + 0.01:
        problems.append(f"{label}: needs {need:.2f}in, box {height_in:.2f}in")


def set_bullet(p, char="•", color=ACCENT):
    pPr = p._p.get_or_add_pPr()
    pPr.set("marL", str(Emu(Inches(0.26))))
    pPr.set("indent", str(-Emu(Inches(0.26))))
    for tag in ("a:buClr", "a:buFont", "a:buChar", "a:buNone"):
        for el in pPr.findall(qn(tag)):
            pPr.remove(el)
    clr = pPr.makeelement(qn("a:buClr"), {})
    s = clr.makeelement(qn("a:srgbClr"), {"val": color})
    clr.append(s)
    pPr.append(clr)
    pPr.append(pPr.makeelement(qn("a:buChar"), {"char": char}))


def write_paras(tf, items, size, color, label, width_in, height_in, align=PP_ALIGN.LEFT, after=6, bold=False):
    """items: list of str | dict(text, size, color, bold, bullet, after)."""
    tf.word_wrap = True
    measure = []
    for i, it in enumerate(items):
        it = {"text": it} if isinstance(it, str) else it
        sz, col = it.get("size", size), it.get("color", color)
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = it.get("align", align)
        p.space_after = Pt(it.get("after", after))
        for seg, b, sub in parse(it["text"]):
            r = p.add_run()
            r.text = seg
            r.font.size, r.font.name = Pt(sz), FONT
            r.font.bold = b or it.get("bold", bold)
            r.font.color.rgb = rgb(INK if b and col in (INK2, MUTED) else col)
            if sub:
                r._r.get_or_add_rPr().set("baseline", "-25000")
        rpr_ea(p)
        bw = width_in
        if it.get("bullet"):
            set_bullet(p)
            bw -= 0.26
        elif it.get("indent"):
            p._p.get_or_add_pPr().set("marL", str(Emu(Inches(0.26))))
            bw -= 0.26
        measure.append((it["text"], sz, it.get("bold", bold), it.get("after", after), bw))
    check_fit(label, measure, width_in, height_in)


def rpr_ea(p):
    """Set the East-Asian font on every run so Korean text uses Malgun Gothic in all viewers."""
    for r in p.runs:
        rPr = r._r.get_or_add_rPr()
        for tag in ("a:ea", "a:cs"):
            el = rPr.find(qn(tag))
            if el is None:
                el = rPr.makeelement(qn(tag), {})
                rPr.append(el)
            el.set("typeface", FONT)


def textbox(slide, x, y, w, h, items, size=16, color=INK2, label="", anchor=MSO_ANCHOR.TOP, **kw):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.margin_left = tf.margin_right = Inches(0.04)
    tf.margin_top = tf.margin_bottom = Inches(0.02)
    tf.vertical_anchor = anchor
    write_paras(tf, items, size, color, label or items_label(items), w - 0.08, h - 0.04, **kw)
    return tb


def items_label(items):
    first = items[0] if isinstance(items[0], str) else items[0]["text"]
    return first.replace("**", "")[:24]


def card(slide, x, y, w, h, items, fill=TINT, size=15, color=INK2, label="", pad=0.16, anchor=MSO_ANCHOR.MIDDLE, **kw):
    shp = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    shp.adjustments[0] = 0.08
    shp.fill.solid()
    shp.fill.fore_color.rgb = rgb(fill)
    shp.line.fill.background()
    shp.shadow.inherit = False
    tf = shp.text_frame
    tf.margin_left = tf.margin_right = Inches(pad)
    tf.margin_top = tf.margin_bottom = Inches(pad * 0.7)
    tf.vertical_anchor = anchor
    write_paras(tf, items, size, color, label or items_label(items), w - 2 * pad, h - 1.4 * pad, **kw)
    return shp


def outline_card(slide, x, y, w, h, items, **kw):
    shp = card(slide, x, y, w, h, items, fill="FFFFFF", **kw)
    shp.line.color.rgb = rgb(LINE_C)
    shp.line.width = Pt(1)
    return shp


def image(slide, name, x, y, w, h, align="center"):
    path = IMG / f"{name}.png"
    iw, ih = Image.open(path).size
    k = min(w / iw, h / ih)
    pw, ph = iw * k, ih * k
    px = x + (w - pw) / 2 if align == "center" else x
    pic = slide.shapes.add_picture(str(path), Inches(px), Inches(y + (h - ph) / 2), Inches(pw), Inches(ph))
    return pic


def table(slide, x, y, w, col_w, rows, size=12, row_h=0.36, header_size=11, label="table", num_cols=(), tags=None):
    nrows, ncols = len(rows), len(rows[0])
    scale = w / sum(col_w)
    col_w = [c * scale for c in col_w]
    gt = slide.shapes.add_table(nrows, ncols, Inches(x), Inches(y), Inches(w), Inches(row_h * nrows)).table
    tblPr = gt._tbl.tblPr
    tblPr.set("firstRow", "0")
    tblPr.set("bandRow", "0")
    style = tblPr.find(qn("a:tableStyleId"))
    if style is None:
        style = tblPr.makeelement(qn("a:tableStyleId"), {})
        tblPr.append(style)
    style.text = "{5940675A-B579-460E-94D1-54222C63F5DA}"  # "No Style, Table Grid" -> we restyle cells
    for j, cw in enumerate(col_w):
        gt.columns[j].width = Inches(cw)
    tags = tags or {}
    for i, row in enumerate(rows):
        gt.rows[i].height = Inches(row_h)
        for j, val in enumerate(row):
            cell = gt.cell(i, j)
            cell.margin_left = cell.margin_right = Inches(0.07)
            cell.margin_top = cell.margin_bottom = Inches(0.03)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.fill.solid()
            cell.fill.fore_color.rgb = rgb("FFFFFF" if i else "F0EFEC")
            tf = cell.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            p.alignment = PP_ALIGN.RIGHT if j in num_cols else PP_ALIGN.LEFT
            sz = header_size if i == 0 else size
            tag = tags.get((i, j))
            if tag:
                kind, word = tag
                r = p.add_run()
                r.text = word
                r.font.bold = True
                r.font.size, r.font.name = Pt(sz), FONT
                r.font.color.rgb = rgb({"ok": GOOD, "no": BAD, "mid": INK2}[kind])
                val = "  " + val
            for seg, b, sub in parse(str(val)):
                r = p.add_run()
                r.text = seg
                r.font.size, r.font.name = Pt(sz), FONT
                r.font.bold = b or i == 0 or (j == 0 and i > 0)
                r.font.color.rgb = rgb(MUTED if i == 0 else (INK if (b or j == 0) else INK2))
                if sub:
                    r._r.get_or_add_rPr().set("baseline", "-25000")
            rpr_ea(p)
            _borders(cell)
            need = text_lines(str(val) + (tag[1] + "  " if tag else ""), sz, col_w[j] - 0.14,
                              i == 0 or j == 0) * sz * LINE / 72 + 0.06
            if need > row_h + 0.01:
                problems.append(f"{label} r{i}c{j} '{str(val)[:18]}': needs {need:.2f}in, row {row_h:.2f}in")
    return gt


def _borders(cell):
    tcPr = cell._tc.get_or_add_tcPr()
    for side in ("a:lnL", "a:lnR", "a:lnT", "a:lnB"):
        ln = tcPr.makeelement(qn(side), {"w": str(Emu(Pt(0.75))) if side == "a:lnB" else "0"})
        if side == "a:lnB":
            fill = ln.makeelement(qn("a:solidFill"), {})
            fill.append(fill.makeelement(qn("a:srgbClr"), {"val": LINE_C}))
            ln.append(fill)
        else:
            ln.append(ln.makeelement(qn("a:noFill"), {}))
        tcPr.append(ln)


def new_slide(kicker, title, week=None, notes=None):
    s = prs.slides.add_slide(BLANK)
    bg = s.background.fill
    bg.solid()
    bg.fore_color.rgb = rgb("FFFFFF")
    k = kicker + (f"   ·   {week}" if week else "")
    textbox(s, MX, 0.34, CW, 0.38, [{"text": k, "bold": True}], size=13, color=ACCENT, label="kicker")
    textbox(s, MX, 0.70, CW, 0.68, [{"text": title, "bold": True}], size=27, color=INK, label=f"title:{title[:14]}")
    n = len(prs.slides)
    textbox(s, W - MX - 1.0, H - 0.46, 1.0, 0.34, [{"text": f"{n}", "align": PP_ALIGN.RIGHT}], size=11, color=MUTED,
            label="pageno")
    if notes:
        s.notes_slide.notes_text_frame.text = notes
    return s


def note(slide, text, y=H - 0.78, h=0.42):
    textbox(slide, MX, y, CW - 1.2, h, [text], size=11, color=MUTED, label="note")


TOP = 1.5  # content starts below the title


def rect(slide, x, y, w, h, fill, text="", size=12, color=INK, bold=True, rounded=True):
    shp = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE if rounded else MSO_SHAPE.RECTANGLE,
                                 Inches(x), Inches(y), Inches(w), Inches(h))
    if rounded:
        shp.adjustments[0] = 0.15
    shp.fill.solid()
    shp.fill.fore_color.rgb = rgb(fill)
    shp.line.fill.background()
    shp.shadow.inherit = False
    if text:
        tf = shp.text_frame
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = Inches(0.02)
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        write_paras(tf, [{"text": t, "align": PP_ALIGN.CENTER, "after": 0, "bold": bold if k == 0 else False,
                          "size": size if k == 0 else size - 2}
                         for k, t in enumerate(text.split("\n"))], size, color, f"rect:{text[:10]}", w - 0.04, h - 0.04)
    return shp


# ---------------- 1. Title ----------------
s = prs.slides.add_slide(BLANK)
s.background.fill.solid()
s.background.fill.fore_color.rgb = rgb("12305A")
textbox(s, 0.9, 1.3, 11.5, 0.46, [{"text": "데이터리터러시의이해 · 데이터 분석 발표", "bold": True}], size=15, color="9EC5F4")
textbox(s, 0.9, 1.85, 11.5, 1.9, [{"text": "고엔트로피합금의 결정 구조,", "bold": True, "after": 0},
                                  {"text": "데이터로 예측할 수 있을까?", "bold": True}], size=44, color="FFFFFF")
textbox(s, 0.9, 3.95, 11.3, 0.9, ["원자료 1,361행을 진단·검증·정제해 합금 258종으로 만들고, 기술통계와 머신러닝으로 상(Phase)을 분류하다"],
        size=20, color="CDE2FB")
x = 0.9
for f in ["수집 설계", "진단", "정제 로그", "기술통계", "예측 모델", "해석(SHAP)"]:
    card(s, x, 5.2, 1.62, 0.56, [{"text": f, "bold": True, "align": PP_ALIGN.CENTER}], fill="1C4A80", size=15,
         color="FFFFFF", pad=0.08)
    x += 1.62 + 0.22
textbox(s, 0.9, 6.25, 11.5, 0.6, ["데이터: Machaka (2021), Data in Brief 38, 107346 · 분석: Python + Claude Code(AI 에이전트)"],
        size=13, color="9EC5F4")
s.notes_slide.notes_text_frame.text = "주제와 분석 흐름 소개. 수업에서 배운 순서(수집 설계 → 진단 → 정제 → 기술통계)를 그대로 따랐고, 마지막에 SHAP으로 모델을 해석했다."

# ---------------- 2. Background ----------------
s = new_slide("배경과 질문", "고엔트로피합금(HEA)과 ‘상’",
              notes="HEA는 여러 원소를 비슷한 비율로 섞은 합금. 상(결정 구조)이 성질을 좌우하는데, 확인하려면 실험이 필요하다.")
textbox(s, MX, TOP + 0.1, 5.9, 4.9, [
    {"text": "기존 강철: **철(Fe) 하나가 주원소**, 나머지는 소량 첨가", "bullet": True, "after": 10},
    {"text": "HEA: **4~5종 이상의 원소를 비슷한 비율**로 섞은 합금 (예: CoCrFeMnNi)", "bullet": True, "after": 10},
    {"text": "성질을 좌우하는 것은 **결정 구조(상)**", "bullet": True, "after": 4},
    {"text": "BCC: 단단하지만 깨지기 쉬움", "size": 15, "after": 2, "indent": True},
    {"text": "FCC: 잘 늘어나고 질김", "size": 15, "after": 2, "indent": True},
    {"text": "금속간화합물(Im): 매우 단단하지만 취성", "size": 15, "indent": True},
], size=18, label="bg-left")
cx = MX + 6.3
card(s, cx, TOP + 0.1, CW - 6.3, 1.25, ["**문제:** 새 합금의 상을 확인하려면 용해·주조·X선 회절 분석까지 실험이 필요하다."], size=16)
card(s, cx, TOP + 1.55, CW - 6.3, 1.25, ["**분석 질문:** 조성에서 계산되는 열역학 변수만으로, 실험 전에 주조 직후의 상을 맞힐 수 있는가?"], size=16)
card(s, cx, TOP + 3.0, CW - 6.3, 1.55, ["**하위 질문:** ① 상마다 변수 분포가 어떻게 다른가(기술통계)  ② 어느 변수가 어느 방향으로 작용하나(SHAP)  ③ 단순 규칙보다 나은가"],
     size=16)

# ---------------- 3. Two forks ----------------
s = new_slide("배경 · 변수 소개", "상은 두 번의 갈림길에서 정해진다",
              notes="갈림길 1: 고르게 섞이나(ΔHmix, δ, Δχ, ΔSmix, 원소 개수). 갈림길 2: 고용체라면 FCC냐 BCC냐(VEC). 마지막에 SHAP으로 모델이 이 구조를 배웠는지 확인한다.")
image(s, "phase_tree", MX, TOP - 0.05, 7.6, 4.9)
table(s, MX + 7.85, TOP, CW - 7.85, [1.15, 2.6], [
    ["변수", "쉬운 뜻"], ["VEC", "원자당 가전자 수 (접착제 양)"], ["ΔHmix", "원소끼리의 친밀도"], ["δ", "원자 크기의 제각각 정도"],
    ["Δχ", "전자 끌어당기는 힘의 차이"], ["ΔSmix", "섞임의 무질서도"], ["원소 개수", "섞인 원소 종류 수"]],
      size=13, row_h=0.44, label="vars")
card(s, MX + 7.85, TOP + 3.35, CW - 7.85, 0.95, ["이 그림이 맞는지 마지막에 **SHAP으로 확인**한다."], size=15)

# ---------------- 4. Collection design ----------------
s = new_slide("수집 설계", "질문 → 조작적 정의 → 변수 → 출처, 이 순서로", "2주차",
              notes="2주차: 데이터를 찾기 전에 질문을 고정하고, 말을 숫자로 바꾸는 조작적 정의를 먼저 적었다. 관측 단위는 조성 1종.")
steps = [("질문", "상을 맞힐 수 있나", "열역학 변수 → 주조 직후의 상"),
         ("조작적 정의", "말을 숫자로", "HEA = ΔSmix ≥ 1R (8.31 J/K·mol)\n상 = 주조 직후 X선 회절로 관측한 구조"),
         ("관측 단위", "한 행 = 조성 1종", "이름 표기가 달라도 조성이 같으면 하나로"),
         ("출처", "논문 공개 데이터", "Machaka(2021) 부록 CSV\n문헌 실험 결과를 모은 2차 데이터")]
sw = (CW - 3 * 0.25) / 4
for i, (n, t, dsc) in enumerate(steps):
    outline_card(s, MX + i * (sw + 0.25), TOP, sw, 1.9, [
        {"text": n, "bold": True, "size": 12, "color": ACCENT, "after": 2},
        {"text": t, "bold": True, "size": 16, "color": INK, "after": 4},
        {"text": dsc, "size": 12}], anchor=MSO_ANCHOR.TOP, label=f"step {n}")
table(s, MX, TOP + 2.2, 7.4, [2.6, 1.7, 3.1], [
    ["변수", "척도", "평균을 낼 수 있나"],
    ["상 (Phases)", "범주형 · 명목", "빈도·비율로만 요약"],
    ["원소 개수", "수치형 · 이산", "정수값, 최빈값도 함께"],
    ["VEC, δ, Δχ, ΔHmix, ΔSmix", "수치형 · 연속", "분포를 보고 판단"],
], size=13, row_h=0.46, label="scale", tags={(1, 2): ("no", "불가"), (2, 2): ("ok", "가능"), (3, 2): ("ok", "가능")})
card(s, MX + 7.75, TOP + 2.2, CW - 7.75, 1.84, ["**AI 함정 #1 대응:** 참고한 Kaggle 데이터는 비공개였다. AI의 말을 믿지 않고 원 논문의 부록 파일을 **직접 내려받아** 1,361행 × 53열을 눈으로 확인했다."],
     fill=WARN_TINT, size=15)

# ---------------- 5. Diagnosis ----------------
s = new_slide("데이터 진단", "고치기 전에 먼저 본다 — 진단 결과", "3주차",
              notes="3주차: 진단과 처리를 분리. 이 표는 아무것도 고치지 않은 상태에서 본 결과다.")
table(s, MX, TOP, 8.3, [1.95, 1.4, 4.95], [
    ["점검 항목", "결과", "의미"],
    ["인코딩", "UTF-8 실패", "**cp1252**로 지정해 해결 (‘10°C/min’ 기호가 원인)"],
    ["완전히 같은 행", "0행", "복사·붙여넣기 중복은 없음"],
    ["같은 합금 이름", "890행 반복", "열처리·논문만 다른 기록 → 지우면 안 되는 중복"],
    ["표기만 다른 조성", "15종", "AlCrFeCoNi = AlCoCrFeNi. 글자 비교로는 못 잡음"],
    ["열처리 열 결측", "758~1,305행", "빈칸 = ‘처리하지 않음’. **이유가 있는 빈칸**"],
    ["상 라벨 충돌", "15종", "같은 조성인데 논문마다 상이 다름"],
    ["이름과 안 맞는 값", "60건·39행", "VEC 38·Δχ 22건 오타 / 39행은 다른 조성으로 계산됨"],
], size=12, row_h=0.56, label="diag")
cx = MX + 8.6
card(s, cx, TOP, CW - 8.6, 2.1, ["**AI 함정 #2 대응:** “정제해줘”가 아니라 **“문제를 보고만 하고 아무것도 고치지 마”**로 시켰다."],
     fill=WARN_TINT, size=15)
card(s, cx, TOP + 2.35, CW - 8.6, 1.7, ["처리 방법은 이 표를 본 뒤 **분석 전에** 정하고, 정제 로그에 모두 적었다."], size=15)

# ---------------- 6. Judgments ----------------
s = new_slide("정제 판단", "지울 것인가, 고칠 것인가 — 세 가지 판단", "3주차",
              notes="빈칸은 '처리 안 함', 같은 이름은 진짜 중복이 아닐 수 있음, 이상치는 원본(합금 이름)으로 되짚어 오류인지 확인한 뒤 결정.")
cols = [
    ("① 빈칸에도 이유가 있다",
     "열처리 온도가 빈 칸은 ‘모름’이 아니라 **‘열처리를 안 함’**. 같은 합금도 열처리하면 상이 바뀐다(두 상태가 다 있는 49종 중 22종).",
     "→ 채우지 않고, 빈칸인 행(= 주조 직후)만 골라 조건 통일"),
    ("② 중복처럼 보이는 것",
     "AlCoCrFeNi는 논문마다 **BCC**이기도, **금속간화합물**이기도 했다. 이전 코드는 ‘첫 행만 남기기’라 행 순서가 정답을 정했다.",
     "→ 라벨 충돌 15종은 **제외**, 같은 조성은 표기가 달라도 **하나로**"),
    ("③ 원본(이름)으로 되짚기",
     "이름으로 VEC·Δχ·ΔSmix를 다시 계산. ΔSmix가 맞으면 **값만 오타** → 교정(VEC 38, Δχ 22. 예: TiZrNbTa Δχ 3.92 → 0.10). ΔSmix도 틀리면 **조성 자체가 틀림** → 제외(39행).",
     "→ 극단값(δ 16.9%, ΔHmix −39)은 이름과 일치 → 그대로"),
]
cw3 = (CW - 2 * 0.3) / 3
for i, (t, body, act) in enumerate(cols):
    outline_card(s, MX + i * (cw3 + 0.3), TOP, cw3, 3.75, [
        {"text": t, "bold": True, "size": 17, "color": INK, "after": 8},
        {"text": body, "size": 13.5, "after": 8},
        {"text": act, "size": 13.5, "color": ACCENT_DARK, "bold": True}], anchor=MSO_ANCHOR.TOP, label=t)
card(s, MX, TOP + 4.0, CW, 0.85, ["표기가 애매해 검증 못 한 17행(예: NbTaTi30Zr)은 원본 값을 그대로 두었다 — **고치지 않기로 한 결정도 기록**한다."],
     size=14)

# ---------------- 6b. Why the alloy name is the reference ----------------
s = new_slide("정제 판단 · 검증 기준", "조성 열이 아니라 ‘합금 이름’을 기준으로 삼은 이유", "3주차",
              notes="이름과 조성 열이 다른 54행에서, 정리자가 계산해 넣은 VEC·ΔSmix는 52행이 이름과 일치했다. 조성 열에 옮겨 적기 실수가 있었던 것. 조성 열로 고쳤다면 맞는 값을 틀린 값으로 바꿨을 것.")
lw6 = 6.3
card(s, MX + 0.8, TOP + 0.1, lw6 - 1.6, 0.9, [{"text": "원본 · 논문 저자가 보고", "bold": True, "size": 11, "color": "9EC5F4", "align": PP_ALIGN.CENTER, "after": 2},
                                          {"text": "합금 이름 “Al2CoCrFeNi”", "bold": True, "size": 17, "color": "FFFFFF", "align": PP_ALIGN.CENTER}],
     fill="12305A", pad=0.1, label="origin")
bw2 = (lw6 - 0.2) / 2
for k, (edge, title, sub, fill, col) in enumerate([
        ("↓ 정리자가 **계산**", "VEC 6.50 · ΔSmix 12.98", "이름과 일치 ✓", GOOD_TINT, GOOD),
        ("↓ 정리자가 **옮겨 적음**", "조성 열: Al 비율 오기", "이 비율로 계산하면 VEC 8.00 ✗", BAD_TINT, BAD)]):
    bx = MX + k * (bw2 + 0.2)
    textbox(s, bx, TOP + 1.1, bw2, 0.4, [{"text": edge, "align": PP_ALIGN.CENTER}], size=13, label="edge")
    card(s, bx, TOP + 1.55, bw2, 0.95, [{"text": title, "bold": True, "size": 15, "color": INK, "align": PP_ALIGN.CENTER, "after": 2},
                                        {"text": sub, "bold": True, "size": 13, "color": col, "align": PP_ALIGN.CENTER}],
         fill=fill, pad=0.1, label=f"branch{k}")
card(s, MX, TOP + 2.75, lw6, 1.45, ["조성 열도 이름에서 옮겨 적은 **2차 값**이다. 조성 열로 ‘교정’했다면 맞는 VEC 6.50을 **틀린 8.00으로 바꿨을 것** — 6.5는 BCC 쪽, 8.0은 FCC 경계다."],
     fill=WARN_TINT, size=14)
rx6, rw6 = MX + 6.7, CW - 6.7
sw6 = (rw6 - 0.2) / 2
for k, (v, l) in enumerate([("1,289", "이름 = 조성 열 (96%)\n어느 쪽을 써도 같다"), ("54", "이름 ≠ 조성 열\n누가 맞는지가 중요")]):
    outline_card(s, rx6 + k * (sw6 + 0.2), TOP, sw6, 1.32, [{"text": v, "bold": True, "size": 28, "color": INK, "after": 0},
                                                            {"text": l, "size": 12, "color": MUTED}], label=f"stat6b{k}")
textbox(s, rx6, TOP + 1.42, rw6, 0.68, ["54행에서, 정리자가 계산해 넣은 **VEC·ΔSmix는 어느 쪽 조성과 맞았나?**"], size=14, label="q6b")
table(s, rx6, TOP + 2.15, rw6, [3.0, 1.2], [["일치하는 쪽", "행 수"], ["합금 이름", "**52**"], ["조성 열", "1"], ["둘 다 아님", "1"]],
      size=13, row_h=0.38, label="t6b", num_cols=(1,))
card(s, rx6, TOP + 3.9, rw6, 1.05, ["정리자는 **이름 기준의 올바른 조성**으로 계산했고, 실수는 조성 열을 옮겨 적을 때 생겼다 → **이름을 기준**으로 검증."],
     size=13.5)
note(s, "이름을 해석할 수 있는 1,343행 기준. 표기가 애매한 17행(예: NbTaTi30Zr)은 추측하지 않고 원본 값을 그대로 두었다.")
# ---------------- 6c. Formulas ----------------
s = new_slide("계산 공식", "이름으로 계산한 두 공식 — VEC와 ΔSmix",
              notes="VEC는 원소별 가전자 수를 비율로 가중 평균한 값. ΔSmix는 비율만으로 계산되는 섞임의 무질서도로, 원소 고유값이 없어서 조성 검증의 열쇠로 썼다. 예시는 Al2CoCrFeNi.")
hw = (CW - 0.4) / 2
for k, (lab, eq, hdr, rows, tail) in enumerate([
        ("VEC (가전자 농도) — 원자당 평균 가전자 수", "VEC = Σ c_{i} × VEC_{i}",
         ["원소", "비율 c_{i}", "가전자 수 VEC_{i}", "c_{i} × VEC_{i}"],
         [["Al", "2/6 = 0.333", "3", "1.000"], ["Co", "1/6 = 0.167", "9", "1.500"], ["Cr", "0.167", "6", "1.000"],
          ["Fe", "0.167", "8", "1.333"], ["Ni", "0.167", "10", "1.667"], ["합계", "", "", "**VEC = 6.50**"]],
         "가전자 수 = 주기율표 족 번호 (Al 3, Ti 4, Nb 5, Cr 6, Mn 7, Fe 8, Co 9, Ni 10, Cu 11). 6.50 < 6.87 → BCC 영역"),
        ("ΔSmix (혼합 엔트로피) — 섞임의 무질서도", "ΔSmix = −R × Σ c_{i} ln c_{i}",
         ["원소", "비율 c_{i}", "ln c_{i}", "c_{i} × ln c_{i}"],
         [["Al", "0.333", "−1.099", "−0.366"], ["Co", "0.167", "−1.792", "−0.299"], ["Cr", "0.167", "−1.792", "−0.299"],
          ["Fe", "0.167", "−1.792", "−0.299"], ["Ni", "0.167", "−1.792", "−0.299"], ["합계", "", "", "−1.561"]],
         "R = 8.314 J/(K·mol) → ΔSmix = −8.314 × (−1.561) = **12.98 J/(K·mol)**")]):
    x0 = MX + k * (hw + 0.4)
    textbox(s, x0, TOP - 0.08, hw, 0.45, [{"text": lab, "bold": True}], size=15, color=INK, label=f"lab{k}")
    card(s, x0, TOP + 0.42, hw, 0.6, [{"text": eq, "bold": True, "align": PP_ALIGN.CENTER, "color": INK}], fill=CARD, size=18,
         pad=0.08, label=f"eq{k}")
    table(s, x0, TOP + 1.15, hw, [0.9, 1.55, 1.75, 1.65], [hdr] + rows, size=12, header_size=11, row_h=0.34,
          label=f"ftab{k}", num_cols=(1, 2, 3))
    textbox(s, x0, TOP + 3.6, hw, 0.62, [tail], size=12, label=f"tail{k}")
card(s, MX, TOP + 4.35, hw, 0.85, ["**같은 비율로 n개 원소** → ΔSmix = R ln n. 3원소 9.13 · 4원소 11.53 · 5원소 13.38 · 6원소 14.90 (히스토그램의 봉우리)"],
     size=13, label="eqn")
card(s, MX + hw + 0.4, TOP + 4.35, hw, 0.85, ["**ΔSmix에는 원소 고유값이 없다** → 비율만 맞으면 반드시 같은 값 → ‘조성을 제대로 썼나’를 가리는 **검증의 열쇠**"],
     fill=WARN_TINT, size=13, label="key")
note(s, "예시: Al2CoCrFeNi (Al 2 : Co 1 : Cr 1 : Fe 1 : Ni 1, 합계 6). c_{i} = 원소 i의 몰 비율(모두 더하면 1).", y=H - 0.66, h=0.36)
# ---------------- 7. Cleaning log ----------------
s = new_slide("정제 로그", "1,361행 → 258종: 모든 규칙과 행 수", "3주차",
              notes="규칙 9개를 순서대로. 회색은 행을 지우지 않은 결정. 라벨 충돌 규칙은 정확도를 4%p 바꾸므로 한계로 함께 말한다.")
log = [["#", "규칙", "전", "후", "이유"],
       ["1", "빈 행 제외", "1,361", "1,360", "CSV 끝의 빈 줄"],
       ["2", "이름으로 VEC·Δχ 교정", "1,360", "1,360", "오타 60건, 행 유지"],
       ["3", "잘못된 조성 행 제외", "1,360", "1,321", "ΔSmix까지 이름과 다름"],
       ["4", "ΔSmix ≥ 1R", "1,321", "1,292", "조작적 정의 밖의 일반 합금"],
       ["5", "주조(AC)만", "1,292", "1,217", "분말야금은 제조 경로가 다름"],
       ["6", "가공·열처리 없음", "1,217", "470", "주조 직후 상태로 통일"],
       ["7", "라벨 충돌 제외", "470", "404", "15종, 정답을 정할 수 없음"],
       ["8", "같은 조성은 1행", "404", "258", "관측 단위 = 조성 1종"],
       ["9", "이상치·결측 그대로", "258", "258", "지울 근거 없음, 대치 안 함"]]
gt = table(s, MX, TOP, 8.4, [0.4, 2.3, 0.85, 0.85, 4.0], log, size=12, row_h=0.46, label="log", num_cols=(2, 3))
for i in (2, 9):
    for j in range(5):
        for p in gt.cell(i, j).text_frame.paragraphs:
            for r in p.runs:
                r.font.color.rgb = rgb(MUTED)
cx = MX + 8.7
card(s, cx, TOP, CW - 8.7, 2.35, [
    {"text": "규칙 한 줄이 결론을 바꾸나?", "bold": True, "color": INK, "after": 8},
    {"text": "7번 대신 ‘첫 행만 남기기’", "after": 0}, {"text": "n = 273, 정확도 **78.7%**", "after": 8},
    {"text": "7번 사용", "after": 0}, {"text": "n = 258, 정확도 **83.0%**"}], size=15, label="sens")
card(s, cx, TOP + 2.6, CW - 8.7, 1.95, ["변수 순위는 같지만 **정확도는 4%p 차이**. 애매한 합금을 빼면 문제가 쉬워진다 — 83%는 ‘정답이 확실한 합금’에서의 성능이다."],
     fill=WARN_TINT, size=14)
note(s, "회색 행은 행을 지우지 않은 결정. 규칙은 모두 모델 결과를 보기 전에 정했다.")

# ---------------- 8. Descriptive stats ----------------
s = new_slide("기술통계", "평균과 중앙값을 함께, 표준편차와 n도 함께", "4주차",
              notes="4주차 보고 규칙: 평균 옆에 중앙값·표준편차·n. 평균과 중앙값이 다르면 그 차이가 보고 내용.")
desc = [["변수", "n", "평균", "중앙값", "표준편차", "최솟값 (합금)", "최댓값 (합금)", "평균으로 요약?"],
        ["원소 개수", "258", "5.12", "5", "0.84", "3 (CoFeNi)", "7 (Al0.5CoCrCu0.5FeNiTi0.5)", "대칭"],
        ["VEC", "258", "6.09", "6.52", "1.53", "3.46 (Al58.5Mg31.5…)", "9.00 (CoFeNi)", "봉우리 둘"],
        ["원자 크기 차이 δ (%)", "258", "5.34", "5.34", "2.07", "0.75 (CoFeNi)", "16.86 (AlCCoCrFeNi)", "꼬리 주의"],
        ["전기음성도 차이 Δχ", "258", "0.17", "0.14", "0.08", "0.03 (CoFeNi)", "0.38 (HfNbTaTiZrMoW)", "오른쪽 꼬리"],
        ["ΔHmix (kJ/mol)", "258", "−7.54", "−6.21", "7.74", "−39.45 (Mo0.5NbHf0.5ZrTiSi0.9)", "4.16 (CoCrCuFeMn)", "왼쪽 꼬리"],
        ["ΔSmix (J/K·mol)", "258", "12.89", "13.15", "1.55", "8.34 (Al58.5Mg31.5…)", "16.18 (HfNbTaTiZrMoW)", "봉우리 여럿"]]
table(s, MX, TOP, CW, [2.05, 0.55, 0.75, 0.8, 0.95, 2.6, 2.5, 1.95], desc, size=12, header_size=11, row_h=0.5, label="desc",
      num_cols=(1, 2, 3, 4), tags={(1, 7): ("ok", "가능"), (2, 7): ("no", "불가"), (3, 7): ("ok", "가능"),
                                    (4, 7): ("no", "중앙값"), (5, 7): ("no", "중앙값"), (6, 7): ("no", "불가")})
card(s, MX, TOP + 3.75, CW, 0.95, ["**ΔHmix:** 왼쪽으로 꼬리가 긴 분포(왜도 −0.94). 강하게 음수인 소수 합금(대부분 금속간화합물)이 평균(−7.54)을 중앙값(−6.21)보다 꼬리 쪽으로 끌어간다."],
     size=15)
note(s, "평균과 중앙값의 차이가 표준편차의 0.15배를 넘거나 봉우리가 둘 이상이면 평균 하나로 요약하지 않았다. 정제 후 결측 0건.")

# ---------------- 9. Histograms ----------------
s = new_slide("분포의 모양", "그려 보기 전에는 모른다 — 히스토그램 (구간 25개)", "4주차",
              notes="VEC는 봉우리가 둘. 평균 6.09 자리에는 합금이 거의 없다 = 평균이 빈자리를 가리킨다. 두 집단이 섞인 신호라 상별로 쪼갠다.")
image(s, "histograms", MX, TOP - 0.05, CW, 3.85)
card(s, MX, TOP + 3.95, CW / 2 - 0.15, 1.15, ["**VEC는 이봉 분포.** 평균 6.09 자리에는 합금이 거의 없다 — **평균이 빈자리를 가리킨다**. 두 집단이 섞였다는 신호 → 상별로 쪼갠다."],
     size=14)
card(s, MX + CW / 2 + 0.15, TOP + 3.95, CW / 2 - 0.15, 1.15, ["**ΔSmix의 봉우리**는 11.5·13.4·14.9 = R·ln4·ln5·ln6. **4·5·6원소를 똑같은 비율로 섞은 합금**이 많다는 뜻이다."],
     size=14)
note(s, "검은 실선 = 평균, 주황 점선 = 중앙값. 원소 개수는 정수라 구간을 1 단위로 그렸다.", y=H - 0.68, h=0.36)

# ---------------- 10. By phase ----------------
s = new_slide("집단별 기술통계", "상별로 쪼개면 VEC가 깔끔하게 갈린다", "4주차",
              notes="쪼갠 뒤 각 상의 표준편차가 0.5~1.0으로 줄었다. 금속간화합물만 VEC로 안 갈리고 ΔHmix가 가장 음수.")
image(s, "vec_by_phase", MX, TOP, 6.3, 3.6)
table(s, MX + 6.6, TOP, CW - 6.6, [1.45, 0.55, 1.45, 0.85, 1.25], [
    ["상", "n", "VEC 평균 (SD)", "중앙값", "ΔHmix 중앙값"],
    ["BCC", "131", "5.03 (0.99)", "4.67", "−2.8"],
    ["FCC+BCC", "22", "7.43 (0.49)", "7.47", "−7.8"],
    ["FCC", "27", "8.12 (0.47)", "8.06", "−5.0"],
    ["금속간화합물", "78", "6.79 (1.30)", "7.12", "−11.8"],
], size=13, row_h=0.42, label="byphase", num_cols=(1, 2, 3, 4))
card(s, MX + 6.6, TOP + 2.3, CW - 6.6, 1.25, ["쪼개고 나니 각 상의 표준편차는 0.5~1.0으로 전체(1.53)보다 훨씬 작다. 경험 규칙(VEC < 6.87 → BCC, ≥ 8 → FCC)과 일치."],
     size=14)
card(s, MX + 6.6, TOP + 3.75, CW - 6.6, 1.0, ["금속간화합물은 VEC가 넓게 퍼져(SD 1.30) 못 가른다. 대신 **ΔHmix가 가장 음수**다."],
     fill=WARN_TINT, size=14)
note(s, "점 하나 = 합금 1종, 검은 막대 = 중앙값, 주황 점선 = 문헌의 VEC 경계값.")

# ---------------- 11. delta-dH ----------------
s = new_slide("탐색적 분석", "문헌의 고용체 조건도 금속간화합물을 다 걸러내지 못한다",
              notes="Guo & Liu의 고용체 영역 안에 금속간화합물도 41%가 들어온다. 규칙 하나로는 부족해서 여러 변수를 함께 쓰는 모델로 넘어간다.")
image(s, "delta_dh_facets", MX, TOP - 0.05, CW, 3.55)
for i, (v, l) in enumerate([("70.6%", "고용체(BCC·FCC·2상) 합금 중 영역 안에 든 비율"),
                            ("41.0%", "금속간화합물 중 영역 안에 든 비율 (걸러져야 할 합금)")]):
    outline_card(s, MX + i * (CW / 2 + 0.15), TOP + 3.65, CW / 2 - 0.15, 1.15, [
        {"text": v, "bold": True, "size": 30, "color": INK, "after": 0}, {"text": l, "size": 13, "color": MUTED}],
        label=f"stat{i}")
note(s, "주황 점선 = Guo & Liu(2011)의 고용체 형성 영역(δ ≤ 6.6%, −11.6 ≤ ΔHmix ≤ 3.2 kJ/mol). 파란 점 = 해당 상, 회색 점 = 나머지.")

# ---------------- 12. Concept: cross-validation ----------------
s = new_slide("개념 · 교차검증", "교차검증 — 시험을 다섯 번 나눠 본다",
              notes="처음 보는 합금으로 시험해야 진짜 실력. 한 번만 나누면 운이 끼므로 5조각으로 돌아가며 시험하고 평균을 낸다. 층화는 조각마다 상 비율을 같게 맞추는 것.")
gx, gy, lw, bw, bh, gap = MX, TOP + 0.35, 0.85, 1.0, 0.44, 0.08
for j in range(5):
    textbox(s, gx + lw + j * (bw + gap), TOP - 0.1, bw, 0.38, [{"text": f"조각 {j + 1}", "align": PP_ALIGN.CENTER, "bold": True}],
            size=12, color=INK2, label="foldhdr")
textbox(s, gx + lw + 5 * (bw + gap), TOP - 0.1, 1.1, 0.38, [{"text": "시험 정확도", "align": PP_ALIGN.CENTER, "bold": True}],
        size=12, color=INK2, label="acchdr")
for i in range(5):
    yy = gy + i * (bh + gap)
    textbox(s, gx, yy + 0.04, lw, 0.36, [{"text": f"{i + 1}회차", "bold": True}], size=12, color=INK2, label="round")
    for j in range(5):
        test = i == j
        rect(s, gx + lw + j * (bw + gap), yy, bw, bh, ORANGE if test else "CDE2FB", "시험" if test else "학습", size=12,
             color="FFFFFF" if test else ACCENT_DARK)
    textbox(s, gx + lw + 5 * (bw + gap), yy + 0.02, 1.1, 0.4, [{"text": f"a{i + 1}", "align": PP_ALIGN.CENTER, "bold": True}],
            size=13, color=INK, label="acc")
ly = gy + 5 * (bh + gap) + 0.1
rect(s, gx, ly + 0.05, 0.2, 0.2, "CDE2FB", rounded=False)
textbox(s, gx + 0.28, ly, 2.4, 0.36, ["학습용 (약 206종)"], size=12, label="lg1")
rect(s, gx + 2.6, ly + 0.05, 0.2, 0.2, ORANGE, rounded=False)
textbox(s, gx + 2.88, ly, 4.0, 0.36, ["시험용 (약 52종, 모델이 처음 보는 합금)"], size=12, label="lg2")
card(s, gx, ly + 0.5, 7.25, 0.62, [{"text": "최종 성능 = (a1 + a2 + a3 + a4 + a5) ÷ 5  ± 표준편차", "bold": True, "align": PP_ALIGN.CENTER,
                                    "color": INK}], fill=CARD, size=16, pad=0.1)
rx = MX + 7.65
textbox(s, rx, TOP, CW - 7.65, 3.4, [
    {"text": "**왜 나누나:** 공부한 문제로 시험 보면 100점. 처음 보는 합금으로 시험해야 진짜 실력이다", "bullet": True, "after": 8},
    {"text": "**왜 다섯 번:** 한 번만 나누면 쉬운 문제가 시험에 몰리는 ‘운’이 생긴다. 모든 합금이 한 번씩 시험에 나오게 돌린다", "bullet": True, "after": 8},
    {"text": "**층화(stratified):** 조각마다 상 비율(BCC 51%…)을 똑같이 맞춘다", "bullet": True},
], size=14, label="cv-text")
card(s, rx, TOP + 3.55, CW - 7.65, 1.15, ["SMOTE·전처리는 **학습 조각 안에서만**. 시험 조각을 건드리면 점수가 부풀려진다(슬라이드 22)."],
     fill=WARN_TINT, size=14)

# ---------------- 13. Models ----------------
s = new_slide("예측 모델", "모델은 단순 규칙보다 26%p 더 정확하다",
              notes="BCC가 51%라 전부 BCC라고 찍어도 51%. 그래서 정확도만이 아니라 상마다 고르게 맞혔는지 보는 Macro F1을 같이 본다.")
image(s, "model_compare", MX, TOP, 6.4, 3.7)
table(s, MX + 6.7, TOP, CW - 6.7, [2.5, 1.7, 1.2], [
    ["방법", "정확도 (SD)", "Macro F1"],
    ["전부 BCC라고 찍기", "50.8%", "—"],
    ["VEC 규칙 (기준선)", "57.4%", "0.42"],
    ["로지스틱 회귀", "75.2% (3.6)", "0.68"],
    ["**랜덤포레스트**", "**83.0% (4.4)**", "**0.79**"],
    ["그래디언트 부스팅", "78.3% (1.5)", "0.73"],
], size=13, row_h=0.42, label="models", num_cols=(1, 2))
card(s, MX + 6.7, TOP + 2.75, CW - 6.7, 1.3, ["BCC가 51%라 정확도만 보면 과대평가된다 → 상마다 고르게 맞혔는지 보는 **Macro F1**을 함께 보고한다."],
     size=14)
note(s, "입력 변수 6개, 5-fold 층화 교차검증 평균. 괄호 = 5회의 표준편차(%p).")

# ---------------- 14. Pseudo R2 ----------------
s = new_slide("예측 모델 · 설명력", "모델별 R² — 분류 모델에서는 ‘의사 R²’로 잰다",
              notes="R²는 회귀용. 분류에는 McFadden 의사 R² = 1 − 모델 로그손실 / 비율대로 찍기의 로그손실. 0.2~0.4만 돼도 좋은 편. 부스팅은 정확도는 높아도 틀릴 때 과신해서 R²가 낮다.")
image(s, "pseudo_r2", MX, TOP, 6.3, 3.7)
rx = MX + 6.6
textbox(s, rx, TOP, CW - 6.6, 0.75, ["**R²**는 숫자를 예측하는 회귀용 지표다. 상(범주)을 맞히는 분류에는 **McFadden 의사 R²**를 쓴다."], size=15,
        label="r2-intro")
card(s, rx, TOP + 0.85, CW - 6.6, 0.75, [{"text": "R²(McF) = 1 − 모델의 로그손실 ÷ ‘비율대로 찍기’의 로그손실", "bold": True, "color": INK,
                                          "align": PP_ALIGN.CENTER}], fill=CARD, size=14, pad=0.1)
textbox(s, rx, TOP + 1.75, CW - 6.6, 2.4, [
    {"text": "0 = 상 비율대로 찍는 것과 같음, 1 = 완벽. **0.2~0.4만 돼도 좋은 편**", "bullet": True, "after": 6},
    {"text": "랜덤포레스트 **0.59**로 가장 높다", "bullet": True, "after": 6},
    {"text": "부스팅은 정확도(78%)가 로지스틱(75%)보다 높은데 R²는 낮다 → **틀릴 때 너무 확신**해서 감점이 크다", "bullet": True},
], size=14, label="r2-bul")
note(s, "로그손실: 정답에 준 확률이 낮을수록 커지는 벌점. 5-fold 교차검증의 시험 조각에서 계산.")

# ---------------- 15. Concept: confusion matrix ----------------
s = new_slide("개념 · 혼동행렬", "혼동행렬 — ‘무엇을 무엇으로’ 틀렸는지 보는 표",
              notes="행이 실제, 열이 예측. 대각선이 맞힌 것. 재현율은 행 방향, 정밀도는 열 방향으로 읽는다.")
textbox(s, MX, TOP, 6.0, 0.42, ["예: “FCC인가, 아닌가”만 볼 때"], size=15, label="cm-ex")
hx, hy, c0, cw2, rh = MX, TOP + 0.5, 1.45, 2.2, 1.15
for j, t in enumerate(["FCC라고 예측", "아니라고 예측"]):
    textbox(s, hx + c0 + j * (cw2 + 0.1), hy - 0.02, cw2, 0.38, [{"text": t, "align": PP_ALIGN.CENTER, "bold": True}], size=12, color=MUTED,
            label="cmh")
cells = [[("정답", "맞게 찾음", "g"), ("놓침", "FCC인데 못 찾음", "r")], [("헛짚음", "아닌데 FCC라고 함", "r"), ("정답", "맞게 걸러냄", "g")]]
for i, rowlab in enumerate(["실제 FCC", "실제 FCC 아님"]):
    yy = hy + 0.42 + i * (rh + 0.1)
    textbox(s, hx, yy + rh / 2 - 0.2, c0 - 0.1, 0.4, [{"text": rowlab, "bold": True, "align": PP_ALIGN.RIGHT}], size=12, color=MUTED,
            label="cmr")
    for j, (t, sub, kind) in enumerate(cells[i]):
        rect(s, hx + c0 + j * (cw2 + 0.1), yy, cw2, rh, "CDE2FB" if kind == "g" else "FDF0EA", f"{t}\n{sub}", size=16,
             color=ACCENT_DARK if kind == "g" else BAD)
rx = MX + 6.4
textbox(s, rx, TOP, CW - 6.4, 3.3, [
    {"text": "**행 = 실제 상, 열 = 예측한 상.** 대각선이 진할수록 좋은 모델", "bullet": True, "after": 6},
    {"text": "**재현율(recall):** 실제 FCC 중 FCC로 찾아낸 비율 — 행 방향으로 읽는다", "bullet": True, "after": 6},
    {"text": "**정밀도(precision):** FCC라고 한 것 중 진짜 FCC 비율 — 열 방향으로 읽는다", "bullet": True, "after": 6},
    {"text": "정확도 하나는 ‘어디서’ 틀렸는지 숨긴다. 혼동행렬은 **틀린 방향**을 보여준다", "bullet": True},
], size=15, label="cm-text")
card(s, rx, TOP + 3.5, CW - 6.4, 0.9, ["우리 문제는 상이 4개라 4×4 표가 된다. 다음 장에서 실제 결과를 읽는다."], size=14)

# ---------------- 16. Confusion / importance ----------------
s = new_slide("예측 결과 해석", "무엇을 맞히고, 무엇을 틀렸나",
              notes="2상은 22종뿐이라 배울 예가 적고, 틀린 것의 대부분은 금속간화합물로 갔다. 순열 중요도는 VEC가 압도적.")
image(s, "confusion", MX, TOP - 0.05, 5.2, 3.7)
image(s, "importance", MX + 5.5, TOP - 0.05, CW - 5.5, 3.7)
card(s, MX, TOP + 3.8, CW, 1.05, ["**BCC(89%)는 잘 맞히고, FCC+BCC 2상은 68%** — 22종뿐이라 배울 예가 적고, 틀린 것의 대부분(23%)은 금속간화합물로 갔다. 순열 중요도는 **VEC가 압도적**, ΔHmix가 2위."],
     size=14)
note(s, "왼쪽: 혼동행렬(교차검증 예측, 행 = 실제 상, 재현율) · 오른쪽: 순열 중요도(변수 하나를 뒤섞었을 때 정확도가 떨어지는 정도, 5개 fold 평균).",
     y=H - 0.68, h=0.36)

# ---------------- 17. Concept: SHAP ----------------
s = new_slide("개념 · SHAP", "SHAP — 예측 하나를 변수별 기여로 나눈다",
              notes="팀 프로젝트 점수를 팀원 기여도로 나누듯, 예측 확률을 변수별 몫으로 나눈다. +면 그 상 쪽, −면 반대. 순열 중요도와 순위를 교차 확인한다.")
card(s, MX, TOP, 5.9, 0.95, [{"text": "이 합금의 BCC 확률 = 평균 확률 + VEC 몫 + ΔHmix 몫 + δ 몫 + …", "bold": True, "color": INK,
                              "align": PP_ALIGN.CENTER}], fill=CARD, size=15, pad=0.12)
textbox(s, MX, TOP + 1.15, 5.9, 3.0, [
    {"text": "**비유:** 팀 프로젝트 점수를 팀원 기여도로 공정하게 나누기 (게임이론의 섀플리 값)", "bullet": True, "after": 8},
    {"text": "**+ 값**이면 그 상 쪽으로 밀고, **− 값**이면 반대로 민다", "bullet": True, "after": 8},
    {"text": "합금 하나하나에 대해 계산 → 모으면 **변수가 어느 방향으로 작용하는지** 보인다", "bullet": True},
], size=15, label="shap-text")
table(s, MX + 6.3, TOP, CW - 6.3, [1.5, 2.6, 2.6], [
    ["", "순열 중요도", "SHAP"],
    ["질문", "이 변수를 망가뜨리면 얼마나 틀리나", "이 예측에 각 변수가 얼마나 기여했나"],
    ["방향 (+/−)", "모름", "**앎**"],
    ["합금 하나 설명", "불가", "**가능**"],
    ["상별로 따로", "하나로 합쳐짐", "**상마다 따로**"],
], size=13, row_h=0.62, label="shap-vs")
card(s, MX + 6.3, TOP + 3.3, CW - 6.3, 0.8, ["두 방법을 함께 써서 **순위가 같은지** 교차 확인한다."], size=14)
note(s, "SHAP은 ‘모델이 이렇게 판단했다’를 설명할 뿐, 자연 법칙을 증명하지는 않는다. Lundberg & Lee (2017).")

# ---------------- 18. SHAP results ----------------
s = new_slide("해석 · SHAP", "모델은 ‘두 갈림길’을 그대로 배웠다",
              notes="VEC가 7.3 위면 FCC 쪽, 6.9 위면 BCC 반대쪽 — 문헌 경계 6.87과 거의 같다. ΔHmix가 −7보다 음수면 금속간화합물 쪽. SHAP과 순열 중요도 순위가 같다.")
image(s, "shap_dependence", MX, TOP - 0.05, CW, 3.5)
cw3 = (CW - 2 * 0.2) / 3
for i, t in enumerate([
    "**VEC → FCC/BCC:** 약 7.3 위에서 FCC 쪽(+), 약 6.9 위에서 BCC 반대쪽(−). 문헌 경계 6.87과 거의 같다.",
    "**ΔHmix → 금속간화합물:** 약 −7 kJ/mol보다 음수일수록 Im 쪽(+). ‘원소끼리 너무 친하면 짝지어 뭉친다’.",
    "**순위 교차 확인:** SHAP과 순열 중요도 모두 VEC → ΔHmix → δ → Δχ → ΔSmix → 원소 개수."]):
    card(s, MX + i * (cw3 + 0.2), TOP + 3.6, cw3, 1.3, [t], size=13.5)
note(s, "점 하나 = 합금 1종. 세로축 = 그 변수가 해당 상 확률을 얼마나 올렸나(+)/내렸나(−). 258종 전체로 학습한 랜덤포레스트.",
     y=H - 0.68, h=0.36)

# ---------------- 19. SHAP example ----------------
s = new_slide("해석 · SHAP 개별 사례", "AlCoFeNi는 VEC 7.5인데 왜 BCC일까",
              notes="VEC만 보면 BCC가 아니지만, Al이 커서 원자 크기 차이가 6.24%로 크고 이게 BCC 쪽으로 더 세게 밀었다. VEC 규칙의 예외를 모델은 δ로 잡아냈다.")
image(s, "shap_example", MX, TOP, 6.8, 3.9)
rx = MX + 7.1
textbox(s, rx, TOP, CW - 7.1, 2.6, [
    {"text": "VEC 7.5는 규칙상 BCC가 아니다 → SHAP도 **−0.20** (BCC 반대)", "bullet": True, "after": 6},
    {"text": "그런데 **원자 크기 차이 6.24%**(+0.15)와 Δχ·ΔHmix가 BCC 쪽으로 더 세게 밀었다", "bullet": True, "after": 6},
    {"text": "결과: BCC 확률 평균 0.51 → **0.71**, 실제로도 BCC", "bullet": True},
], size=15, label="ex-text")
card(s, rx, TOP + 2.8, CW - 7.1, 1.4, ["**Al은 원자가 크다** → δ가 커진다 → 빽빽한 FCC가 불편해져 BCC로. VEC 규칙의 예외(Al 합금)를 모델은 δ로 잡아냈다."],
     size=14)

# ---------------- 20. SMOTE ----------------
s = new_slide("비판적 검토", "참고 노트북의 높은 정확도는 부풀려진 숫자였다",
              notes="SMOTE를 먼저 하고 나누면 시험 조각에 가짜 샘플이 섞여 89%. 올바르게 하면 83%. 평균 대치가 표준편차를 줄이는 것과 같은 구조.")
image(s, "smote_leak", MX, TOP + 0.1, 6.6, 3.5)
textbox(s, MX + 6.9, TOP + 0.1, CW - 6.9, 2.6, [
    {"text": "SMOTE: 소수 상의 가짜 샘플을 만들어 불균형을 줄이는 기법", "bullet": True, "after": 8},
    {"text": "참고 노트북은 **SMOTE를 먼저 하고 데이터를 나눴다** → 시험 조각에 가짜 샘플이 섞임", "bullet": True, "after": 8},
    {"text": "같은 방식으로 재현하면 **89%**, 올바르게 하면 **83%**", "bullet": True},
], size=15, label="smote-text")
card(s, MX + 6.9, TOP + 2.85, CW - 6.9, 1.6, ["3주차의 교훈과 같다: 가짜 값을 끼워 넣으면 숫자가 실제보다 좋아 보인다 — **평균 대치가 표준편차를 줄이는 것과 같은 구조**."],
     fill=WARN_TINT, size=14)

# ---------------- 21. Conclusion ----------------
s = new_slide("결론과 한계", "이 데이터에는 누가 빠져 있는가", "2주차 · 편향",
              notes="발견: 약 83%, VEC가 FCC/BCC, ΔHmix가 금속간화합물, Al 예외는 δ. 한계: 출판 편향, 쉬운 문제 편향(4%p), 주조 직후만, ΔHmix·δ 미검증.")
half = (CW - 0.3) / 2
outline_card(s, MX, TOP, half, 3.75, [
    {"text": "발견한 것", "bold": True, "size": 18, "color": INK, "after": 8},
    {"text": "열역학 변수 6개로 주조 직후 상을 **약 83%** 맞힌다 (규칙 57%, 찍기 51%, 의사 R² 0.59)", "bullet": True, "after": 6},
    {"text": "**VEC가 FCC/BCC를**, **ΔHmix가 금속간화합물을** 가른다 — 기술통계·순열 중요도·SHAP이 같은 결론", "bullet": True, "after": 6},
    {"text": "VEC 규칙의 예외(Al 합금)는 **원자 크기 차이**가 설명한다", "bullet": True},
], size=13, anchor=MSO_ANCHOR.TOP, label="found")
outline_card(s, MX + half + 0.3, TOP, half, 3.75, [
    {"text": "한계 — 빠진 데이터", "bold": True, "size": 18, "color": INK, "after": 8},
    {"text": "**출판 편향:** 논문에 실린 합금만 있다. 실패한 합금은 없다", "bullet": True, "after": 6},
    {"text": "**쉬운 문제 편향:** 애매한 15종을 빼서 정확도가 4%p 높게 나왔다", "bullet": True, "after": 6},
    {"text": "**범위:** 주조 직후만. 열처리 후 상은 말할 수 없다", "bullet": True, "after": 6},
    {"text": "**검증하지 못한 값:** VEC·Δχ 오류는 고쳤지만, 표기가 애매한 17행과 ΔHmix·δ(원소 쌍 표 필요)는 재계산하지 못했다 — 오류가 남아 있을 수 있다", "bullet": True, "after": 6},
    {"text": "**이름이 맞다는 전제:** 모든 검증의 기준인 합금 이름을 원 논문과 직접 대조하지는 않았다", "bullet": True},
], size=13, anchor=MSO_ANCHOR.TOP, label="limits")
card(s, MX, TOP + 4.0, CW, 0.75, ["**활용:** 실험 전에 유망한 조성을 걸러내는 1차 필터. 단, 최종 판단은 실험이 한다."], size=15)

# ---------------- 22. Sources ----------------
s = new_slide("출처와 AI 활용", "데이터·참고 자료와 분석 방식",
              notes="AI에게는 코드와 계산을 맡기고, 질문·정의·검증은 직접 했다. 수업의 3단 루프(질문 → 명세 → 검증).")
textbox(s, MX, TOP, 5.9, 4.8, [
    {"text": "R. Machaka, “Machine learning-based prediction of phases in high-entropy alloys: A data article,” Data in Brief 38 (2021) 107346. PMC8477136 · Mendeley Data", "bullet": True, "after": 8},
    {"text": "E. Özcan, “High Entropy Alloys EDA and ML,” Kaggle Notebook (분석 흐름 참고)", "bullet": True, "after": 8},
    {"text": "S. Guo, C. T. Liu, Prog. Nat. Sci.: Mater. Int. 21 (2011) 433–446 (고용체 기준, VEC 경계)", "bullet": True, "after": 8},
    {"text": "S. M. Lundberg, S.-I. Lee, “A Unified Approach to Interpreting Model Predictions,” NeurIPS (2017) (SHAP)", "bullet": True, "after": 8},
    {"text": "코드·데이터·정제 로그: github.com/jungdaeun1018-ship-it/hea-phase-prediction", "bullet": True},
], size=13, label="refs")
table(s, MX + 6.2, TOP, CW - 6.2, [1.0, 2.3, 3.0], [
    ["단계", "AI(Claude Code)에게 맡긴 것", "사람이 판단한 것"],
    ["질문", "—", "주제·질문·조작적 정의"],
    ["명세", "코드 작성, 계산", "“고치지 말고 보고만”, “중앙값·분포 함께”"],
    ["검증", "재계산·교차검증·SHAP", "링크 직접 확인, 이름으로 값 대조, 행 수 비교"],
], size=13, row_h=0.78, label="ai")

# ---------------- write ----------------
if problems:
    print("FIT PROBLEMS:")
    for p in problems:
        print("  " + p)
    sys.exit(1)
prs.save(OUT)
print(f"saved {OUT} with {len(prs.slides)} slides, all text fits")
