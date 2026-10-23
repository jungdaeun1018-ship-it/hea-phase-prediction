"""High-entropy alloy phase analysis.

Usage: python -I analyze_hea.py <csv_path> <out_dir>
Writes figures to <out_dir>/img and numbers to <out_dir>/results.json.

Order follows the course: diagnose -> clean (with a log) -> describe -> model.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from alloy_formula import key, parse  # noqa: E402

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
BLUE, ORANGE = "#2a78d6", "#eb6834"
SEQ = ["#fcfcfb", "#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"]

PHASES = ["BCC_SS", "FCC_SS", "FCC_PLUS_BCC", "Im"]
PHASE_KO = {"BCC_SS": "BCC 고용체", "FCC_SS": "FCC 고용체", "FCC_PLUS_BCC": "FCC+BCC", "Im": "금속간화합물(Im)"}
FEATURES = ["Num_of_Elem", "VEC", "Atom.Size.Diff", "Elect.Diff", "dHmix", "dSmix"]
FEATURE_KO = {
    "VEC": "VEC (가전자 농도)", "Atom.Size.Diff": "원자 크기 차이 δ (%)", "Elect.Diff": "전기음성도 차이 Δχ",
    "dHmix": "혼합 엔탈피 ΔHmix (kJ/mol)", "dSmix": "혼합 엔트로피 ΔSmix (J/K·mol)", "Num_of_Elem": "원소 개수",
}
PROCESS_COLS = ["Hot-Cold_Working", "Homogenization_Temp", "Annealing_Temp", "HPR"]
# Pauling electronegativity, used to re-derive Elect.Diff from the composition columns
PAULING = {"Al": 1.61, "Co": 1.88, "Cr": 1.66, "Fe": 1.83, "Ni": 1.91, "Cu": 1.90, "Mn": 1.55, "Ti": 1.54,
           "V": 1.63, "Nb": 1.60, "Mo": 2.16, "Zr": 1.33, "Hf": 1.30, "Ta": 1.50, "W": 2.36, "C": 2.55,
           "Mg": 1.31, "Zn": 1.65, "Si": 1.90, "Re": 1.90, "N": 3.04, "Sc": 1.36, "Li": 0.98, "Sn": 1.96,
           "Be": 1.57}
VEC_E = {"Al": 3, "Co": 9, "Cr": 6, "Fe": 8, "Ni": 10, "Cu": 11, "Mn": 7, "Ti": 4, "V": 5, "Nb": 5, "Mo": 6,
         "Zr": 4, "Hf": 4, "Ta": 5, "W": 6, "C": 4, "Mg": 2, "Zn": 12, "Si": 4, "Re": 7, "N": 5, "Sc": 3,
         "Li": 1, "Sn": 4, "Be": 2}
R = 8.314  # J/(K·mol); operational definition of HEA/MEA: dSmix >= 1R


def confident(name):
    """False for mixed notation like 'NbTaTi30Zr' (Ti = 30 at.%, others implicit), which cannot be read safely."""
    s = name.replace(" ", "")
    if "(" in s:
        return True
    nums = re.findall(r"[A-Z][a-z]?(\d*\.?\d*)", s)
    explicit = [float(n) for n in nums if n]
    implicit = sum(1 for n in nums if not n)
    return not (implicit and explicit and max(explicit) > 5)

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


res = {}

# ---------- 1. Diagnose (no changes yet) ----------
try:
    pd.read_csv(CSV)
    res["encoding"] = "utf-8"
except UnicodeDecodeError:
    res["encoding"] = "cp1252 (utf-8 실패)"
raw = pd.read_csv(CSV, encoding="cp1252")
raw.columns = raw.columns.str.strip()
raw["Alloy"] = raw["Alloy"].str.strip()
res["raw_shape"] = list(raw.shape)
res["exact_duplicate_rows"] = int(raw.duplicated().sum())
res["alloy_name_repeats"] = int(raw["Alloy"].duplicated().sum())
res["unique_alloys_raw"] = int(raw["Alloy"].nunique())
diag_cols = FEATURES + ["Phases", "Sythesis_Route"] + PROCESS_COLS
res["diagnosis"] = [{
    "column": c, "dtype": str(raw[c].dtype), "missing": int(raw[c].isna().sum()),
    "unique": int(raw[c].nunique()),
} for c in diag_cols]

# ---------- 2. Clean, logging every rule ----------
log = []


def step(df_before, df_after, rule, reason):
    log.append({"rule": rule, "before": len(df_before), "after": len(df_after),
                "removed": len(df_before) - len(df_after), "reason": reason})
    return df_after


d = raw.copy()
d = step(d, d.dropna(subset=["Phases"] + FEATURES), "상·입력변수가 빈 행 제외",
         "값이 하나도 없는 빈 행 (CSV 끝의 빈 줄)")

# verify the given features against the alloy name, the primary source.
# dSmix depends only on composition, so it tells whether the original authors used the right composition:
#   dSmix matches -> composition was right, a VEC/dchi mismatch is a typo -> correct that value
#   dSmix differs -> every feature was computed from a wrong composition (dHmix, delta too) -> drop the row
d = d.copy()
d["comp"] = [parse(a) if confident(a) else None for a in d["Alloy"]]
status, n_vec, n_chi, examples = [], 0, 0, []
for i, c in d["comp"].items():
    if c is None:
        status.append("unverifiable")
        continue
    s_name = -R * sum(x * np.log(x) for x in c.values() if x > 0)
    if abs(d.at[i, "dSmix"] - s_name) > 0.15:
        status.append("wrong_comp")
        continue
    status.append("ok")
    v_name = sum(x * VEC_E[e] for e, x in c.items())
    m = sum(x * PAULING[e] for e, x in c.items())
    chi_name = np.sqrt(sum(x * (PAULING[e] - m) ** 2 for e, x in c.items()))
    if abs(d.at[i, "VEC"] - v_name) > 0.05:
        if len(examples) < 6:
            examples.append({"alloy": d.at[i, "Alloy"], "feature": "VEC", "given": round(float(d.at[i, "VEC"]), 2),
                             "from_name": round(v_name, 2)})
        d.at[i, "VEC"] = v_name
        n_vec += 1
    if abs(d.at[i, "Elect.Diff"] - chi_name) > 0.05:
        d.at[i, "Elect.Diff"] = chi_name
        n_chi += 1
d["status"] = status
res["name_check"] = {"ok": status.count("ok"), "wrong_comp": status.count("wrong_comp"),
                     "unverifiable": status.count("unverifiable"), "vec_fixed": n_vec, "chi_fixed": n_chi,
                     "examples": examples,
                     "wrong_comp_examples": d.loc[d["status"] == "wrong_comp", "Alloy"].drop_duplicates().head(6).tolist()}
log.append({"rule": "이름으로 VEC·Δχ 검증 후 오타 교정", "before": len(d), "after": len(d), "removed": 0,
            "reason": f"합금 이름(화학식)으로 다시 계산. VEC {n_vec}행, Δχ {n_chi}행 교정 "
                      f"(예: NbTiZr VEC 4.67 → 4.33, TiZrNbTa Δχ 3.92 → 0.10)"})
d = step(d, d[d["status"] != "wrong_comp"], "잘못된 조성으로 계산된 행 제외",
         "ΔSmix까지 이름과 다름 → 원저자가 틀린 조성으로 모든 변수를 계산(예: MoNbTaTiW는 5원소인데 4원소 값)")
d["key"] = [key(c) if c else a for c, a in zip(d["comp"], d["Alloy"])]

d = step(d, d[d["dSmix"] >= R], "조작적 정의: ΔSmix ≥ 1R(8.31)",
         "고·중엔트로피합금만 분석. Al 90% 합금 같은 일반 합금 제외")
d = step(d, d[d["Sythesis_Route"] == "AC"], "주조(AC) 합금만",
         "분말야금(PM)은 제조 경로가 달라 상이 달라질 수 있음")
d = step(d, d[d[PROCESS_COLS].isna().all(axis=1)], "가공·열처리 기록이 없는 행만",
         "빈칸 = ‘처리하지 않음’. 열처리는 상을 바꾸므로 주조 직후 상태로 통일")
res["name_variants"] = int((d.groupby("key")["Alloy"].nunique() > 1).sum())
conflict = d.groupby("key")["Phases"].nunique()
conflict = conflict[conflict > 1].index
res["conflicting_alloys"] = int(len(conflict))
res["conflict_examples"] = (d[d["key"].isin(conflict)].groupby("key")
                            .agg(names=("Alloy", lambda s: sorted(set(s))), phases=("Phases", lambda s: sorted(set(s))))
                            .head(4).to_dict("records"))
keep_first = d.drop_duplicates(subset="key")  # previous rule, kept for the sensitivity check
d = step(d, d[~d["key"].isin(conflict)], "논문마다 상이 다른 합금 제외",
         f"같은 조성인데 논문마다 상이 다름({len(conflict)}종) → 정답 라벨을 정할 수 없음")
d = step(d, d.drop_duplicates(subset="key"), "같은 조성은 1행만",
         "이름 표기 순서가 달라도(AlCrFeCoNi = AlCoCrFeNi) 같은 조성이면 한 합금으로 셈")
log.append({"rule": "이상치는 지우지 않음", "before": len(d), "after": len(d), "removed": 0,
            "reason": "극단값(δ 16.9%, ΔHmix −39)도 실제 합금의 계산값. 입력 오류 근거 없음"})
log.append({"rule": "결측 대치 안 함", "before": len(d), "after": len(d), "removed": 0,
            "reason": "평균 대치는 표준편차를 줄여 데이터를 실제보다 고르게 만듦"})
df = d.reset_index(drop=True)
res["cleaning_log"] = log
res["n_final"] = len(df)
res["phase_counts"] = df["Phases"].value_counts().reindex(PHASES).to_dict()

# ---------- 3. Describe ----------
desc = []
for f in FEATURES:
    s = df[f]
    imin, imax = s.idxmin(), s.idxmax()
    desc.append({
        "feature": f, "n": int(s.count()), "mean": round(s.mean(), 2), "median": round(s.median(), 2),
        "std": round(s.std(), 2), "min": round(s.min(), 2), "min_alloy": df.at[imin, "Alloy"],
        "max": round(s.max(), 2), "max_alloy": df.at[imax, "Alloy"], "skew": round(s.skew(), 2),
        "mean_minus_median_in_sd": round((s.mean() - s.median()) / s.std(), 2),
    })
res["descriptive"] = desc

grp = df.groupby("Phases")[["VEC", "dHmix", "Atom.Size.Diff"]].agg(["count", "mean", "median", "std"]).reindex(PHASES)
res["by_phase"] = {p: {f"{c}_{s}": round(float(grp.loc[p, (c, s)]), 2) for c in ["VEC", "dHmix", "Atom.Size.Diff"]
                       for s in ["count", "mean", "median", "std"]} for p in PHASES}

# 3a histograms (25 bins) with mean/median markers
fig, axes = plt.subplots(2, 3, figsize=(13, 6.6))
for ax, f in zip(axes.flat, FEATURES):
    s = df[f]
    bins = np.arange(s.min() - 0.5, s.max() + 1.5, 1) if f == "Num_of_Elem" else 25
    ax.hist(s, bins=bins, color=BLUE, edgecolor=SURFACE, linewidth=0.8)
    ax.axvline(s.mean(), color=INK, lw=1.8, label="평균")
    ax.axvline(s.median(), color=ORANGE, lw=1.8, ls="--", label="중앙값")
    ax.set_title(FEATURE_KO[f], fontsize=12, color=INK)
    ax.grid(axis="x", visible=False)
axes[0, 0].legend(frameon=False, fontsize=10)
for ax in axes[:, 0]:
    ax.set_ylabel("합금 수")
fig.tight_layout()
save(fig, "histograms")

# 3b phase counts (single series)
fig, ax = plt.subplots(figsize=(7, 3.6))
counts = [res["phase_counts"][p] for p in PHASES]
bars = ax.barh([PHASE_KO[p] for p in PHASES][::-1], counts[::-1], color=BLUE, height=0.6)
for b, v in zip(bars, counts[::-1]):
    ax.text(v + 3, b.get_y() + b.get_height() / 2, f"{v}", va="center", color=INK2, fontsize=11)
ax.set_xlabel("합금 수")
ax.grid(axis="y", visible=False)
save(fig, "phase_counts")

# 3c VEC by phase: strip + median, with empirical thresholds
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

# 3d delta vs dHmix, faceted by phase, with Guo & Liu (2011) solid-solution window
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

# ---------- 4. Models ----------
X, y = df[FEATURES], df["Phases"]
cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED)


def vec_rule(v):
    return np.where(v >= 8.0, "FCC_SS", np.where(v < 6.87, "BCC_SS", "FCC_PLUS_BCC"))


rule_pred = vec_rule(df["VEC"].values)
res["vec_rule"] = {"accuracy": round(accuracy_score(y, rule_pred), 3),
                   "macro_f1": round(f1_score(y, rule_pred, average="macro"), 3)}
nonim = y != "Im"
res["vec_rule_non_im_accuracy"] = round(accuracy_score(y[nonim], rule_pred[nonim]), 3)
res["majority_baseline"] = round(y.value_counts(normalize=True).max(), 3)

models = {
    "로지스틱 회귀": make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000)),
    "랜덤포레스트": RandomForestClassifier(n_estimators=400, random_state=SEED),
    "그래디언트 부스팅": GradientBoostingClassifier(random_state=SEED),
}
res["models"] = {}
for name, m in models.items():
    s = cross_validate(m, X, y, cv=cv, scoring=["accuracy", "f1_macro"])
    res["models"][name] = {"accuracy": round(s["test_accuracy"].mean(), 3), "acc_std": round(s["test_accuracy"].std(), 3),
                           "macro_f1": round(s["test_f1_macro"].mean(), 3)}

# McFadden pseudo-R^2 = 1 - logloss(model) / logloss(class-frequency model), both on held-out folds.
# R^2 itself is a regression metric; this is its usual analogue for classifiers (0 = no better than guessing by frequency).
for name, m in models.items():
    ll_model = ll_null = 0.0
    for tr, te in cv.split(X, y):
        m.fit(X.iloc[tr], y.iloc[tr])
        proba = np.clip(m.predict_proba(X.iloc[te]), 1e-15, 1)
        idx = np.searchsorted(m.classes_, y.iloc[te])
        ll_model += -np.log(proba[np.arange(len(te)), idx]).sum()
        prior = y.iloc[tr].value_counts(normalize=True).reindex(m.classes_).values
        ll_null += -np.log(prior[idx]).sum()
    res["models"][name]["pseudo_r2"] = round(1 - ll_model / ll_null, 3)

fig, ax = plt.subplots(figsize=(7.5, 4))
names = list(models)
vals = [res["models"][n]["pseudo_r2"] for n in names]
bars = ax.bar([n.replace(" ", "\n") for n in names], vals, color=BLUE, width=0.5)
for b, v in zip(bars, vals):
    ax.text(b.get_x() + b.get_width() / 2, v + 0.02, f"{v:.2f}", ha="center", color=INK, fontsize=13, fontweight="bold")
ax.set_ylim(0, 1)
ax.set_ylabel("McFadden 의사 R² (교차검증)")
ax.grid(axis="x", visible=False)
save(fig, "pseudo_r2")

# sensitivity: does the conflict rule change the answer?
kf = keep_first
s_kf = cross_validate(RandomForestClassifier(n_estimators=400, random_state=SEED), kf[FEATURES], kf["Phases"],
                      cv=cv, scoring=["accuracy", "f1_macro"])
res["sensitivity"] = {"keep_first_n": len(kf), "keep_first_accuracy": round(s_kf["test_accuracy"].mean(), 3),
                      "exclude_conflict_n": len(df), "exclude_conflict_accuracy": res["models"]["랜덤포레스트"]["accuracy"]}

# SMOTE: notebook way (oversample before split = leakage) vs inside CV
Xs_leak, ys_leak = SMOTE(random_state=SEED).fit_resample(X, y)
Xtr, Xte, ytr, yte = train_test_split(Xs_leak, ys_leak, test_size=0.3, random_state=SEED)
leak_acc = accuracy_score(yte, RandomForestClassifier(n_estimators=400, random_state=SEED).fit(Xtr, ytr).predict(Xte))
proper = cross_validate(make_imb_pipeline(SMOTE(random_state=SEED), RandomForestClassifier(n_estimators=400, random_state=SEED)),
                        X, y, cv=cv, scoring=["accuracy", "f1_macro"])
res["smote"] = {"leaky_split_accuracy": round(leak_acc, 3),
                "proper_cv_accuracy": round(proper["test_accuracy"].mean(), 3),
                "proper_cv_macro_f1": round(proper["test_f1_macro"].mean(), 3),
                "no_smote_cv_accuracy": res["models"]["랜덤포레스트"]["accuracy"]}

# figure: model comparison
labels = ["VEC 규칙\n(기준선)"] + [n.replace(" ", "\n") for n in models]
accs = [res["vec_rule"]["accuracy"]] + [res["models"][n]["accuracy"] for n in models]
errs = [0] + [res["models"][n]["acc_std"] for n in models]
fig, ax = plt.subplots(figsize=(7.5, 4))
bars = ax.bar(labels, accs, color=[AXIS] + [BLUE] * len(models), width=0.55, yerr=errs, ecolor=INK2, capsize=4)
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
pred = cross_val_predict(best, X, y, cv=cv)
cm = confusion_matrix(y, pred, labels=PHASES)
cm_norm = cm / cm.sum(axis=1, keepdims=True)
res["per_class_recall"] = {p: round(cm_norm[i, i], 3) for i, p in enumerate(PHASES)}
res["fccbcc_to_im"] = round(cm_norm[2, 3], 3)
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
for tr, te in cv.split(X, y):
    best.fit(X.iloc[tr], y.iloc[tr])
    fold_imps.append(permutation_importance(best, X.iloc[te], y.iloc[te], n_repeats=20,
                                            random_state=SEED).importances_mean)
imp = pd.Series(np.mean(fold_imps, axis=0), index=FEATURES).sort_values()
res["importance"] = imp.round(4)[::-1].to_dict()
fig, ax = plt.subplots(figsize=(7.5, 4))
ax.barh([FEATURE_KO[f] for f in imp.index], imp.values, color=BLUE, height=0.6)
ax.set_xlabel("정확도 감소량 (순열 중요도)")
ax.grid(axis="y", visible=False)
save(fig, "importance")

# ---------- 5. SHAP (explains the random forest fitted on all 289 alloys) ----------
import shap  # noqa: E402

rf = RandomForestClassifier(n_estimators=400, random_state=SEED).fit(X, y)
sv = np.asarray(shap.TreeExplainer(rf).shap_values(X))  # (n, features, classes)
if sv.shape[0] == len(rf.classes_):
    sv = np.moveaxis(sv, 0, -1)
cls = list(rf.classes_)
mean_abs = pd.DataFrame({p: np.abs(sv[:, :, cls.index(p)]).mean(axis=0) for p in PHASES}, index=FEATURES)
res["shap_mean_abs"] = mean_abs.round(4).to_dict()
res["shap_rank_overall"] = mean_abs.sum(axis=1).sort_values(ascending=False).round(4).to_dict()

# 5a mean |SHAP| per phase, grouped bars (categorical slots 1-4 in fixed order)
CAT = {"BCC_SS": BLUE, "FCC_SS": "#1baf7a", "FCC_PLUS_BCC": "#eda100", "Im": ORANGE}
order = mean_abs.sum(axis=1).sort_values().index
fig, ax = plt.subplots(figsize=(8.5, 4.6))
yy = np.arange(len(order))
hh = 0.19
for k, p in enumerate(PHASES):
    ax.barh(yy + (k - 1.5) * hh, mean_abs.loc[order, p], height=hh - 0.02, color=CAT[p], label=PHASE_KO[p])
ax.set_yticks(yy, [FEATURE_KO[f] for f in order])
ax.set_xlabel("평균 |SHAP| (상 확률에 대한 기여 크기)")
ax.legend(frameon=False, fontsize=10, loc="lower right")
ax.grid(axis="y", visible=False)
save(fig, "shap_by_phase")

# 5b direction: VEC -> FCC / BCC, dHmix -> Im
fig, axes = plt.subplots(1, 3, figsize=(13, 3.9))
for ax, (f, p) in zip(axes, [("VEC", "FCC_SS"), ("VEC", "BCC_SS"), ("dHmix", "Im")]):
    ax.scatter(X[f], sv[:, FEATURES.index(f), cls.index(p)], s=12, color=CAT[p], alpha=0.6, linewidths=0)
    ax.axhline(0, color=AXIS, lw=1)
    ax.set_xlabel(FEATURE_KO[f])
    ax.set_title(f"{PHASE_KO[p]} 확률에 대한 SHAP", fontsize=12, color=INK)
axes[0].set_ylabel("SHAP 값 (+ 이면 그 상 쪽으로)")
fig.tight_layout()
save(fig, "shap_dependence")

# 5c one alloy: an Al-containing BCC alloy above the VEC 6.87 rule
cand = df[(df["Phases"] == "BCC_SS") & (df["VEC"] >= 6.87) & (df["Al"] > 0)]
if len(cand):
    i = cand.index[cand["Alloy"].eq("AlCoFeNi")].tolist()
    i = i[0] if i else cand.index[0]
    contrib = pd.Series(sv[i, :, cls.index("BCC_SS")], index=FEATURES).sort_values()
    base = float(np.mean(rf.predict_proba(X)[:, cls.index("BCC_SS")]))
    p_bcc = float(rf.predict_proba(X.loc[[i]])[0, cls.index("BCC_SS")])
    res["shap_example"] = {"alloy": df.at[i, "Alloy"], "vec": round(float(df.at[i, "VEC"]), 2),
                           "p_bcc": round(p_bcc, 2), "base": round(base, 2),
                           "contrib": contrib.round(3)[::-1].to_dict(),
                           "values": {f: round(float(df.at[i, f]), 2) for f in FEATURES}}
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    ax.barh([f"{FEATURE_KO[f]} = {df.at[i, f]:.2f}" for f in contrib.index], contrib.values,
            color=[BLUE if v > 0 else "#e34948" for v in contrib.values], height=0.6)
    ax.axvline(0, color=AXIS, lw=1)
    ax.set_xlabel(f"BCC 확률에 대한 기여 (평균 {base:.2f} → 이 합금 {p_bcc:.2f})")
    ax.grid(axis="y", visible=False)
    save(fig, "shap_example")

(OUT / "results.json").write_text(json.dumps(res, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8")
print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
