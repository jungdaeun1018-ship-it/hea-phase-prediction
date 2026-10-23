# 고엔트로피합금의 결정 구조 예측

데이터리터러시의이해 발표 과제. 고엔트로피합금(HEA) 317종의 열역학 변수로 결정 구조(상)를 분류하는 데이터 분석과 머신러닝.

**발표 슬라이드:** [docs/index.html](docs/index.html) (GitHub Pages로 공개)

## 핵심 결과

| 방법 | 정확도 (5-fold 교차검증) |
|---|---|
| VEC 규칙 (기준선) | 54.6% |
| 로지스틱 회귀 | 74.7% |
| **랜덤포레스트** | **80.1%** |
| 그래디언트 부스팅 | 78.2% |

- 가장 중요한 변수는 VEC(가전자 농도). BCC 중앙값 4.64, FCC 8.0
- FCC+BCC 2상이 가장 예측하기 어려움 (재현율 56%)
- 참고 노트북처럼 데이터를 나누기 전에 SMOTE를 적용하면 정확도가 88%로 부풀려짐. 올바르게 적용하면 79%

## 구성

| 경로 | 내용 |
|---|---|
| `data/hea_phases_machaka2021.csv` | 원본 데이터 (합금 1,360종, Windows-1252 인코딩) |
| `scripts/analyze_hea.py` | 분석 코드: 정제, EDA, 모델 비교, 그래프 생성 |
| `docs/` | 발표 슬라이드 (`index.html`), 그래프 (`img/`), 수치 결과 (`results.json`) |
| `conversation.md` | 과제를 진행하며 Claude Code와 나눈 질문과 답변 |

## 재현 방법

```bash
pip install pandas numpy scikit-learn imbalanced-learn matplotlib
python scripts/analyze_hea.py data/hea_phases_machaka2021.csv docs
```

그래프 한글 표시에 맑은 고딕 폰트를 사용합니다 (Windows 기본 폰트).

## 출처

- 데이터: R. Machaka, "Machine learning-based prediction of phases in high-entropy alloys: A data article," *Data in Brief* 38 (2021) 107346. [PMC8477136](https://pmc.ncbi.nlm.nih.gov/articles/PMC8477136/) · [Mendeley Data](https://data.mendeley.com/datasets/7fhwrgfh2s/1). 논문 부록 CSV(mmc1.csv)를 그대로 사용
- 분석 흐름 참고: E. Özcan, [High Entropy Alloys EDA and ML](https://www.kaggle.com/code/emrzcn/high-entropy-alloys-eda-and-ml/notebook) (Kaggle)
- 고용체 형성 기준: S. Guo, C. T. Liu, *Prog. Nat. Sci.: Mater. Int.* 21 (2011) 433–446
- 분석 도구: Python, scikit-learn, Claude Code (AI 에이전트)
