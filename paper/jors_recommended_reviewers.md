# Recommended reviewers — JORS submission

Five candidate reviewers covering the four expertise axes the
manuscript spans: statistical-integrity procedures, image
forensics, LLM-text detection, and open-source software quality.
No co-authorship overlap; no shared-institution conflict; no
recent (3-year) collaboration with the corresponding author.

The JORS portal accepts up to ~5 recommended reviewers. The author
should look up current contact details for each candidate before
pasting into the form (institutional pages move; the
ORCID-resolved profiles below are the safest entry points).

---

## 1. Michèle B. Nuijten

- **Affiliation:** Tilburg University, Department of Methodology
  and Statistics (Netherlands)
- **ORCID:** [0000-0001-8472-0424](https://orcid.org/0000-0001-8472-0424)
- **Why:** Lead author of the `statcheck` paper
  [@nuijten2016statcheck], which the manuscript's B4 detector
  re-implements in Python. Cohen's κ = 0.79 cross-validation result
  (§3) is directly against her published procedure. She is the
  single best-qualified reviewer to verify B4's correctness.
- **Recent work:** Continues to maintain and extend R `statcheck`;
  has published widely on statistical reporting errors and
  open-science reproducibility.
- **Caveat:** May be busy; if she declines, Sacha Epskamp (also
  Tilburg, statcheck co-author) is a strong second pick.

---

## 2. Nicholas J. L. Brown

- **Affiliation:** Linnaeus University, Sweden (until recently
  University of Groningen)
- **ORCID:** [0000-0001-5604-6473](https://orcid.org/0000-0001-5604-6473)
- **Why:** Co-author of GRIM [@brown2017grim], one of the
  five named procedures PaperGuard re-implements (B1). He has
  also publicly critiqued how research-integrity tools are
  calibrated and reported, which is directly relevant to the
  manuscript's "honest negative findings" framing in §3.
- **Recent work:** GRIMMER (B6 in PaperGuard), continued work on
  data-fabrication detection in psychology and biomedicine.
- **Caveat:** Active on social media; very public reviewer style.
  Will not pull punches but is fair.

---

## 3. James A. J. Heathers

- **Affiliation:** Cipher Skin (industry research) / formerly
  Northeastern University
- **ORCID:** [0000-0002-4377-0307](https://orcid.org/0000-0002-4377-0307)
- **Why:** Originator of the SPRITE procedure (B8 in PaperGuard)
  [@heathers2018sprite] and broadly active in the methodological
  forensics community. Has hands-on experience using research-
  integrity tooling against real disputed papers; will review
  the manuscript's Reuse Potential (§5) claims realistically.
- **Recent work:** Outlier-detection methodology, public-facing
  science-integrity writing.

---

## 4. Elisabeth M. Bik

- **Affiliation:** Independent (formerly Microbiome Digest /
  Stanford)
- **ORCID:** [0000-0002-1352-9551](https://orcid.org/0000-0002-1352-9551)
- **Why:** The image-duplication forensics workflow PaperGuard's
  F1/F2/F3/F4/F6 detectors reproduce traces directly to her
  published practice [@bik2016prevalence]. The manuscript's
  honest report that image-layer LR+ ≈ 1 on randomly-sampled
  retracted papers (because the layer is tuned to her specific
  patch-splice failure mode) deserves her direct read. She is the
  single best-qualified reviewer for whether the image-layer
  framing in §3 is fair to her published method.
- **Recent work:** PubPeer-driven image-integrity casework,
  COPE consultation, continued advocacy for retraction reform.
- **Caveat:** Very high-demand reviewer; if she declines, Mike
  Rossner (Image Data Integrity) or Jana Christopher (FEBS image-
  integrity analyst) are reasonable alternates.

---

## 5. Dmitry Kobak

- **Affiliation:** University of Tübingen, Germany
- **ORCID:** [0000-0002-5639-7209](https://orcid.org/0000-0002-5639-7209)
- **Why:** Author of "Delving into ChatGPT word patterns"
  [@kobak2025delving] — one of the two literature pillars under
  PaperGuard's T6 lexical detector. The manuscript's T7
  five-endpoint study (§3, RLHF-driven direction inversion)
  extends the LLM-text-detection literature his work is part of;
  he is well-placed to assess whether the inversion claim is
  methodologically sound. Also expert in statistical/ML rigor
  generally, which transfers to the broader pipeline.
- **Recent work:** LLM-generated-text detection at scale;
  visualization and dimensionality-reduction methodology.

---

## Additional candidates (alternates if any of the above decline)

| Name | Affiliation | Best-fit area |
|---|---|---|
| **Guillaume Cabanac** | Université de Toulouse III | Tortured-phrases detection (T4 in PaperGuard); paper-mill identification |
| **Sacha Epskamp** | Tilburg University | statcheck co-author; alt to Nuijten |
| **Daniël Lakens** | Eindhoven University of Technology | p-curve methodology (B7 in PaperGuard); reproducibility tooling |
| **Eric Mitchell** | Stanford / OpenAI | DetectGPT [@mitchell2023detectgpt]; can review T8 reasoning-model incompatibility claim |
| **Jana Christopher** | FEBS Press | Image-integrity professional reviewer; alt to Bik |
| **John P. A. Ioannidis** | Stanford School of Medicine | Meta-research / research-integrity statistics broadly |
| **Lex Bouter** | VU Amsterdam | Research-integrity policy and methodology |

## Conflicts of interest disclosure

The corresponding author has had no co-authorship, no shared
institutional affiliation, no advisory relationship, and no
financial interaction with any of the five primary recommended
reviewers or the seven alternates in the past three years (and,
indeed, has never directly collaborated with any of them — the
relationship is reader-of-published-work in every case).

The list deliberately excludes (a) other JOSS / JORS / SoftwareX
editors and (b) people who would have an obvious incentive to
review the manuscript positively because of citation reciprocity.
