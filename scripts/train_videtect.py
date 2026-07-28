"""Fine-tune a Vietnamese AI-text detector for the humanize v4 loop.

This trains the "referee" that orchestrator/tools/detector.py::ViDetectScorer
loads. It is the FREE path (self-hosted, no per-call cost) — the trade-off,
established in the humanizer research, is that a self-hosted detector correlates
only partially (~60-70%) with the commercial detector a reader actually runs, so
treat its score as an in-house proxy, not a guarantee.

WHY mDeBERTa-v3-base: it won the ViDetect benchmark (Tran et al., 2024,
arXiv:2405.03206) with F1 0.9506 — the best of ViT5 / BARTpho / PhoBERT /
mBERT / mDeBERTa on 6,800 Vietnamese essays (3,400 human, 3,400 AI). PhoBERT is
a fine monolingual fallback (--base vinai/phobert-base) but scored lower there.

DATA — the one thing this script cannot fetch for you:
    The ViDetect paper calls the set "publicly available" but ships no download
    link. Obtain it (author contact / any mirror) as a CSV with two columns:

        text,label            # label: 1 = AI-generated, 0 = human

    then point --data at it. Any human-vs-AI Vietnamese CSV in that shape works
    if ViDetect proves hard to get — the label contract is all that matters.

LABEL CONTRACT (must match ViDetectScorer): the AI class is id 1 and is named so
its label string contains "ai" — the scorer maps P(label containing "ai") to
P(AI). Do not rename the classes without updating detector.py.

RUN (free on a Colab T4; ~6,800 samples fine-tunes in well under an hour):

    pip install "transformers>=4.40" datasets evaluate torch sentencepiece
    python scripts/train_videtect.py --data videtect.csv --out models/videtect-mdeberta

    # then enable it:
    export HUMANIZE_SCORER=videtect
    export HUMANIZE_VIDETECT_MODEL=models/videtect-mdeberta
"""
from __future__ import annotations

import argparse
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("train_videtect")

# The AI class is id 1 and named to contain "ai" — the ViDetectScorer depends on
# this string to map the pipeline's top label to P(AI). See module docstring.
ID2LABEL = {0: "human", 1: "ai_generated"}
LABEL2ID = {v: k for k, v in ID2LABEL.items()}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data", required=True,
                   help="CSV with columns text,label (label: 1=AI, 0=human).")
    p.add_argument("--out", default="models/videtect-mdeberta",
                   help="Output dir for the fine-tuned model + tokenizer.")
    p.add_argument("--base", default="microsoft/mdeberta-v3-base",
                   help="Base encoder to fine-tune (ViDetect's winner).")
    # The paper's best F1 used 64-token truncation, but academic passages scored
    # in production are longer; 256 is a safer default. Tune if you reproduce.
    p.add_argument("--max-len", type=int, default=256)
    p.add_argument("--epochs", type=float, default=4.0)
    p.add_argument("--batch-size", type=int, default=16)
    p.add_argument("--lr", type=float, default=2e-5)
    p.add_argument("--test-size", type=float, default=0.2,
                   help="Held-out fraction (paper used a 7:1:2 split).")
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args()


def _normalize_label(v) -> int:
    """Accept 1/0, '1'/'0', or human/ai text labels — emit the id contract."""
    s = str(v).strip().lower()
    if s in ("1", "ai", "ai_generated", "machine", "generated", "llm"):
        return 1
    if s in ("0", "human", "real"):
        return 0
    raise ValueError(f"unrecognized label {v!r} — use 1=AI / 0=human")


def main() -> None:
    args = parse_args()

    # Heavy deps are imported here, not at module top, so `--help` and a syntax
    # check work without a full ML stack installed.
    import numpy as np
    import evaluate
    from datasets import Dataset
    import pandas as pd
    from transformers import (AutoModelForSequenceClassification, AutoTokenizer,
                              Trainer, TrainingArguments)

    df = pd.read_csv(args.data)
    if not {"text", "label"} <= set(df.columns):
        raise SystemExit(f"{args.data} must have columns text,label "
                         f"(found {list(df.columns)})")
    df = df[["text", "label"]].dropna()
    df["label"] = df["label"].map(_normalize_label)
    log.info("loaded %d rows — %d AI / %d human",
             len(df), int(df.label.sum()), int((df.label == 0).sum()))

    ds = Dataset.from_pandas(df, preserve_index=False).train_test_split(
        test_size=args.test_size, seed=args.seed, stratify_by_column="label")

    tok = AutoTokenizer.from_pretrained(args.base)

    def _tok(batch):
        return tok(batch["text"], truncation=True, max_length=args.max_len)

    ds = ds.map(_tok, batched=True)

    model = AutoModelForSequenceClassification.from_pretrained(
        args.base, num_labels=2, id2label=ID2LABEL, label2id=LABEL2ID)

    f1 = evaluate.load("f1")
    acc = evaluate.load("accuracy")

    def _metrics(eval_pred):
        logits, labels = eval_pred
        preds = np.argmax(logits, axis=-1)
        return {"f1": f1.compute(predictions=preds, references=labels)["f1"],
                "accuracy": acc.compute(predictions=preds,
                                        references=labels)["accuracy"]}

    targs = TrainingArguments(
        output_dir=args.out + "/_checkpoints",
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        learning_rate=args.lr,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="f1",
        seed=args.seed,
        logging_steps=50,
    )
    trainer = Trainer(
        model=model, args=targs,
        train_dataset=ds["train"], eval_dataset=ds["test"],
        tokenizer=tok, compute_metrics=_metrics,
    )
    trainer.train()
    log.info("final eval: %s", trainer.evaluate())

    trainer.save_model(args.out)
    tok.save_pretrained(args.out)
    log.info("saved model to %s", args.out)
    log.info("enable it: HUMANIZE_SCORER=videtect HUMANIZE_VIDETECT_MODEL=%s",
             args.out)


if __name__ == "__main__":
    main()
