# Recruitment Companion — Hiring Decision Tool

A Django web application that helps recruiters make structured, data-driven hiring decisions using weighted multi-criteria scoring.

---

## How It Works

1. **Define the role** — enter the job title
2. **Set criteria** — add evaluation criteria, weights, and direction (higher or lower is better)
3. **Add candidates** — list all candidates being compared
4. **Enter values** — input raw actual values per candidate per criteria (e.g. salary=55000, experience=7, test score=82)
5. **View results** — candidates are ranked by weighted normalised score with full breakdown

---

## Architecture Diagram

> Shows how the system layers connect — browser, Django, scoring engine, and database.

```mermaid
graph TD
    Browser["Browser\nBootstrap 5 UI"]

    subgraph Django["Django Application"]
        URLs["urls.py\nRoute dispatcher"]
        Views["views.py\nStep 1-4 + Results\nAJAX recalculate"]
        Forms["forms.py\nCriteriaForm\nCandidateValueForm"]
        Templates["templates/\nstep1-4, results\nbase.html"]
        Session["Django Session\nrole_title, criteria\ncandidates + values"]
        Scoring["scoring.py\nPure Python engine\nno ORM dependency"]
        Models["models.py\nHiringDecision\nHiringCriteria\nCandidate\nCandidateValue"]
        Admin["admin.py\nDjango Admin"]
    end

    DB[("SQLite Database")]

    Browser -->|HTTP Request| URLs
    URLs --> Views
    Views --> Forms
    Views --> Templates
    Views -->|read/write| Session
    Views -->|run_scoring| Scoring
    Views -->|save/load history| Models
    Models -->|ORM| DB
    Admin -->|manage| Models
    Templates -->|HTML response| Browser
```

---

## Data Flow Diagram

> Shows how raw input data travels through the system and becomes a ranked result.

```mermaid
flowchart LR
    U(["User Input"])

    subgraph Step2["Step 2 — Criteria"]
        C1["Salary — weight 40 — lower is better"]
        C2["Experience — weight 30 — higher is better"]
        C3["Test Score — weight 30 — higher is better"]
    end

    subgraph Step4["Step 4 — Raw Values"]
        V1["Alice: 400000 / 4 / 75"]
        V2["Roslin: 200000 / 3 / 74"]
    end

    subgraph Engine["scoring.py"]
        NW["normalize_weights\n40,30,30 → 0.4, 0.3, 0.3"]
        GB["get_bounds\nmin/max per criteria\n1% significance threshold"]
        NV["normalize_value\nmin-max normalization\nis_cost inverts scale"]
        CS["compute_scores\nnorm x weight → total_score"]
        CC["compute_contributions\nweighted share per criteria"]
        RS["run_sensitivity\nplus/minus 10% weight test\nstability flag"]
    end

    subgraph Output["Results Page"]
        R1["Rank 1: Alice 60%"]
        R2["Rank 2: Roslin 40%"]
        BD["Score Breakdown\nraw → rank 0-1 → pts"]
        ST["Stable result flag"]
        WI["What-if sliders\nAJAX recalculate"]
    end

    U --> Step2
    U --> Step4
    Step2 --> NW
    Step2 --> GB
    Step4 --> GB
    NW --> CS
    GB --> NV
    NV --> CS
    CS --> CC
    CS --> RS
    CC --> BD
    RS --> ST
    CS --> R1
    CS --> R2
    WI -->|updated weights| NW
```

---

## Component Diagram

> Shows all files in the project and how they depend on each other.

```mermaid
graph LR
    subgraph Project["decision_tool/ — Django Project Config"]
        S["settings.py\nSENSITIVITY_DELTA\nSTABILITY_THRESHOLD"]
        PU["urls.py — root routing"]
    end

    subgraph App["decisions/ — Main App"]
        MO["models.py\nHiringDecision\nHiringCriteria\nCandidate\nCandidateValue"]
        FO["forms.py\nRoleTitleForm\nCriteriaForm\nCandidateNameForm\nCandidateValueForm"]
        VI["views.py\nstep1_role\nstep2_criteria\nstep3_candidates\nstep4_values\nresults\nrecalculate\nsave_decision"]
        SC["scoring.py\nnormalize_weights\nget_bounds\nnormalize_value\ncompute_scores\ncompute_contributions\nrun_sensitivity\nrun_scoring"]
        AD["admin.py"]
        UR["urls.py — 10 routes"]
        TT["templatetags/score_filters.py\nget_item\nscore_bar_width\nzip_with"]
        TE["tests.py\n30+ unit and integration tests"]
    end

    subgraph Templates["templates/decisions/"]
        B["base.html"]
        T1["step1_role.html"]
        T2["step2_criteria.html"]
        T3["step3_candidates.html"]
        T4["step4_values.html"]
        TR["results.html"]
        TL["decision_list.html"]
    end

    PU --> UR
    UR --> VI
    VI --> FO
    VI --> SC
    VI --> MO
    VI --> Templates
    SC --> S
    B --> T1 & T2 & T3 & T4 & TR & TL
    TR --> TT
    T4 --> TT
    AD --> MO
    TE --> SC
    TE --> VI
```

---

## Decision Logic Diagram

> Shows exactly how the scoring engine calculates a candidate's final score step by step.

```mermaid
flowchart TD
    A(["START: run_scoring(criteria, candidates)"])
    B{"Less than\n2 candidates?"}
    NONE(["Return None — cannot score"])
    C["normalize_weights\nDivide each weight by total\n40+30+30=100 → 0.4, 0.3, 0.3"]
    D["get_bounds per criteria\nFind min and max value\nacross ALL candidates"]
    E{"Is the range less than\n1% of max value?\ne.g. 75.0 vs 75.1"}
    F["Treat as tied\nnorm = 0.5 for all\nDifference is noise"]
    G{"is_cost = True?\ne.g. Salary, Notice Period"}
    H["norm = (max - value) / (max - min)\nLower raw value scores higher"]
    I["norm = (value - min) / (max - min)\nHigher raw value scores higher"]
    J["weighted_pts = norm x normalised_weight\ne.g. 1.0 x 0.4 = 0.400 pts"]
    K["total_score = sum of all weighted_pts\ne.g. 0.0 + 0.3 + 0.3 = 0.600"]
    L["Sort by total_score descending\nAssign ranks — ties get same rank"]
    M["compute_contributions\nEach criteria share of total score %"]
    N["run_sensitivity\nShift each weight plus/minus 10%\nCount rank changes"]
    O{"Rank changes in more\nthan 50% of tests?"}
    P["is_stable = False\nWarn: result is sensitive\nto weight changes"]
    Q["is_stable = True\nResult is robust"]
    R(["RETURN ranked candidates\nbreakdown, contributions\nstability detail, score_gap"])

    A --> B
    B -->|Yes| NONE
    B -->|No| C
    C --> D
    D --> E
    E -->|Yes| F
    E -->|No| G
    F --> J
    G -->|Yes| H
    G -->|No| I
    H --> J
    I --> J
    J --> K
    K --> L
    L --> M
    M --> N
    N --> O
    O -->|Yes| P
    O -->|No| Q
    P --> R
    Q --> R
```

---

## Setup

```bash
git clone https://github.com/yourusername/recruitment-companion.git
cd recruitment-companion/decision_tool

pip install -r requirements.txt
cp .env.example .env

python manage.py migrate
python manage.py runserver
```

Visit `http://127.0.0.1:8000`

---

## Scoring Formula

```
normalised_weight_i  =  weight_i / sum(all weights)

norm_value           =  (value - min) / (max - min)        # higher is better
norm_value           =  (max - value) / (max - min)        # lower is better (is_cost)
norm_value           =  0.5                                # all candidates identical

candidate_score      =  sum( norm_value_i x normalised_weight_i )
final_score_%        =  candidate_score x 100
```

---

## Project Structure

```
decision_tool/
├── decision_tool/
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── decisions/
│   ├── models.py
│   ├── views.py
│   ├── forms.py
│   ├── scoring.py
│   ├── admin.py
│   ├── urls.py
│   ├── tests.py
│   ├── templatetags/
│   │   └── score_filters.py
│   └── templates/decisions/
│       ├── base.html
│       ├── step1_role.html
│       ├── step2_criteria.html
│       ├── step3_candidates.html
│       ├── step4_values.html
│       ├── results.html
│       └── decision_list.html
├── manage.py
├── requirements.txt
└── .env.example
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.13, Django 4.2 |
| Frontend | Bootstrap 5, Vanilla JS |
| Database | SQLite |
| Scoring Engine | Pure Python — no external ML libraries |
| Session Management | Django session framework |
