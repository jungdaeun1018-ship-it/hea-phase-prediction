"""High-entropy alloy phase analysis.

Usage: python -I analyze_hea.py <csv_path> <out_dir>
Writes figures to <out_dir>/img and numbers to <out_dir>/results.json.
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from imblearn.over_sampling import SMOTE
from imblearn.pipeline import make_pipeline as make_imb_pipeline
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score
from sklearn.model_selection import (StratifiedKFold, cross_val_predict,
                                     cross_validate, train_test_split)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

CSV, OUT = Path(sys.argv[1]), Path(sys.argv[2])
IMG = OUT / "img"
IMG.mkdir(parents=True, exist_ok=True)
SEED = 42

# Reference palette (dataviz skill, light mode)
SURFACE, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
SEQ = ["#fcfcfb", "#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"]

PHASES = ["BCC_SS", "FCC_SS", "FCC_PLUS_BCC", "Im"]
PHASE_KO = {"BCC_SS": "BCC 고용체", "FCC_SS": "FCC 고용체", "FCC_PLUS_BCC": "FCC+BCC", "Im": "금속간화합물(Im)"}
BASE_FEATURES = ["Num_of_Elem", "VEC", "Atom.Size.Diff", "Elect.Diff", "dHmix", "dSmix"]
EXTRA_FEATURES = ["Tm", "n.Para", "Density_calc"]
FEATURE_KO = {
    "VEC": "VEC (가전자 농도)", "Atom.Size.Diff": "원자 크기 차이 δ", "Elect.Diff": "전기음성도 차이",
    "dHmix": "혼합 엔탈피 ΔHmix", "dSmix": "혼합 엔트로피 ΔSmix", "Num_of_Elem": "원소 개수",
    "Tm": "평균 녹는점 Tm", "n.Para": "Ω 파라미터", "Density_calc": "밀도",
}

plt.rcParams.update({
    "font.family": "Malgun Gothic", "axes.unicode_minus": False, "font.size": 12,
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": AXIS, "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": MUTED,
    "text.color": INK, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
    "axes.spines.top": False, "axes.spines.right": False, "axes.axisbelow": True,
})


def save(fig, name):
    fig.savefig(IMG / f"{name}.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


# ---------- 1. Load & filter ----------
raw = pd.read_csv(CSV, encoding="cp1252")
raw.columns = raw.columns.str.strip()
raw["Alloy"] = raw["Alloy"].str.strip()
raw = raw.dropna(subset=["Phases"])

as_cast = raw[(raw["Sythesis_Route"] == "AC")
              & raw["Hot-Cold_Working"].isna()
              & raw["Homogenization_Temp"].isna()
              & raw["Annealing_Temp"].isna()
              & raw["HPR"].isna()]
df = as_cast.drop_duplicates(subset="Alloy").reset_index(drop=True)
features = BASE_FEATURES + EXTRA_FEATURES
df = df.dropna(subset=features)

res = {"n_raw": len(raw), "n_as_cast": len(as_cast), "n_final": len(df),
       "phase_counts": df["Phases"].value_counts().reindex(PHASES).to_dict()}

# element frequency
elements = [c for c in raw.columns[2:27]]
elem_freq = (df[elements] > 0).sum().sort_values(ascending=False)
res["top_elements"] = elem_freq.head(10).to_dict()

# ---------- 2. EDA figures ----------
# 2a phase counts (single series)
fig, ax = plt.subplots(figsize=(7, 3.6))
counts = [res["phase_counts"][p] for p in PHASES]
bars = ax.barh([PHASE_KO[p] for p in PHASES][::-1], counts[::-1], color=BLUE, height=0.6)
for b, v in zip(bars, counts[::-1]):
    ax.text(v + 3, b.get_y() + b.get_height() / 2, f"{v}", va="center", color=INK2, fontsize=11)
ax.set_xlabel("합금 수")
ax.grid(axis="y", visible=False)
save(fig, "phase_counts")

# 2b element frequency
fig, ax = plt.subplots(figsize=(7, 3.6))
top = elem_freq.head(12)
ax.bar(top.index, top.values, color=BLUE, width=0.6)
ax.set_ylabel("포함된 합금 수")
ax.grid(axis="x", visible=False)
save(fig, "element_freq")

# 2c VEC by phase: strip + median, with empirical thresholds
fig, ax = plt.subplots(figsize=(8, 4))
rng = np.random.default_rng(SEED)
for i, p in enumerate(PHASES):
    v = df.loc[df["Phases"] == p, "VEC"]
    ax.scatter(v, i + rng.uniform(-0.22, 0.22, len(v)), s=14, color=BLUE, alpha=0.45, linewidths=0)
    ax.plot([v.median()] * 2, [i - 0.32, i + 0.32], color=INK, lw=2)
for x, lab in [(6.87, "6.87"), (8.0, "8.0")]:
    ax.axvline(x, color=ORANGE, lw=1.5, ls="--")
    ax.text(x, len(PHASES) - 0.45, f"VEC {lab}", color=INK2, fontsize=10, ha="center",
            bbox=dict(facecolor=SURFACE, edgecolor="none", pad=1))
ax.set_yticks(range(len(PHASES)), [PHASE_KO[p] for p in PHASES])
ax.set_xlabel("VEC (가전자 농도)")
ax.grid(axis="y", visible=False)
save(fig, "vec_by_phase")
res["vec_median"] = df.groupby("Phases")["VEC"].median().reindex(PHASES).round(2).to_dict()

# 2d delta vs dHmix, faceted by phase, with Guo & Liu (2011) solid-solution window
fig, axes = plt.subplots(1, 4, figsize=(13, 3.8), sharex=True, sharey=True)
for ax, p in zip(axes, PHASES):
    rest = df[df["Phases"] != p]
    sub = df[df["Phases"] == p]
    ax.scatter(rest["Atom.Size.Diff"], rest["dHmix"], s=8, color=AXIS, alpha=0.5, linewidths=0)
    ax.scatter(sub["Atom.Size.Diff"], sub["dHmix"], s=14, color=BLUE, alpha=0.7, linewidths=0)
    ax.add_patch(plt.Rectangle((0, -11.6), 6.6, 3.2 + 11.6, fill=False, ec=ORANGE, lw=1.5, ls="--"))
    ax.set_title(f"{PHASE_KO[p]} (n={len(sub)})", fontsize=12, color=INK)
    ax.set_xlabel("원자 크기 차이 δ (%)")
axes[0].set_ylabel("ΔHmix (kJ/mol)")
save(fig, "delta_dh_facets")

inside = (df["Atom.Size.Diff"] <= 6.6) & df["dHmix"].between(-11.6, 3.2)
ss = df["Phases"] != "Im"
res["guo_window"] = {
    "ss_inside_pct": round(100 * (inside & ss).sum() / ss.sum(), 1),
    "im_inside_pct": round(100 * (inside & ~ss).sum() / (~ss).sum(), 1),
}

# ---------- 3. Models ----------
X, y = df[features], df["Phases"]
Xb = df[BASE_FEATURES]
cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED)


def vec_rule(v):
    return np.where(v >= 8.0, "FCC_SS", np.where(v < 6.87, "BCC_SS", "FCC_PLUS_BCC"))


rule_pred = vec_rule(df["VEC"].values)
res["vec_rule"] = {"accuracy": round(accuracy_score(y, rule_pred), 3),
                   "macro_f1": round(f1_score(y, rule_pred, average="macro"), 3)}
nonim = y != "Im"
res["vec_rule_non_im_accuracy"] = round(accuracy_score(y[nonim], rule_pred[nonim]), 3)

models = {
    "로지스틱 회귀": make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000)),
    "랜덤포레스트": RandomForestClassifier(n_estimators=400, random_state=SEED),
    "그래디언트 부스팅": GradientBoostingClassifier(random_state=SEED),
}
res["models"] = {}
for name, m in models.items():
    for fset, Xs in [("base6", Xb), ("ext9", X)]:
        s = cross_validate(m, Xs, y, cv=cv, scoring=["accuracy", "f1_macro"])
        res["models"].setdefault(name, {})[fset] = {
            "accuracy": round(s["test_accuracy"].mean(), 3), "acc_std": round(s["test_accuracy"].std(), 3),
            "macro_f1": round(s["test_f1_macro"].mean(), 3)}

# SMOTE: notebook way (oversample before split = leakage) vs inside CV
Xs_leak, ys_leak = SMOTE(random_state=SEED).fit_resample(Xb, y)
Xtr, Xte, ytr, yte = train_test_split(Xs_leak, ys_leak, test_size=0.3, random_state=SEED)
leak_acc = accuracy_score(yte, RandomForestClassifier(n_estimators=400, random_state=SEED).fit(Xtr, ytr).predict(Xte))
proper = cross_validate(make_imb_pipeline(SMOTE(random_state=SEED), RandomForestClassifier(n_estimators=400, random_state=SEED)),
                        Xb, y, cv=cv, scoring=["accuracy", "f1_macro"])
res["smote"] = {"leaky_split_accuracy": round(leak_acc, 3),
                "proper_cv_accuracy": round(proper["test_accuracy"].mean(), 3),
                "proper_cv_macro_f1": round(proper["test_f1_macro"].mean(), 3),
                "no_smote_cv_accuracy": res["models"]["랜덤포레스트"]["base6"]["accuracy"]}

# figure: model comparison (accuracy, single series + rule baseline)
labels = ["VEC 규칙\n(기준선)"] + [n.replace(" ", "\n") for n in models]
accs = [res["vec_rule"]["accuracy"]] + [res["models"][n]["base6"]["accuracy"] for n in models]
errs = [0] + [res["models"][n]["base6"]["acc_std"] for n in models]
fig, ax = plt.subplots(figsize=(7.5, 4))
colors = [AXIS] + [BLUE] * len(models)
bars = ax.bar(labels, accs, color=colors, width=0.55, yerr=errs, ecolor=INK2, capsize=4)
for b, v in zip(bars, accs):
    ax.text(b.get_x() + b.get_width() / 2, v + 0.03, f"{v:.0%}", ha="center", color=INK, fontsize=12, fontweight="bold")
ax.set_ylim(0, 1)
ax.set_ylabel("정확도 (5-fold 교차검증)")
ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
ax.grid(axis="x", visible=False)
save(fig, "model_compare")

# figure: SMOTE leakage
fig, ax = plt.subplots(figsize=(7.5, 3.6))
sm_labels = ["SMOTE 없음\n(교차검증)", "SMOTE 후 분할\n(참고 노트북 방식)", "분할 후 SMOTE\n(교차검증)"]
sm_vals = [res["smote"]["no_smote_cv_accuracy"], res["smote"]["leaky_split_accuracy"], res["smote"]["proper_cv_accuracy"]]
bars = ax.bar(sm_labels, sm_vals, color=[BLUE, ORANGE, BLUE], width=0.55)
for b, v in zip(bars, sm_vals):
    ax.text(b.get_x() + b.get_width() / 2, v + 0.02, f"{v:.0%}", ha="center", color=INK, fontsize=12, fontweight="bold")
ax.set_ylim(0, 1)
ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
ax.set_ylabel("랜덤포레스트 정확도")
ax.grid(axis="x", visible=False)
save(fig, "smote_leak")

# best model: confusion matrix + permutation importance
best = RandomForestClassifier(n_estimators=400, random_state=SEED)
pred = cross_val_predict(best, Xb, y, cv=cv)
cm = confusion_matrix(y, pred, labels=PHASES)
cm_norm = cm / cm.sum(axis=1, keepdims=True)
res["per_class_recall"] = {p: round(cm_norm[i, i], 3) for i, p in enumerate(PHASES)}
fig, ax = plt.subplots(figsize=(6.2, 5))
cmap = matplotlib.colors.LinearSegmentedColormap.from_list("seq", SEQ)
ax.imshow(cm_norm, cmap=cmap, vmin=0, vmax=1)
for i in range(4):
    for j in range(4):
        ax.text(j, i, f"{cm_norm[i, j]:.0%}\n({cm[i, j]})", ha="center", va="center", fontsize=10,
                color="white" if cm_norm[i, j] > 0.55 else INK)
short = ["BCC", "FCC", "FCC+BCC", "Im"]
ax.set_xticks(range(4), short)
ax.set_yticks(range(4), short)
ax.set_xlabel("예측한 상")
ax.set_ylabel("실제 상")
ax.grid(False)
for s in ax.spines.values():
    s.set_visible(False)
save(fig, "confusion")

fold_imps = []
for tr, te in cv.split(Xb, y):
    best.fit(Xb.iloc[tr], y.iloc[tr])
    fold_imps.append(permutation_importance(best, Xb.iloc[te], y.iloc[te], n_repeats=20,
                                            random_state=SEED).importances_mean)
imp = pd.Series(np.mean(fold_imps, axis=0), index=BASE_FEATURES).sort_values()
res["importance"] = imp.round(4)[::-1].to_dict()
fig, ax = plt.subplots(figsize=(7.5, 4))
ax.barh([FEATURE_KO[f] for f in imp.index], imp.values, color=BLUE, height=0.6)
ax.set_xlabel("정확도 감소량 (순열 중요도)")
ax.grid(axis="y", visible=False)
save(fig, "importance")

(OUT / "results.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(res, ensure_ascii=False, indent=2))
