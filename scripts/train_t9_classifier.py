"""Train the T9 TF-IDF + logistic-regression LLM-text classifier on HC3.

This is a **dev-time** script. scikit-learn is needed only here (to fit the
model); the shipped detector infers with pure NumPy. Run once to (re)generate
``src/paperguard/data/t9_classifier.npz`` and the golden test fixtures.

    pip install "scikit-learn>=1.4"          # transient, training only
    .venv/Scripts/python.exe scripts/train_t9_classifier.py

What it does:
  1. Download HC3 (Hello-SimpleAI/HC3, all.jsonl) via httpx — no datasets lib.
  2. Flatten to (text, label): human=0, chatgpt=1.
  3. Stratified, seeded 80/10/10 split.
  4. Fit TfidfVectorizer(ngram=(1,2), sublinear_tf, max_features) + LogisticReg.
  5. Evaluate held-out accuracy + LR+ at the SUSPICIOUS threshold.
  6. CROSS-CHECK: the pure-NumPy scorer in t9_classifier._Model must match
     sklearn predict_proba within 1e-9 on held-out samples — else abort. This
     proves the runtime detector is faithful to the trained pipeline.
  7. Save the NumPy artifact + a small golden fixture for the unit test.
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import httpx
import numpy as np

# Make the in-repo package importable for the cross-check.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

HC3_URL = "https://huggingface.co/datasets/Hello-SimpleAI/HC3/resolve/main/all.jsonl"
SEED = 42
MAX_FEATURES = 8000          # small vocab -> small bundled artifact (~hundreds KB)
NGRAM_MAX = 2
SUSPICIOUS_THRESHOLD = 0.90  # p(LLM) >= this -> SUSPICIOUS tier; LR+ reported here
MIN_LEN = 40

ARTIFACT = ROOT / "src" / "paperguard" / "data" / "t9_classifier.npz"
GOLDEN = ROOT / "tests" / "fixtures" / "t9_golden.json"


def download_hc3() -> list[dict]:
    print(f"downloading HC3 from {HC3_URL} ...")
    with httpx.stream("GET", HC3_URL, follow_redirects=True, timeout=120.0) as r:
        r.raise_for_status()
        body = b"".join(r.iter_bytes())
    rows = [json.loads(line) for line in body.splitlines() if line.strip()]
    print(f"  {len(rows):,} question groups")
    return rows


def flatten(rows: list[dict]) -> tuple[list[str], list[int]]:
    texts: list[str] = []
    labels: list[int] = []
    for row in rows:
        for ans in row.get("human_answers") or []:
            a = (ans or "").strip()
            if len(a) >= MIN_LEN:
                texts.append(a)
                labels.append(0)
        for ans in row.get("chatgpt_answers") or []:
            a = (ans or "").strip()
            if len(a) >= MIN_LEN:
                texts.append(a)
                labels.append(1)
    print(f"  flattened: {len(texts):,} (human={labels.count(0):,} llm={labels.count(1):,})")
    return texts, labels


def lr_plus(y_true: np.ndarray, p_llm: np.ndarray, threshold: float) -> tuple[float, float, float]:
    pred = (p_llm >= threshold).astype(int)
    tp = int(((pred == 1) & (y_true == 1)).sum())
    fn = int(((pred == 0) & (y_true == 1)).sum())
    fp = int(((pred == 1) & (y_true == 0)).sum())
    tn = int(((pred == 0) & (y_true == 0)).sum())
    sens = tp / (tp + fn) if (tp + fn) else 0.0
    fpr = fp / (fp + tn) if (fp + tn) else 0.0
    lrp = float("inf") if (fpr == 0 and sens > 0) else (sens / fpr if fpr else 0.0)
    return lrp, sens, 1.0 - fpr


def main() -> None:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import accuracy_score
    from sklearn.model_selection import train_test_split

    texts, labels = flatten(download_hc3())
    y = np.asarray(labels)

    tr_x, tmp_x, tr_y, tmp_y = train_test_split(
        texts, y, test_size=0.20, random_state=SEED, stratify=y
    )
    val_x, te_x, val_y, te_y = train_test_split(
        tmp_x, tmp_y, test_size=0.50, random_state=SEED, stratify=tmp_y
    )
    print(f"  split: train={len(tr_x):,} val={len(val_x):,} test={len(te_x):,}")

    vec = TfidfVectorizer(
        lowercase=True,
        ngram_range=(1, NGRAM_MAX),
        sublinear_tf=True,
        norm="l2",
        smooth_idf=True,
        max_features=MAX_FEATURES,
        min_df=5,
    )
    x_tr = vec.fit_transform(tr_x)
    clf = LogisticRegression(C=4.0, max_iter=2000, class_weight="balanced")
    clf.fit(x_tr, tr_y)

    # Held-out metrics.
    p_te = clf.predict_proba(vec.transform(te_x))[:, 1]
    acc = accuracy_score(te_y, (p_te >= 0.5).astype(int))
    lrp, sens, spec = lr_plus(te_y, p_te, SUSPICIOUS_THRESHOLD)
    print("=" * 56)
    print(f"TEST accuracy (0.5)        : {acc:.4f}  (target >= 0.85)")
    print(f"SUSPICIOUS threshold       : {SUSPICIOUS_THRESHOLD}")
    print(f"  sensitivity / specificity: {sens:.4f} / {spec:.4f}")
    print(f"  LR+                      : {lrp}")
    print("=" * 56)
    if acc < 0.85:
        sys.exit(f"ABORT: accuracy {acc:.4f} below target 0.85")

    # Build the artifact arrays. sklearn vocabulary_ maps term -> column index.
    # Store vocab as a unicode-string array (NOT object dtype) so the shipped
    # loader can read it with allow_pickle=False.
    vocab_items = sorted(vec.vocabulary_.items(), key=lambda kv: kv[1])
    vocab = np.array([t for t, _ in vocab_items], dtype=np.str_)
    idf = vec.idf_.astype(np.float64)
    coef = clf.coef_[0].astype(np.float64)
    intercept = float(clf.intercept_[0])
    lrp_store = float(lrp) if lrp != float("inf") else 1e9  # inf -> sentinel

    np.savez_compressed(
        ARTIFACT,
        vocab=vocab,
        idf=idf,
        coef=coef,
        intercept=np.float64(intercept),
        ngram_max=np.int64(NGRAM_MAX),
        threshold=np.float64(SUSPICIOUS_THRESHOLD),
        accuracy=np.float64(acc),
        lr_plus=np.float64(lrp_store),
    )

    # ---- CROSS-CHECK: pure-NumPy scorer must equal sklearn predict_proba ----
    # Reload through the SHIPPED scorer (allow_pickle=False, same as runtime).
    from paperguard.detectors.t9_classifier import _Model

    with open(ARTIFACT, "rb") as fh:
        model = _Model(np.load(io.BytesIO(fh.read()), allow_pickle=False))

    sample_idx = list(range(0, min(len(te_x), 300)))
    sk = clf.predict_proba(vec.transform([te_x[i] for i in sample_idx]))[:, 1]
    mine = np.array([model.prob_llm(te_x[i]) for i in sample_idx])
    max_diff = float(np.max(np.abs(sk - mine)))
    print(f"cross-check max |sklearn - numpy| over {len(sample_idx)} samples: {max_diff:.2e}")
    if max_diff > 1e-9:
        sys.exit(f"ABORT: NumPy scorer diverges from sklearn ({max_diff:.2e})")

    # Golden fixture for the unit test: a few (text, expected_prob) pairs.
    golden = [
        {"text": te_x[i], "prob": float(mine[i])}
        for i in (0, 1, 2, 3, 4, 5, 6, 7)
        if i < len(te_x)
    ]
    GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN.write_text(json.dumps(golden, indent=2, ensure_ascii=False), encoding="utf-8")

    size_kb = ARTIFACT.stat().st_size / 1024
    print(f"wrote {ARTIFACT}  ({size_kb:.0f} KB, vocab={len(vocab):,})")
    print(f"wrote {GOLDEN}  ({len(golden)} golden samples)")


if __name__ == "__main__":
    main()
