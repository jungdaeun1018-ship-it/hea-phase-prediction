"""Draw the 'two forks' phase decision diagram.

Usage: python -I draw_phase_tree.py <out.png>
"""
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

OUT = sys.argv[1]
SURFACE, INK, INK2, MUTED, LINE = "#ffffff", "#0b0b0b", "#52514e", "#898781", "#c3c2b7"
BLUE, BLUE_TINT, BLUE_DARK = "#2a78d6", "#eef4fc", "#1c5cab"
ORANGE, ORANGE_TINT, ORANGE_DARK = "#eb6834", "#fdf0ea", "#b4441a"
GRAY_TINT = "#f0efec"

plt.rcParams.update({"font.family": "Malgun Gothic", "axes.unicode_minus": False})
fig, ax = plt.subplots(figsize=(16, 9.6))
fig.patch.set_facecolor(SURFACE)
ax.set_xlim(0, 130)
ax.set_ylim(-3, 76)
ax.axis("off")


def box(cx, cy, w, h, title, sub=None, fill=GRAY_TINT, edge=LINE, title_color=INK, title_size=17, sub_size=12.5, tag=None, tag_color=MUTED):
    ax.add_patch(FancyBboxPatch((cx - w / 2, cy - h / 2), w, h, boxstyle="round,pad=0,rounding_size=1.6",
                                facecolor=fill, edgecolor=edge, linewidth=1.6))
    if sub:
        ty = cy + h / 2 - 2.6
        ax.text(cx, ty, title, ha="center", va="center", fontsize=title_size, fontweight="bold", color=title_color)
        ax.text(cx, ty - 2.4, sub, ha="center", va="top", fontsize=sub_size, color=INK2, linespacing=1.5)
    else:
        ax.text(cx, cy, title, ha="center", va="center", fontsize=title_size, fontweight="bold", color=title_color)
    if tag:
        ax.text(cx, cy + h / 2 + 1.6, tag, ha="center", va="bottom", fontsize=12, color=tag_color, fontweight="bold")


def arrow(x1, y1, x2, y2, color=MUTED, label=None, lx=None, ly=None, lcolor=None):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=18, linewidth=2,
                                 color=color, shrinkA=0, shrinkB=0, connectionstyle="arc3,rad=0"))
    if label:
        ax.text(lx, ly, label, ha="center", va="center", fontsize=13, fontweight="bold", color=lcolor or color,
                bbox=dict(facecolor=SURFACE, edgecolor="none", pad=2))


def elbow(points, color, label=None, lpos=None):
    xs, ys = zip(*points)
    ax.plot(xs[:-1], ys[:-1], color=color, linewidth=2, solid_capstyle="round")
    arrow(xs[-2], ys[-2], xs[-1], ys[-1], color=color)
    if label:
        ax.text(*lpos, label, ha="center", va="center", fontsize=13, fontweight="bold", color=color,
                bbox=dict(facecolor=SURFACE, edgecolor="none", pad=2))


# start
box(65, 70, 44, 7, "원소들을 섞어 녹였다가 굳힌다", fill=GRAY_TINT, title_size=16)
arrow(65, 66.5, 65, 61.2)

# fork 1
box(65, 55.5, 62, 11, "갈림길 1 · 원자들이 아무 자리에나 고르게 섞이나?",
    "결정 변수:  ΔHmix (원소끼리의 친밀도) · δ (원자 크기 차이)\nΔχ (전기음성도 차이) · ΔSmix (섞임의 무질서도) · 원소 개수",
    fill=SURFACE, edge=INK2, title_size=16, sub_size=12.5)

# no -> intermetallic (right)
elbow([(96, 55.5), (113, 55.5), (113, 46)], ORANGE_DARK, "아니오", (104.5, 55.5))
box(113, 39, 30, 14, "금속간화합물 (Im)", "특정 원자끼리\n정해진 자리에 짝지어 앉음\n→ 매우 단단하지만 깨지기 쉬움",
    fill=ORANGE_TINT, edge=ORANGE, title_color=ORANGE_DARK, sub_size=12)

# yes -> solid solution (down)
arrow(65, 50, 65, 44.3, color=BLUE_DARK, label="예", lx=67.8, ly=47.2, lcolor=BLUE_DARK)
box(65, 40.5, 34, 7.2, "고용체 (Solid Solution)", fill=BLUE_TINT, edge=BLUE, title_color=BLUE_DARK, title_size=16)
arrow(65, 36.9, 65, 32.2, color=BLUE_DARK)

# fork 2
box(65, 27.5, 52, 9.5, "갈림길 2 · 원자들이 어떤 모양으로 쌓이나?", "결정 변수:  VEC (원자당 가전자 수)",
    fill=SURFACE, edge=INK2, title_size=16, sub_size=12)

# three leaves
leaves = [
    (24, "BCC (체심입방)", "덜 빽빽하게 쌓임\n→ 단단하지만 잘 깨짐", "VEC < 6.87"),
    (65, "FCC + BCC", "두 구조가 섞임", "6.87 ≤ VEC < 8"),
    (106, "FCC (면심입방)", "빽빽하게 쌓임\n→ 잘 늘어나고 질김", "VEC ≥ 8"),
]
for x, t, sub, rule in leaves:
    if x == 65:
        arrow(65, 23, 65, 15.6, color=BLUE_DARK)
    else:
        elbow([(65 + (-26 if x < 65 else 26), 27.5), (x, 27.5), (x, 15.6)], BLUE_DARK)
    box(x, 10, 31, 11.2, t, sub, fill=BLUE_TINT, edge=BLUE, title_color=BLUE_DARK, sub_size=12.5)
    ax.text(x + 1.2, 19.2, rule, ha="left", va="center", fontsize=12.5, fontweight="bold", color=BLUE_DARK)

ax.text(1, -2, "VEC 경계값: Guo et al. (2011). 실제 합금은 경계 근처에서 예외가 있다.", fontsize=10, color=MUTED, ha="left")
fig.savefig(OUT, dpi=200, bbox_inches="tight", facecolor=SURFACE)
print("saved", OUT)
