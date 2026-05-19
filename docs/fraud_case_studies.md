# Real Fraud Case Studies — How PaperGuard Maps to Each

This document catalogs major public misconduct cases, their specific
techniques, and which PaperGuard detectors would (or would not) catch them.
Use it to (a) understand what each detector is actually designed against,
and (b) calibrate expectations about what this tool can and cannot do.

**Reminder of epistemic position:** Every "would catch" below means
"PaperGuard would have surfaced a statistical anomaly". It does not mean
"PaperGuard would have proven misconduct". See `epistemic_position.md`.

---

## Diederik Stapel (social psychology, 2011 — 58 retractions)

**Techniques used:**
- Whole datasets fabricated at home, never shared raw data with students
- Large mean differences with implausibly small within-group variance
- Minor pre-existing data was "edited" before escalating to full fabrication
- Linguistic style: more methodology / certainty terms, fewer adjectives
  than his genuine papers (Markowitz & Hancock 2014 PLOS ONE)

**PaperGuard mapping:**
| Signal | Detector | Status |
|---|---|---|
| Small within-group variance | **D1 Residual Smoothness** | ✅ direct |
| Large effects with low variance | A1 + D1 combined | ✅ via cross-cluster |
| Linguistic fingerprint | **T5 Stylometry** | ✅ direct |
| Multi-study Var(z) < 1 | **B5 TIVA** | ✅ if user supplies a list |
| Refusal to share raw | — | ❌ not detectable |

---

## Yoshitaka Fujii (anesthesia, 2012 — 172 retractions)

**Techniques used:**
- Baseline characteristics of RCTs unrealistically balanced across groups
  (continuous variables with p ≈ 1 across many baselines)
- Forged co-author signatures on submission letters
- Co-authors listed from institutions other than his current employer to
  fake "multi-site" status
- Ambiguous study dates and institutions

**PaperGuard mapping:**
| Signal | Detector | Status |
|---|---|---|
| Baseline over-balance | **C1 Carlisle** | ✅ direct (this case birthed the test) |
| Forged signatures | — | ❌ not detectable |
| Multi-site coauthor inconsistency | — | ⚠️ planned (institutional cross-check) |
| Date/location ambiguity | T3 + manual review | 🟡 partial |

---

## Hwang Woo-suk (stem cells, 2005-06 — Science retraction)

**Techniques used:**
- Same stem cell microscopy images relabeled as different cell lines
  (one image used for 4 of 11 "distinct" cell lines)
- Same DNA fingerprint patterns claimed as different genotypes

**PaperGuard mapping:**
| Signal | Detector | Status |
|---|---|---|
| Same image, different labels | **F1 pHash** | ✅ direct |
| Cross-paper image reuse | **F4 cross-paper pHash** (NEW 0.8.0) | ✅ direct |
| Internal duplication | **F2 ORB + F3 splice** | ✅ direct |

---

## Jan Hendrik Schön (physics, 2002 — 16 retractions, Bell Labs)

**Techniques used:**
- **Same noise curve** in figures across different experiments / temperatures /
  materials (this is what caught him — Lydia Sohn noticed identical noise
  in two graphs at very different temperatures)
- Deleted raw data files claiming "computer ran out of memory"
- Substituted whole curves and partial curves across figures

**PaperGuard mapping:**
| Signal | Detector | Status |
|---|---|---|
| Identical noise across plots | **F1 pHash on figures** | ✅ if charts extracted as bitmaps |
| Identical sequence values across columns | **A3 inter-column σ → 0** | ✅ if data is in tables |
| Deleted raw data | — | ❌ not directly detectable, but G4 file metadata |
| Substituted whole curves | F1/F2 image comparison | ✅ direct |

**Note:** Schön's case was particularly devastating because his "data"
were graphs. If you only have the published PDF, our image detectors
work on rasterized plots — F1 will catch identical noise patterns.

---

## Paolo Macchiarini (regenerative surgery, 2018)

**Techniques used:**
- Reported patient outcomes did not match the underlying medical records
- Omitted post-surgery complications and deaths from publications
- Continued claiming success after multiple patients had died

**PaperGuard mapping:**
| Signal | Detector | Status |
|---|---|---|
| Discrepancy paper vs medical records | — | ❌ requires the actual records |
| Survival data manipulation | — | ❌ same |
| Ethics violations (no IRB, no animal pre-test) | **T3 ethics audit** | ✅ direct |
| Inflated case-series success | — | ❌ requires external truth |

**Honest assessment:** This is the case PaperGuard is *most useless* on.
Detecting Macchiarini-style fraud requires comparing the paper to private
medical records — no statistical tool can do this from the manuscript alone.

---

## Brian Wansink (food psychology, 2018 — 18 retractions)

**Techniques used:**
- Massive p-hacking: emails show explicit instructions to "keep trying"
  different cuts of the data
- Self-plagiarism: same dataset used across multiple papers with
  contradictory N and means
- Impossible values (e.g., children eating 700 pizza slices)
- Multiple statistical errors per paper (often 150+ in a single paper)

**PaperGuard mapping:**
| Signal | Detector | Status |
|---|---|---|
| Implausible values (700 pizza slices) | **A6 Implausible Values** (NEW 0.8.0) | ✅ direct |
| P-hacking (p clustered just below 0.05) | **B7 P-Curve** (NEW 0.8.0) + **B5 TIVA** | ✅ direct |
| Cross-paper duplicate data | **T1 text similarity** | 🟡 partial (catches text reuse) |
| Statistical errors per paper | **B4 statcheck + B1 GRIM + B6 GRIMMER** | ✅ direct |

---

## Eliezer Masliah (Alzheimer's neuroscience, 2024 — 132 papers flagged)

**Techniques used:**
- Western blot splicing and reuse across decades of papers
- Same micrograph relabeled across multiple publications
- Spans 1997 to 2023

**PaperGuard mapping:**
| Signal | Detector | Status |
|---|---|---|
| WB splice within paper | **F3 splice forensics** | ✅ direct |
| Image reuse across papers | **F4 cross-paper pHash** (NEW 0.8.0) | ✅ direct |
| ORB-based internal duplication | **F2** | ✅ direct |

**Note:** Detecting Masliah would have required two things PaperGuard now
has but didn't in 0.6.0: F4 (cross-paper store) and high-recall F2/F3.

---

## Geng Hongwei's targets (Chinese academic sleuth, 2025)

**Techniques he uses to catch fraud:**
- Terminal digit analysis (e.g., "5" appearing 212 times in 2400 data points,
  body weights essentially never ending in 0)
- Benford's law on tabulated data
- Cross-paper consistency

**PaperGuard mapping:**
| Signal | Detector | Status |
|---|---|---|
| Terminal-digit bias | **A1** | ✅ direct (this case validates the approach) |
| Benford violations | **A2** | ✅ direct |
| Cross-paper inconsistency | F4 + T1 | ✅ partial |

---

## Bik et al. (2016) systematic image-duplication study

**Bik's three categories of problematic images:**
1. Simple copy-paste duplications (easiest to find)
2. Duplications with shift / rotation / mirror / minor crop
3. Photoshopped composites with deliberate splicing

**PaperGuard mapping:**
| Bik category | Detector |
|---|---|
| Simple copy-paste | F1 pHash (Hamming ≤ 2 → CRITICAL) |
| Rotated / mirrored / cropped | F2 ORB+RANSAC (rotation tolerant) |
| Splicing / Photoshop | F3 statistical block-signature |
| Cross-paper reuse | F4 persistent store |

We deliberately use **three different image methods** because each catches
a different category and they don't fully overlap.

---

## What PaperGuard cannot catch (honest gaps)

| Fraud type | Why we can't | What would |
|---|---|---|
| Forged co-author signatures (Fujii) | Off-document | Publisher cooperation |
| Medical-record fabrication (Macchiarini) | Records are private | Patient registry audit |
| Single-experiment fabrication with no statistical tell | Looks normal | Independent replication |
| Forged peer review (PLOS ONE 2022 mass retractions) | No public signal | Journal-side IP / email checks |
| Ghost authorship | Not in document | Author ORCID + signing-history audit |
| Pure invention with realistic noise | By construction undetectable from data | Lab audit / inspect raw |

This list is the honest answer to "is PaperGuard the silver bullet for
fraud detection?" — **no**, and any tool claiming it is, is lying. PaperGuard
covers a meaningful subset (~85% of detectable statistical/image signals)
and explicitly leaves the rest to humans and institutions.

---

## How to use this catalog

1. **Reviewer screening pre-publication:** Run `paperguard scan` to surface
   technical anomalies; cross-reference with the matching case in this
   document to understand what each finding could mean.
2. **Self-screening pre-submission:** If any detector here matches your
   working draft, **investigate before submitting** — it's almost always
   an honest error (rounding, copy-paste in tables, etc.) but it's better
   to find it yourself than to have a referee surface it.
3. **Education:** Use specific cases to teach students why each detector
   exists. The detectors are not abstract — they were each motivated by
   real scandals.
