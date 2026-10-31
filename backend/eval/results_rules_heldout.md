# Extraction eval: `rules`

40 labeled criteria · 0.0s

| Metric | Result |
|---|---|
| Category accuracy | **90%** (36/40) |
| Exact structured match | **88%** (35/40) |
| Recall on checkable criteria | **85%** (28/33) |
| Unsafe rate (wrong checkable rule) | **2%** (1/40) |

| Category | Exact |
|---|---|
| age | 1/4 |
| condition | 9/9 |
| lab | 10/10 |
| medication | 3/5 |
| other | 7/7 |
| performance_status | 2/2 |
| pregnancy | 2/2 |
| sex | 1/1 |

## Misses

| Criterion | Expected | Got |
|---|---|---|
| Subjects must be at least eighteen (18) years of age | age age >= 18 | other None None None |
| Aged 50 years and over | age age >= 50 | other None None None |
| Patients aged ≥18 and ≤80 years | age age between 18 | age age >= 18.0 |
| Patients on chronic opioid therapy for pain | medication medication present opioids | other None None None |
| Requires ongoing anticoagulation | medication medication present anticoagulant | other None None None |
