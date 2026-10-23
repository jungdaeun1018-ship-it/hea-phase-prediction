# 고엔트로피합금의 결정 구조 예측

데이터리터러시의이해 발표 과제. 고엔트로피합금(HEA) 원자료 1,361행을 진단·검증·정제해 258종으로 만들고, 기술통계와 머신러닝으로 결정 구조(상)를 분류한 뒤 SHAP으로 해석했습니다.

- **발표 슬라이드(웹):** https://jungdaeun1018-ship-it.github.io/hea-phase-prediction/hea-phase-prediction/docs/
- **발표 자료(PPTX):** [데이터리터러시_중간과제.pptx](데이터리터러시_중간과제.pptx)

## 분석 흐름

수집 설계 → 진단(고치지 않고 보기만) → 합금 이름으로 값 검증 → 정제(규칙과 행 수를 로그로 기록) → 기술통계(평균·중앙값·표준편차·n, 히스토그램) → 예측 모델(5-fold 교차검증) → 해석(순열 중요도, SHAP)

## 정제 로그

| # | 규칙 | 전 | 후 | 이유 |
|---|---|---:|---:|---|
| 1 | 빈 행 제외 | 1,361 | 1,360 | CSV 끝의 빈 줄 |
| 2 | 이름으로 VEC·Δχ 교정 | 1,360 | 1,360 | 합금 이름으로 재계산. VEC 38건, Δχ 22건 오타 교정 (예: TiZrNbTa Δχ 3.92 → 0.10) |
| 3 | 잘못된 조성 행 제외 | 1,360 | 1,321 | ΔSmix까지 이름과 다름 → 틀린 조성으로 모든 변수를 계산 (예: MoNbTaTiW) |
| 4 | ΔSmix ≥ 1R | 1,321 | 1,292 | 조작적 정의: 고·중엔트로피합금만 |
| 5 | 주조(AC)만 | 1,292 | 1,217 | 분말야금 제외 |
| 6 | 가공·열처리 없음 | 1,217 | 470 | 빈칸 = 처리 안 함. 주조 직후 상태로 통일 |
| 7 | 라벨 충돌 제외 | 470 | 404 | 같은 조성인데 논문마다 상이 다른 15종 |
| 8 | 같은 조성은 1행 | 404 | 258 | 이름 표기가 달라도(AlCrFeCoNi = AlCoCrFeNi) 같은 조성이면 하나로 |
| 9 | 이상치·결측 그대로 | 258 | 258 | 지울 근거 없음, 평균 대치 안 함 |

**왜 합금 이름이 기준인가:** 이름과 원소 비율 열이 다른 54행에서, 데이터에 적힌 VEC·ΔSmix는 52행이 이름과 일치했습니다. 비율 열에 옮겨 적기 실수가 있었던 것이라 이름을 기준으로 검증했습니다. 표기가 애매한 17행(예: NbTaTi30Zr)은 원본 값을 그대로 두었습니다.

## 핵심 결과

| 방법 | 정확도 (5-fold) | Macro F1 | McFadden 의사 R² |
|---|---|---|---|
| 전부 BCC로 찍기 | 50.8% | — | 0 |
| VEC 규칙 (기준선) | 57.4% | 0.42 | — |
| 로지스틱 회귀 | 75.2% | 0.68 | 0.50 |
| **랜덤포레스트** | **83.0%** | **0.79** | **0.59** |
| 그래디언트 부스팅 | 78.3% | 0.73 | 0.38 |

- 변수 순위는 순열 중요도와 SHAP 모두 VEC → ΔHmix → δ → Δχ → ΔSmix → 원소 개수
- SHAP: VEC가 약 6.9를 넘으면 BCC 반대쪽, 약 7.3을 넘으면 FCC 쪽 (문헌 경계 6.87, 8과 일치). ΔHmix가 약 −7 kJ/mol보다 음수면 금속간화합물 쪽
- 참고 노트북처럼 데이터를 나누기 전에 SMOTE를 적용하면 정확도가 89%로 부풀려짐. 올바르게 적용하면 83%
- 한계: 라벨 충돌 15종을 빼서 정확도가 약 4%p 높게 나옴(첫 행만 남기면 78.7%), ΔHmix·δ는 재계산으로 검증하지 못함

## 구성

| 경로 | 내용 |
|---|---|
| `데이터리터러시_중간과제.pptx` | 최종 발표 자료 |
| `data/hea_phases_machaka2021.csv` | 원본 데이터 (1,361행 × 53열, cp1252 인코딩) |
| `scripts/analyze_hea.py` | 분석 코드: 진단, 이름 검증, 정제 로그, 기술통계, 모델, SHAP, 그래프 |
| `scripts/alloy_formula.py` | 합금 이름(화학식)을 원소 비율로 해석 |
| `scripts/draw_phase_tree.py` | ‘두 갈림길’ 그림 |
| `scripts/build_pptx.py` | 슬라이드 PPTX 생성 (초안) |
| `docs/` | 웹 슬라이드 (`index.html`), 그래프 (`img/`), 모든 수치 (`results.json`) |
| `conversation.md` | 과제를 진행하며 Claude Code와 나눈 질문과 답변 |

## 재현 방법

```bash
pip install pandas numpy scikit-learn imbalanced-learn matplotlib shap
python scripts/analyze_hea.py data/hea_phases_machaka2021.csv docs
```

그래프 한글 표시에 맑은 고딕 폰트를 사용합니다 (Windows 기본 폰트).

## 출처

- 데이터: R. Machaka, "Machine learning-based prediction of phases in high-entropy alloys: A data article," *Data in Brief* 38 (2021) 107346. [PMC8477136](https://pmc.ncbi.nlm.nih.gov/articles/PMC8477136/) · [Mendeley Data](https://data.mendeley.com/datasets/7fhwrgfh2s/1)
- 분석 흐름 참고: E. Özcan, [High Entropy Alloys EDA and ML](https://www.kaggle.com/code/emrzcn/high-entropy-alloys-eda-and-ml/notebook) (Kaggle)
- 고용체 형성 기준, VEC 경계: S. Guo, C. T. Liu, *Prog. Nat. Sci.: Mater. Int.* 21 (2011) 433–446
- SHAP: S. M. Lundberg, S.-I. Lee, "A Unified Approach to Interpreting Model Predictions," NeurIPS (2017)
- SMOTE: N. V. Chawla et al., *Journal of Artificial Intelligence Research* 16 (2002) 321–357
- 분석 도구: Python, scikit-learn, shap, Claude Code (AI 에이전트)
