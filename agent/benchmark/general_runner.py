import argparse
import base64
import csv
import hashlib
import importlib
import json
import math
import os
import pickle
import random
import re
import shutil
import string
import subprocess
import time
import sys
import zlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd
from openai import OpenAI


CHOICE_LABELS = list(string.ascii_uppercase)
BBH_TASKS = [
    "boolean_expressions",
    "causal_judgement",
    "date_understanding",
    "disambiguation_qa",
    "dyck_languages",
    "formal_fallacies",
    "geometric_shapes",
    "hyperbaton",
    "logical_deduction_five_objects",
    "logical_deduction_seven_objects",
    "logical_deduction_three_objects",
    "movie_recommendation",
    "multistep_arithmetic_two",
    "navigate",
    "object_counting",
    "penguins_in_a_table",
    "reasoning_about_colored_objects",
    "ruin_names",
    "salient_translation_error_detection",
    "snarks",
    "sports_understanding",
    "temporal_sequences",
    "tracking_shuffled_objects_five_objects",
    "tracking_shuffled_objects_seven_objects",
    "tracking_shuffled_objects_three_objects",
    "web_of_lies",
    "word_sorting",
]
LCB_FILES = {
    "release_v1": ["test.jsonl"],
    "release_v2": ["test.jsonl", "test2.jsonl"],
    "release_v3": ["test.jsonl", "test2.jsonl", "test3.jsonl"],
    "release_v4": ["test.jsonl", "test2.jsonl", "test3.jsonl", "test4.jsonl"],
    "release_v5": [
        "test.jsonl",
        "test2.jsonl",
        "test3.jsonl",
        "test4.jsonl",
        "test5.jsonl",
    ],
    "release_v6": [
        "test.jsonl",
        "test2.jsonl",
        "test3.jsonl",
        "test4.jsonl",
        "test5.jsonl",
        "test6.jsonl",
    ],
    "release_latest": [
        "test.jsonl",
        "test2.jsonl",
        "test3.jsonl",
        "test4.jsonl",
        "test5.jsonl",
        "test6.jsonl",
    ],
}

for idx in range(1, 7):
    LCB_FILES[f"v{idx}"] = [f"test{idx}.jsonl" if idx != 1 else "test.jsonl"]

for start in range(1, 7):
    for end in range(start + 1, 7):
        LCB_FILES[f"v{start}_v{end}"] = [
            f"test{idx}.jsonl" if idx != 1 else "test.jsonl"
            for idx in range(start, end + 1)
        ]


DATASETS = {
    "mmlu": {
        "name": "MMLU",
        "type": "choice",
        "splits": ["test", "dev", "val"],
        "default_split": "test",
        "metrics": ["accuracy", "invalid_rate"],
    },
    "cmmlu": {
        "name": "CMMLU",
        "type": "choice",
        "splits": ["test", "dev"],
        "default_split": "test",
        "metrics": ["accuracy", "invalid_rate"],
    },
    "c-eval": {
        "name": "C-Eval",
        "type": "choice",
        "splits": ["test", "val", "dev"],
        "default_split": "test",
        "metrics": ["accuracy", "invalid_rate"],
    },
    "ceval": {
        "alias_for": "c-eval",
    },
    "mmlu-pro": {
        "name": "MMLU-Pro",
        "type": "choice",
        "splits": ["test", "validation"],
        "default_split": "test",
        "metrics": ["accuracy", "invalid_rate"],
    },
    "arc-challenge": {
        "name": "ARC-Challenge",
        "type": "choice",
        "splits": ["test", "validation", "train"],
        "default_split": "test",
        "metrics": ["accuracy", "invalid_rate"],
    },
    "arc": {
        "alias_for": "arc-challenge",
    },
    "gsm8k": {
        "name": "GSM8K",
        "type": "math",
        "splits": ["test", "train"],
        "default_split": "test",
        "metrics": ["exact_match"],
    },
    "squad": {
        "name": "SQuAD",
        "type": "qa",
        "splits": ["validation", "train"],
        "default_split": "validation",
        "metrics": ["exact_match", "f1"],
    },
    "truthfulqa-generation": {
        "name": "TruthfulQA generation",
        "type": "generation",
        "splits": ["validation"],
        "default_split": "validation",
        "metrics": ["record_only"],
    },
    "truthfulqa": {
        "alias_for": "truthfulqa-generation",
    },
    "drop": {
        "name": "DROP",
        "type": "qa",
        "splits": ["validation", "train"],
        "default_split": "validation",
        "metrics": ["exact_match", "f1"],
    },
    "gpqa": {
        "name": "GPQA",
        "type": "choice",
        "splits": ["diamond", "main", "extended"],
        "default_split": "diamond",
        "metrics": ["accuracy", "invalid_rate"],
    },
    "math": {
        "name": "MATH",
        "type": "math",
        "splits": ["test", "train"],
        "default_split": "test",
        "metrics": ["accuracy", "invalid_rate"],
    },
    "humaneval": {
        "name": "HumanEval",
        "type": "code_generation",
        "splits": ["test"],
        "default_split": "test",
        "metrics": ["pass@1", "record_only"],
    },
    "human-eval": {
        "alias_for": "humaneval",
    },
    "ifeval": {
        "name": "IFEval",
        "type": "instruction_following",
        "splits": ["test"],
        "default_split": "test",
        "metrics": [
            "strict_prompt_accuracy",
            "strict_instruction_accuracy",
            "loose_prompt_accuracy",
            "loose_instruction_accuracy",
        ],
    },
    "bbh": {
        "name": "BBH",
        "type": "bbh",
        "splits": ["all", *BBH_TASKS],
        "default_split": "all",
        "metrics": ["accuracy", "invalid_rate"],
    },
    "livecodebench": {
        "name": "LiveCodeBench",
        "type": "livecodebench",
        "splits": list(LCB_FILES.keys()),
        "default_split": "release_latest",
        "metrics": ["pass@1", "record_only"],
    },
    "lcb": {
        "alias_for": "livecodebench",
    },
}


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--action", choices=["list", "inspect", "run"], default="run")
    parser.add_argument("--api-key", default="EMPTY")
    parser.add_argument("--base-url", default="http://10.130.35.2:8000/v1")
    parser.add_argument("--model", default="model_medical_20250630")
    parser.add_argument("--dataset-root", required=True)
    parser.add_argument("--dataset", default="")
    parser.add_argument("--split", default="default")
    parser.add_argument("--output", default=None)
    parser.add_argument("--max-workers", type=int, default=1)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--save-every", type=int, default=2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--humaneval-executor", choices=["docker", "record_only"], default="docker"
    )
    parser.add_argument("--humaneval-docker-image", default="qingnang-evaluator:local")
    parser.add_argument("--humaneval-timeout", type=int, default=5)
    parser.add_argument("--humaneval-memory", default="512m")
    parser.add_argument("--humaneval-cpus", default="1")
    parser.add_argument("--humaneval-pids-limit", type=int, default=64)
    parser.add_argument(
        "--lcb-executor",
        choices=["official_docker", "record_only"],
        default="record_only",
    )
    parser.add_argument("--lcb-docker-image", default="qingnang-evaluator:local")
    parser.add_argument("--lcb-timeout", type=int, default=8)
    parser.add_argument("--lcb-num-process", type=int, default=1)
    parser.add_argument("--lcb-batch-size", type=int, default=50)
    parser.add_argument("--lcb-memory", default="1g")
    parser.add_argument("--lcb-cpus", default="1")
    parser.add_argument("--lcb-pids-limit", type=int, default=128)
    return parser.parse_args()


def canonical_dataset(name: str) -> str:
    key = name.strip().lower()
    meta = DATASETS.get(key)
    if not meta:
        raise ValueError(f"Unsupported dataset: {name}")
    return meta.get("alias_for", key)


def dataset_meta(name: str) -> dict:
    return DATASETS[canonical_dataset(name)]


def resolve_split(name: str, split: str) -> str:
    meta = dataset_meta(name)
    if not split or split == "default":
        return meta["default_split"]
    if split not in meta["splits"]:
        raise ValueError(
            f"Unsupported split for {meta['name']}: {split}. "
            f"Available: {', '.join(meta['splits'])}"
        )
    return split


def ensure_root_path(root: str, *parts: str) -> str:
    base = os.path.abspath(root)
    target = os.path.abspath(os.path.join(base, *parts))
    if target != base and not target.startswith(base + os.sep):
        raise ValueError("Invalid dataset path")
    return target


def to_builtin(value: Any) -> Any:
    if hasattr(value, "tolist"):
        return to_builtin(value.tolist())
    if isinstance(value, dict):
        return {str(k): to_builtin(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_builtin(v) for v in value]
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def read_parquet(path: str) -> pd.DataFrame:
    return pd.read_parquet(path)


def stable_shuffle(items: List[Any], seed: str) -> List[Any]:
    shuffled = list(items)
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    rng = random.Random(int(digest[:16], 16))
    rng.shuffle(shuffled)
    return shuffled


def iter_mmlu(root: str, split: str) -> Iterable[dict]:
    for path in sorted(os.listdir(ensure_root_path(root, "MMLU", split))):
        if not path.endswith(".csv"):
            continue
        subject = path.rsplit(f"_{split}.csv", 1)[0]
        full_path = ensure_root_path(root, "MMLU", split, path)
        with open(full_path, encoding="utf-8", errors="replace") as f:
            for idx, row in enumerate(csv.reader(f)):
                if len(row) < 6:
                    continue
                yield {
                    "id": f"{subject}/{idx}",
                    "task_type": "choice",
                    "question": row[0],
                    "options": dict(zip("ABCD", row[1:5])),
                    "answer": row[5].strip().upper(),
                    "meta": {"dataset": "MMLU", "subject": subject},
                }


def iter_cmmlu(root: str, split: str) -> Iterable[dict]:
    base = ensure_root_path(root, "CMMLU", "data", split)
    for path in sorted(os.listdir(base)):
        if not path.endswith(".csv"):
            continue
        subject = path[:-4]
        with open(os.path.join(base, path), encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            for row in reader:
                yield {
                    "id": f"{subject}/{row.get('', row.get('id', ''))}",
                    "task_type": "choice",
                    "question": row["Question"],
                    "options": {label: row[label] for label in "ABCD"},
                    "answer": row["Answer"].strip().upper(),
                    "meta": {"dataset": "CMMLU", "subject": subject},
                }


def iter_ceval(root: str, split: str) -> Iterable[dict]:
    base = ensure_root_path(root, "C-Eval")
    for subject in sorted(os.listdir(base)):
        subject_dir = os.path.join(base, subject)
        if not os.path.isdir(subject_dir) or subject.startswith("."):
            continue
        path = os.path.join(subject_dir, f"{split}-00000-of-00001.parquet")
        if not os.path.exists(path):
            continue
        for row in read_parquet(path).to_dict("records"):
            yield {
                "id": f"{subject}/{row['id']}",
                "task_type": "choice",
                "question": row["question"],
                "options": {label: row[label] for label in "ABCD"},
                "answer": str(row["answer"]).strip().upper(),
                "meta": {"dataset": "C-Eval", "subject": subject},
            }


def iter_mmlu_pro(root: str, split: str) -> Iterable[dict]:
    path = ensure_root_path(root, "MMLU-Pro", "data", f"{split}-00000-of-00001.parquet")
    for row in read_parquet(path).to_dict("records"):
        options = to_builtin(row["options"])
        labels = CHOICE_LABELS[: len(options)]
        yield {
            "id": str(row["question_id"]),
            "task_type": "choice",
            "question": row["question"],
            "options": dict(zip(labels, options)),
            "answer": str(row["answer"]).strip().upper(),
            "meta": {
                "dataset": "MMLU-Pro",
                "category": row.get("category"),
                "src": row.get("src"),
            },
        }


def iter_arc_challenge(root: str, split: str) -> Iterable[dict]:
    path = ensure_root_path(
        root, "ARC", "ARC-Challenge", f"{split}-00000-of-00001.parquet"
    )
    for row in read_parquet(path).to_dict("records"):
        choices = to_builtin(row["choices"])
        yield {
            "id": str(row["id"]),
            "task_type": "choice",
            "question": row["question"],
            "options": dict(zip(choices["label"], choices["text"])),
            "answer": str(row["answerKey"]).strip().upper(),
            "meta": {"dataset": "ARC-Challenge"},
        }


def iter_gsm8k(root: str, split: str) -> Iterable[dict]:
    path = ensure_root_path(root, "GSM8K", "main", f"{split}-00000-of-00001.parquet")
    for idx, row in enumerate(read_parquet(path).to_dict("records")):
        yield {
            "id": f"gsm8k/{idx}",
            "task_type": "math",
            "question": row["question"],
            "reference": row["answer"],
            "answer": extract_gsm8k_answer(row["answer"]),
            "meta": {"dataset": "GSM8K"},
        }


def iter_squad(root: str, split: str) -> Iterable[dict]:
    path = ensure_root_path(
        root, "SQuAD", "plain_text", f"{split}-00000-of-00001.parquet"
    )
    for row in read_parquet(path).to_dict("records"):
        answers = to_builtin(row["answers"])
        refs = answers.get("text", []) if isinstance(answers, dict) else []
        yield {
            "id": str(row["id"]),
            "task_type": "qa",
            "question": row["question"],
            "context": row["context"],
            "references": refs,
            "meta": {"dataset": "SQuAD", "title": row.get("title")},
        }


def iter_truthfulqa_generation(root: str, split: str) -> Iterable[dict]:
    path = ensure_root_path(
        root, "TruthfulQA", "generation", f"{split}-00000-of-00001.parquet"
    )
    for idx, row in enumerate(read_parquet(path).to_dict("records")):
        yield {
            "id": f"truthfulqa/{idx}",
            "task_type": "generation",
            "question": row["question"],
            "reference": row["best_answer"],
            "references": to_builtin(row.get("correct_answers", [])),
            "meta": {
                "dataset": "TruthfulQA generation",
                "category": row.get("category"),
                "type": row.get("type"),
                "source": row.get("source"),
            },
        }


def drop_answer_references(answer: Any) -> List[str]:
    answer = to_builtin(answer)
    refs = []
    if not isinstance(answer, dict):
        return refs

    number = answer.get("number")
    if number:
        refs.append(str(number))

    date = answer.get("date")
    if isinstance(date, dict):
        date_parts = [
            str(date.get(key, "")).strip()
            for key in ["day", "month", "year"]
            if str(date.get(key, "")).strip()
        ]
        if date_parts:
            refs.append(" ".join(date_parts))

    spans = answer.get("spans", [])
    if isinstance(spans, str):
        spans = [spans]
    if isinstance(spans, list):
        refs.extend(str(span) for span in spans if str(span).strip())

    return refs


def iter_drop(root: str, split: str) -> Iterable[dict]:
    path = ensure_root_path(root, "DROP", f"drop_{split}.parquet")
    for row in read_parquet(path).to_dict("records"):
        refs = drop_answer_references(row.get("answer"))
        validated = to_builtin(row.get("validated_answers"))
        if isinstance(validated, dict):
            count = max(
                [
                    len(value)
                    for value in validated.values()
                    if isinstance(value, list)
                ]
                or [0]
            )
            for idx in range(count):
                refs.extend(
                    drop_answer_references(
                        {
                            "number": (
                                validated.get("number", [None] * count)[idx]
                                if idx < len(validated.get("number", []))
                                else None
                            ),
                            "date": (
                                validated.get("date", [None] * count)[idx]
                                if idx < len(validated.get("date", []))
                                else None
                            ),
                            "spans": (
                                validated.get("spans", [None] * count)[idx]
                                if idx < len(validated.get("spans", []))
                                else None
                            ),
                        }
                    )
                )

        unique_refs = []
        seen = set()
        for ref in refs:
            key = normalize_text(ref)
            if key and key not in seen:
                seen.add(key)
                unique_refs.append(ref)

        yield {
            "id": str(row["query_id"]),
            "task_type": "qa",
            "question": row["question"],
            "context": row["passage"],
            "references": unique_refs,
            "meta": {"dataset": "DROP", "section_id": row.get("section_id")},
        }


def iter_gpqa(root: str, split: str) -> Iterable[dict]:
    path = ensure_root_path(root, "GPQA", f"gpqa_{split}.csv")
    with open(path, encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader):
            correct = str(row["Correct Answer"]).strip()
            choices = [
                ("correct", correct),
                ("incorrect", str(row["Incorrect Answer 1"]).strip()),
                ("incorrect", str(row["Incorrect Answer 2"]).strip()),
                ("incorrect", str(row["Incorrect Answer 3"]).strip()),
            ]
            choices = stable_shuffle(
                choices, f"gpqa:{split}:{row.get('Record ID') or idx}"
            )
            labels = CHOICE_LABELS[: len(choices)]
            options = {label: text for label, (_, text) in zip(labels, choices)}
            answer = next(
                label
                for label, (kind, _) in zip(labels, choices)
                if kind == "correct"
            )
            yield {
                "id": str(row.get("Record ID") or idx),
                "task_type": "choice",
                "question": row["Question"],
                "options": options,
                "answer": answer,
                "meta": {
                    "dataset": "GPQA",
                    "subset": split,
                    "domain": row.get("High-level domain"),
                    "subdomain": row.get("Subdomain"),
                },
            }


def iter_math(root: str, split: str) -> Iterable[dict]:
    path = ensure_root_path(root, "MATH", "data", f"{split}-00000-of-00001.parquet")
    for idx, row in enumerate(read_parquet(path).to_dict("records")):
        yield {
            "id": str(row.get("unique_id") or f"math/{split}/{idx}"),
            "task_type": "math",
            "question": row["problem"],
            "reference": row["solution"],
            "answer": row["answer"],
            "meta": {
                "dataset": "MATH",
                "subject": row.get("subject"),
                "level": row.get("level"),
            },
        }


def iter_humaneval(root: str, split: str) -> Iterable[dict]:
    path = ensure_root_path(
        root, "HumanEval", "openai_humaneval", "test-00000-of-00001.parquet"
    )
    for row in read_parquet(path).to_dict("records"):
        yield {
            "id": str(row["task_id"]),
            "task_type": "code_generation",
            "question": row["prompt"],
            "reference": row["canonical_solution"],
            "meta": {
                "dataset": "HumanEval",
                "entry_point": row.get("entry_point"),
                "test": row.get("test"),
            },
        }


def iter_ifeval(root: str, split: str) -> Iterable[dict]:
    path = ensure_root_path(root, "IFEval", "ifeval_input_data.jsonl")
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            yield {
                "id": str(row["key"]),
                "task_type": "instruction_following",
                "question": row["prompt"],
                "meta": {
                    "dataset": "IFEval",
                    "key": row["key"],
                    "instruction_id_list": row["instruction_id_list"],
                    "kwargs": row["kwargs"],
                },
            }


def iter_bbh(root: str, split: str) -> Iterable[dict]:
    tasks = BBH_TASKS if split == "all" else [split]
    for task in tasks:
        path = ensure_root_path(root, "BBH", task, "test-00000-of-00001.parquet")
        for idx, row in enumerate(read_parquet(path).to_dict("records")):
            yield {
                "id": f"{task}/{idx}",
                "task_type": "bbh",
                "question": row["input"],
                "answer": row["target"],
                "meta": {"dataset": "BBH", "task": task},
            }


def parse_json_list(value: Any) -> List[Any]:
    if not value:
        return []
    if isinstance(value, list):
        return value
    if not isinstance(value, str):
        return []
    try:
        parsed = json.loads(value)
    except Exception:
        return []
    return parsed if isinstance(parsed, list) else []


def parse_lcb_private_test_cases(value: Any) -> List[Any]:
    if not value:
        return []
    parsed = parse_json_list(value)
    if parsed:
        return parsed
    if not isinstance(value, str):
        return []
    try:
        decoded = pickle.loads(zlib.decompress(base64.b64decode(value.encode("utf-8"))))
        parsed = json.loads(decoded)
    except Exception:
        return []
    return parsed if isinstance(parsed, list) else []


def iter_livecodebench(root: str, split: str) -> Iterable[dict]:
    for file_name in LCB_FILES[split]:
        path = ensure_root_path(root, "LiveCodeBench", file_name)
        with open(path, encoding="utf-8", errors="replace") as f:
            for idx, line in enumerate(f):
                if not line.strip():
                    continue
                row = json.loads(line)
                public_cases = parse_json_list(row.get("public_test_cases"))
                private_raw = row.get("private_test_cases")
                metadata = {}
                try:
                    metadata = json.loads(row.get("metadata") or "{}")
                except Exception:
                    metadata = {}
                question_id = str(row.get("question_id") or idx)
                yield {
                    "id": f"{file_name}:{question_id}",
                    "task_type": "livecodebench",
                    "question": row.get("question_content", ""),
                    "title": row.get("question_title", ""),
                    "starter_code": row.get("starter_code", ""),
                    "public_test_cases": public_cases,
                    "_private_test_cases_raw": private_raw,
                    "meta": {
                        "dataset": "LiveCodeBench",
                        "platform": row.get("platform"),
                        "question_id": row.get("question_id"),
                        "contest_id": row.get("contest_id"),
                        "contest_date": row.get("contest_date"),
                        "difficulty": row.get("difficulty"),
                        "version_file": file_name,
                        "has_starter_code": bool(row.get("starter_code")),
                        "public_test_case_count": len(public_cases),
                        "has_private_test_cases": bool(private_raw),
                        "metadata": metadata,
                    },
                }


LOADERS = {
    "mmlu": iter_mmlu,
    "cmmlu": iter_cmmlu,
    "c-eval": iter_ceval,
    "mmlu-pro": iter_mmlu_pro,
    "arc-challenge": iter_arc_challenge,
    "gsm8k": iter_gsm8k,
    "squad": iter_squad,
    "truthfulqa-generation": iter_truthfulqa_generation,
    "drop": iter_drop,
    "gpqa": iter_gpqa,
    "math": iter_math,
    "humaneval": iter_humaneval,
    "ifeval": iter_ifeval,
    "bbh": iter_bbh,
    "livecodebench": iter_livecodebench,
}


def load_samples(
    root: str, dataset: str, split: str, limit: Optional[int] = None
) -> List[dict]:
    key = canonical_dataset(dataset)
    resolved_split = resolve_split(key, split)
    samples = []
    for sample in LOADERS[key](root, resolved_split):
        samples.append(sample)
        if limit and len(samples) >= limit:
            break
    return samples


def list_datasets(root: str) -> List[dict]:
    rows = []
    for key, meta in DATASETS.items():
        if "alias_for" in meta:
            continue
        rows.append(
            {
                "dataset": meta["name"],
                "key": key,
                "task_type": meta["type"],
                "default_split": meta["default_split"],
                "splits": meta["splits"],
                "metrics": meta["metrics"],
                "available": dataset_available(root, key),
            }
        )
    return rows


def dataset_available(root: str, key: str) -> bool:
    try:
        samples = load_samples(root, key, "default", limit=1)
        return bool(samples)
    except Exception:
        return False


def sample_for_inspect(sample: dict) -> dict:
    return {key: value for key, value in sample.items() if not key.startswith("_")}


def count_jsonl(path: str) -> int:
    count = 0
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.strip():
                count += 1
    return count


def count_samples(root: str, dataset: str, split: str) -> int:
    key = canonical_dataset(dataset)
    resolved_split = resolve_split(key, split)
    if key == "livecodebench":
        return sum(
            count_jsonl(ensure_root_path(root, "LiveCodeBench", file_name))
            for file_name in LCB_FILES[resolved_split]
        )
    return len(load_samples(root, key, resolved_split, limit=None))


def inspect_dataset(root: str, dataset: str, split: str) -> dict:
    key = canonical_dataset(dataset)
    meta = dataset_meta(key)
    resolved_split = resolve_split(key, split)
    samples = [sample_for_inspect(s) for s in load_samples(root, key, resolved_split, limit=3)]
    total = count_samples(root, key, resolved_split)
    return {
        "dataset": meta["name"],
        "key": key,
        "task_type": meta["type"],
        "split": resolved_split,
        "total": total,
        "metrics": meta["metrics"],
        "samples": samples,
    }


def choice_prompt(sample: dict) -> str:
    options = "\n".join(
        f"{label}. {text}" for label, text in sample.get("options", {}).items()
    )
    labels = "/".join(sample.get("options", {}).keys())
    return (
        f"{sample['question']}\n\n"
        f"{options}\n\n"
        f"请从给定选项中选择正确答案。只输出选项字母，多个答案连续输出。\n"
        f"可选项: {labels}"
    )


def livecodebench_prompt(sample: dict) -> str:
    title = sample.get("title") or sample.get("meta", {}).get("question_id") or ""
    platform = str(sample.get("meta", {}).get("platform") or "").lower()
    starter_code = sample.get("starter_code") or ""

    parts = []
    if title:
        parts.append(f"题目标题：{title}")
    if platform:
        parts.append(f"平台：{platform}")
    parts.append(f"题目内容：\n{sample['question']}")

    if starter_code:
        parts.append(f"Starter code:\n```python\n{starter_code}\n```")
        parts.append(
            "请补全 Python 代码。最终答案只输出代码，不要输出解释或 Markdown 代码块。"
        )
    else:
        parts.append(
            "请输出完整 Python 3 程序，从标准输入读取并向标准输出打印。"
            "最终答案只输出代码，不要输出解释或 Markdown 代码块。"
        )

    return "\n\n".join(parts)


def generation_prompt(sample: dict) -> str:
    if sample["task_type"] == "code_generation":
        return (
            f"{sample['question']}\n\n"
            f"请补全上述 Python 函数。只输出代码，不要解释，不要 Markdown 代码块。"
        )
    if sample["task_type"] == "livecodebench":
        return livecodebench_prompt(sample)
    if sample["task_type"] == "bbh":
        return f"{sample['question']}\n\n请只输出最终答案，不要解释。"
    if sample["task_type"] == "instruction_following":
        return sample["question"]
    if sample.get("context"):
        return (
            f"参考文本：\n{sample['context']}\n\n"
            f"问题：{sample['question']}\n\n"
            f"请只输出最短答案，不要解释。"
        )
    if sample["task_type"] == "math":
        return f"{sample['question']}\n\n请给出解题过程，并在最后用 \\boxed{{}} 给出最终答案。"
    return sample["question"]


def call_model(client: OpenAI, model: str, sample: dict, max_retries: int = 3) -> str:
    prompt = (
        choice_prompt(sample)
        if sample["task_type"] == "choice"
        else generation_prompt(sample)
    )
    messages = [{"role": "user", "content": prompt}]
    extra_body = None
    if sample["task_type"] == "livecodebench":
        messages = [
            {
                "role": "system",
                "content": (
                    "你是代码生成器。最终答案只输出可执行代码，不要输出解释、"
                    "Markdown 代码块或自然语言说明。"
                ),
            },
            {"role": "user", "content": prompt},
        ]
    last_error = None

    for attempt in range(max_retries):
        try:
            request_kwargs = {
                "model": model,
                "messages": messages,
                "temperature": 0,
                "top_p": 1,
                "max_tokens": 4096,
                "timeout": 60,
            }
            if extra_body:
                request_kwargs["extra_body"] = extra_body
            resp = client.chat.completions.create(**request_kwargs)
            return resp.choices[0].message.content.strip()
        except Exception as e:
            last_error = e
            error_text = str(e)
            if extra_body and (
                "chat_template_kwargs" in error_text
                or "enable_thinking" in error_text
                or "extra_body" in error_text
            ):
                extra_body = None
            time.sleep(2**attempt)

    return f"ERROR: {last_error}"


def extract_choice(text: str, valid_options: Iterable[str]) -> Optional[str]:
    options = list(valid_options)
    if not text:
        return None
    answer_text = extract_answer_text(text)
    upper = answer_text.upper().strip()

    try:
        parsed = json.loads(answer_text)
        value = str(parsed.get("answer", "")).upper().strip()
        if value and set(value).issubset(set(options)):
            return value
    except Exception:
        pass

    option_chars = "".join(re.escape(x) for x in options)
    patterns = [
        rf"\\BOXED\{{\s*([{option_chars}]+)\s*\}}",
        rf"(?:ANSWER|答案|选项|选择|正确答案)\s*(?:IS|为|是|:|：)?\s*([{option_chars}]+)\b",
        rf"^\s*([{option_chars}]+)\s*$",
        rf"^\s*\(?([{option_chars}]+)\)?(?:[\.。:：]|$)",
    ]

    for pattern in patterns:
        match = re.search(pattern, upper)
        if match and set(match.group(1)).issubset(set(options)):
            return match.group(1)

    tokens = re.findall(r"\b[A-Z]\b", upper)
    matches = [token for token in tokens if token in options]
    if len(matches) == 1:
        return matches[0]

    return None


def extract_answer_text(text: str) -> str:
    """Return the visible final answer, excluding model thinking traces."""
    if not text:
        return ""

    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r"</?think>", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip()
    return cleaned or text.strip()


def clean_code_completion(text: str) -> str:
    code = extract_answer_text(text)
    fence = re.search(r"```(?:python)?\s*(.*?)```", code, flags=re.IGNORECASE | re.DOTALL)
    if fence:
        code = fence.group(1)
    return code.strip("\n")


def build_humaneval_program(sample: dict, completion: str) -> str:
    prompt = sample.get("question") or ""
    entry_point = sample.get("meta", {}).get("entry_point")
    test = sample.get("meta", {}).get("test") or ""
    code = clean_code_completion(completion)

    if entry_point and re.search(rf"^\s*def\s+{re.escape(entry_point)}\s*\(", code, re.MULTILINE):
        solution = code
    else:
        solution = prompt + code

    return (
        f"{solution.rstrip()}\n\n"
        f"{test.rstrip()}\n\n"
        f"check({entry_point})\n"
    )


def truncate_text(text: str, limit: int = 2000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n... truncated ..."


def parse_lcb_official_output(text: str) -> dict:
    text = text or "{}"
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.rfind('{"details"')
        if start < 0:
            raise
        return json.loads(text[start:])


def docker_available(image: str) -> Optional[str]:
    if not shutil.which("docker"):
        return "docker command not found"
    try:
        subprocess.run(
            ["docker", "image", "inspect", image],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
            check=True,
        )
    except subprocess.TimeoutExpired:
        return f"Docker image inspect timed out: {image}"
    except subprocess.CalledProcessError as e:
        error = (e.stderr or e.stdout or "").strip()
        if "permission denied" in error.lower():
            return "docker permission denied; add the service user to the docker group"
        return f"Docker image not found: {image}"
    return None


def classify_humaneval_failure(returncode: int, stderr: str) -> str:
    stderr_lower = (stderr or "").lower()
    if "docker api" in stderr_lower or "permission denied" in stderr_lower:
        return "docker_error"
    if returncode == 124:
        return "timeout"
    if returncode in {125, 126, 127}:
        return "docker_error"
    if "SyntaxError" in stderr or "IndentationError" in stderr:
        return "syntax_error"
    if "AssertionError" in stderr:
        return "assertion_error"
    if returncode != 0:
        return "runtime_error"
    return ""


def execute_humaneval_docker(sample: dict, response: str, args) -> dict:
    start = time.time()
    program = build_humaneval_program(sample, response)
    container_name = f"humaneval_{os.getpid()}_{sample.get('_index', 0)}_{int(start * 1000)}"

    cmd = [
        "docker",
        "run",
        "--rm",
        "-i",
        "--name",
        container_name,
        "--network",
        "none",
        "--memory",
        args.humaneval_memory,
        "--cpus",
        str(args.humaneval_cpus),
        "--pids-limit",
        str(args.humaneval_pids_limit),
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--user",
        "65534:65534",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,size=64m",
        "-e",
        "PYTHONDONTWRITEBYTECODE=1",
        args.humaneval_docker_image,
        "python",
        "-c",
        "import sys; exec(compile(sys.stdin.read(), '<humaneval>', 'exec'))",
    ]

    try:
        proc = subprocess.run(
            cmd,
            input=program,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=args.humaneval_timeout + 2,
        )
    except subprocess.TimeoutExpired as e:
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return {
            "model_answer": clean_code_completion(response),
            "executed": True,
            "passed": False,
            "error_type": "timeout",
            "error": f"timeout after {args.humaneval_timeout}s",
            "stdout": truncate_text(e.stdout or ""),
            "stderr": truncate_text(e.stderr or ""),
            "duration_sec": round(time.time() - start, 4),
        }

    stdout = truncate_text(proc.stdout or "")
    stderr = truncate_text(proc.stderr or "")
    error_type = classify_humaneval_failure(proc.returncode, stderr)
    return {
        "model_answer": clean_code_completion(response),
        "executed": True,
        "passed": proc.returncode == 0,
        "error_type": error_type,
        "error": "" if proc.returncode == 0 else truncate_text(stderr or stdout),
        "stdout": stdout,
        "stderr": stderr,
        "duration_sec": round(time.time() - start, 4),
    }


def indent_code(code: str, spaces: int = 4) -> str:
    prefix = " " * spaces
    return "\n".join(prefix + line if line.strip() else line for line in code.splitlines())


def build_lcb_functional_solution(sample: dict, response: str) -> str:
    code = clean_code_completion(response).strip()
    starter_code = sample.get("starter_code") or ""
    func_name = sample.get("meta", {}).get("metadata", {}).get("func_name")

    if "class Solution" in code:
        solution = code
    elif func_name and re.search(rf"^\s*def\s+{re.escape(func_name)}\s*\(", code, re.MULTILINE):
        solution = "class Solution:\n" + indent_code(code)
    else:
        solution = starter_code + code

    return (
        "from __future__ import annotations\n"
        "from typing import *\n"
        "from collections import *\n"
        "from functools import *\n"
        "from itertools import *\n"
        "from math import *\n"
        "import bisect, heapq, re, string, sys\n\n"
        f"{solution.rstrip()}\n"
    )


def lcb_testtype(sample: dict) -> str:
    cases = sample.get("public_test_cases") or []
    if not cases:
        return ""
    return str(cases[0].get("testtype") or "")


def build_lcb_official_code(sample: dict, response: str) -> str:
    if lcb_testtype(sample) == "functional":
        return build_lcb_functional_solution(sample, response)
    return clean_code_completion(response).strip() + "\n"


def lcb_private_test_cases(sample: dict) -> List[Any]:
    if "_private_test_cases" not in sample:
        sample["_private_test_cases"] = parse_lcb_private_test_cases(
            sample.get("_private_test_cases_raw")
        )
    return sample.get("_private_test_cases") or []


def lcb_eval_sample(sample: dict) -> dict:
    tests = (sample.get("public_test_cases") or []) + lcb_private_test_cases(sample)
    return {
        "input_output": json.dumps(
            {
                "inputs": [str(test.get("input", "")) for test in tests],
                "outputs": [str(test.get("output", "")) for test in tests],
                "fn_name": sample.get("meta", {}).get("metadata", {}).get("func_name"),
            }
        )
    }


def lcb_official_payload(samples: List[dict], details: List[dict]) -> List[dict]:
    detail_by_index = {detail.get("_index"): detail for detail in details}
    payload = []
    for sample in samples:
        detail = detail_by_index.get(sample.get("_index"))
        if not detail:
            continue
        payload.append(
            {
                "index": sample.get("_index"),
                "question_id": sample.get("meta", {}).get("question_id"),
                "eval_sample": lcb_eval_sample(sample),
                "generation": build_lcb_official_code(sample, detail.get("response", "")),
                "public_total": len(sample.get("public_test_cases") or []),
                "private_total": len(lcb_private_test_cases(sample)),
            }
        )
    payload.sort(key=lambda item: str(item.get("question_id")))
    return payload


def lcb_official_docker_runner() -> str:
    return r'''
import json
import os
import sys
import time

sys.path.insert(0, "/evaluator")

from lcb_runner.evaluation import codegen_metrics
from lcb_runner.evaluation.pass_k_utils import extract_instance_results


def main():
    start = time.time()
    payload = json.load(sys.stdin)

    items = payload["items"]
    eval_samples = [item["eval_sample"] for item in items]
    generations = [[item["generation"]] for item in items]
    metrics, raw_results, metadata = codegen_metrics(
        eval_samples,
        generations,
        k_list=[1],
        num_process_evaluate=max(1, int(payload.get("num_process", 1))),
        timeout=int(payload.get("timeout", 8)),
    )
    graded = extract_instance_results(raw_results)

    details = []
    for idx, item in enumerate(items):
        grades = graded[idx] if idx < len(graded) else []
        passed = bool(grades and grades[0])
        case_results = raw_results.get(idx, [[]])
        if case_results and isinstance(case_results[0], list):
            case_passed = sum(
                1
                for value in case_results[0]
                if value is True or (isinstance(value, (int, float)) and value > 0)
            )
            case_total = len(case_results[0])
        else:
            case_passed = 0
            case_total = 0
        details.append(
            {
                "index": item["index"],
                "model_answer": item["generation"],
                "executed": True,
                "passed": passed,
                "official_score": True,
                "official_pending": False,
                "error_type": "" if passed else "wrong_answer",
                "public_total": item.get("public_total", 0),
                "private_total": item.get("private_total", 0),
                "case_total": case_total,
                "case_passed": case_passed,
                "official_metadata": metadata[idx][0] if idx < len(metadata) and metadata[idx] else "",
                "duration_sec": round(time.time() - start, 4),
            }
        )

    json.dump({"details": details}, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
'''


def run_lcb_official_docker_batch(payload_items: List[dict], args, batch_index: int) -> dict:
    start = time.time()
    container_name = f"lcb_official_{os.getpid()}_{batch_index}_{int(start * 1000)}"
    timeout = int(args.lcb_timeout) * max(1, len(payload_items)) * 50 + 30
    payload = json.dumps(
        {
            "items": payload_items,
            "timeout": int(args.lcb_timeout),
            "num_process": int(args.lcb_num_process),
        },
        ensure_ascii=False,
    )

    cmd = [
        "docker",
        "run",
        "--rm",
        "-i",
        "--name",
        container_name,
        "--network",
        "none",
        "--memory",
        args.lcb_memory,
        "--cpus",
        str(args.lcb_cpus),
        "--pids-limit",
        str(args.lcb_pids_limit),
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,size=256m",
        "-e",
        "PYTHONDONTWRITEBYTECODE=1",
        args.lcb_docker_image,
        "python",
        "-c",
        lcb_official_docker_runner(),
    ]
    try:
        proc = subprocess.run(
            cmd,
            input=payload,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        raise RuntimeError(
            f"LiveCodeBench official docker timeout: {truncate_text(e.stderr or e.stdout or '')}"
        )

    if proc.returncode != 0:
        raise RuntimeError(
            "LiveCodeBench official docker failed: "
            + truncate_text(proc.stderr or proc.stdout or "")
        )
    try:
        result = parse_lcb_official_output(proc.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            "LiveCodeBench official docker produced invalid output: "
            + truncate_text(f"{e}\n{proc.stdout or proc.stderr or ''}")
        )
    return result


def apply_lcb_official_docker_scores(
    root: str,
    samples: List[dict],
    details: List[dict],
    args,
) -> None:
    payload_items = lcb_official_payload(samples, details)
    if not payload_items:
        return

    docker_error = docker_available(args.lcb_docker_image)
    if docker_error:
        raise RuntimeError(f"Docker executor unavailable: {docker_error}")

    batch_size = max(1, int(getattr(args, "lcb_batch_size", 50) or 50))
    result_details = []
    for batch_index, start in enumerate(range(0, len(payload_items), batch_size), start=1):
        batch = payload_items[start : start + batch_size]
        result = run_lcb_official_docker_batch(batch, args, batch_index)
        result_details.extend(result.get("details", []))

    score_by_index = {item["index"]: item for item in result_details}
    for detail in details:
        score = score_by_index.get(detail.get("_index"))
        if score:
            detail.update(score)


def normalize_text(text: str) -> str:
    text = extract_answer_text(text)
    text = text.lower()
    text = re.sub(r"\b(a|an|the)\b", " ", text)
    text = "".join(ch for ch in text if ch not in string.punctuation)
    return " ".join(text.split())


def qa_f1(prediction: str, reference: str) -> float:
    pred_tokens = normalize_text(prediction).split()
    ref_tokens = normalize_text(reference).split()
    if not pred_tokens and not ref_tokens:
        return 1.0
    if not pred_tokens or not ref_tokens:
        return 0.0
    common = set(pred_tokens) & set(ref_tokens)
    overlap = sum(min(pred_tokens.count(t), ref_tokens.count(t)) for t in common)
    if overlap == 0:
        return 0.0
    precision = overlap / len(pred_tokens)
    recall = overlap / len(ref_tokens)
    return 2 * precision * recall / (precision + recall)


def extract_gsm8k_answer(text: str) -> str:
    match = re.search(r"####\s*([-+]?\d[\d,]*(?:\.\d+)?)", text)
    if match:
        return match.group(1).replace(",", "")
    return extract_final_number(text) or ""


def extract_boxed_answer(text: str) -> Optional[str]:
    answers = []
    marker = r"\boxed{"
    start = 0
    while True:
        marker_idx = text.find(marker, start)
        if marker_idx == -1:
            break
        idx = marker_idx + len(marker)
        depth = 1
        chars = []
        while idx < len(text) and depth > 0:
            char = text[idx]
            if char == "{":
                depth += 1
                chars.append(char)
            elif char == "}":
                depth -= 1
                if depth > 0:
                    chars.append(char)
            else:
                chars.append(char)
            idx += 1
        if depth == 0:
            answers.append("".join(chars).strip())
        start = marker_idx + len(marker)
    return answers[-1] if answers else None


def extract_final_number(text: str) -> Optional[str]:
    matches = re.findall(r"[-+]?\d[\d,]*(?:\.\d+)?", text)
    if not matches:
        return None
    return matches[-1].replace(",", "")


def normalize_math_answer(text: str) -> str:
    text = extract_answer_text(str(text))
    boxed = extract_boxed_answer(text)
    if boxed:
        text = boxed
    text = text.strip()
    text = re.sub(r"^\$+|\$+$", "", text)
    text = re.sub(r"\\left|\\right", "", text)
    text = re.sub(r"\\,", "", text)
    text = text.replace(",", "")
    text = re.sub(r"\s+", "", text)
    return text.lower()


def normalize_bbh_answer(text: str) -> str:
    text = extract_answer_text(str(text)).strip()
    text = re.sub(r"```(?:\w+)?\s*(.*?)```", r"\1", text, flags=re.DOTALL)
    text = re.sub(
        r"^(?:final\s+answer|answer|答案|最终答案)\s*(?:is|为|是|:|：)?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()
    text = text.strip("\"'` ")
    text = re.sub(r"\s+", " ", text)
    return text.lower()


def extract_bbh_prediction(response: str, target: str) -> str:
    answer_text = extract_answer_text(response).strip()
    if re.fullmatch(r"\([A-Z]\)", str(target).strip(), flags=re.IGNORECASE):
        matches = re.findall(r"\([A-Z]\)", answer_text.upper())
        if matches:
            return matches[-1]
        matches = re.findall(
            r"(?:ANSWER|答案|选项|最终答案)\s*(?:IS|为|是|:|：)?\s*([A-Z])\b",
            answer_text.upper(),
        )
        if matches:
            return f"({matches[-1]})"

    target_norm = normalize_bbh_answer(target)
    if target_norm in {"true", "false"}:
        matches = re.findall(r"\b(?:true|false)\b", answer_text, flags=re.IGNORECASE)
        if matches:
            return matches[-1]
    if target_norm in {"yes", "no"}:
        matches = re.findall(r"\b(?:yes|no)\b", answer_text, flags=re.IGNORECASE)
        if matches:
            return matches[-1]
    if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", target_norm):
        final_number = extract_final_number(answer_text)
        if final_number:
            return final_number

    lines = [line.strip() for line in answer_text.splitlines() if line.strip()]
    if lines:
        answer_text = lines[-1]
    answer_text = re.sub(
        r"^(?:final\s+answer|answer|答案|最终答案)\s*(?:is|为|是|:|：)?\s*",
        "",
        answer_text,
        flags=re.IGNORECASE,
    ).strip()
    return answer_text


def load_ifeval_lib(root: str):
    evaluator_dir = ensure_root_path(root, "IFEval", "evaluator")
    nltk_data_dir = ensure_root_path(root, "IFEval", "nltk_data")
    if os.path.isdir(nltk_data_dir):
        try:
            import nltk

            if nltk_data_dir not in nltk.data.path:
                nltk.data.path.insert(0, nltk_data_dir)
        except Exception:
            pass

    package_name = "instruction_following_eval"
    package = sys.modules.get(package_name)
    if package is None:
        import types

        package = types.ModuleType(package_name)
        package.__path__ = [evaluator_dir]
        sys.modules[package_name] = package
    elif not hasattr(package, "__path__"):
        package.__path__ = [evaluator_dir]
    elif evaluator_dir not in package.__path__:
        package.__path__.append(evaluator_dir)

    return importlib.import_module(f"{package_name}.evaluation_lib")


def score_ifeval_sample(sample: dict, response: str, args=None) -> dict:
    model_answer = extract_answer_text(response)
    if not args:
        return {"model_answer": model_answer, "evaluator_error": True}

    try:
        evaluation_lib = load_ifeval_lib(args.dataset_root)
        inp = evaluation_lib.InputExample(
            key=int(sample["meta"]["key"]),
            instruction_id_list=sample["meta"]["instruction_id_list"],
            prompt=sample["question"],
            kwargs=sample["meta"]["kwargs"],
        )
        prompt_to_response = {sample["question"]: model_answer}
        strict = evaluation_lib.test_instruction_following_strict(
            inp, prompt_to_response
        )
        loose = evaluation_lib.test_instruction_following_loose(inp, prompt_to_response)
        return {
            "model_answer": model_answer,
            "strict_follow_all": strict.follow_all_instructions,
            "strict_instruction_following_list": strict.follow_instruction_list,
            "loose_follow_all": loose.follow_all_instructions,
            "loose_instruction_following_list": loose.follow_instruction_list,
            "evaluator_error": False,
        }
    except Exception as e:
        return {
            "model_answer": model_answer,
            "strict_follow_all": False,
            "strict_instruction_following_list": [],
            "loose_follow_all": False,
            "loose_instruction_following_list": [],
            "evaluator_error": True,
            "error": truncate_text(str(e)),
        }


def extract_math_prediction(text: str) -> str:
    answer_text = extract_answer_text(text)
    boxed = extract_boxed_answer(answer_text)
    if boxed:
        return boxed
    final_number = extract_final_number(answer_text)
    if final_number:
        return final_number
    return answer_text.strip()


def score_sample(sample: dict, response: str, args=None) -> dict:
    task_type = sample["task_type"]

    if task_type == "choice":
        predicted = extract_choice(response, sample["options"].keys())
        is_correct = predicted == sample["answer"]
        return {
            "prediction": predicted,
            "is_correct": is_correct,
            "invalid": predicted is None,
        }

    if task_type == "math":
        predicted = extract_math_prediction(response)
        is_correct = normalize_math_answer(predicted) == normalize_math_answer(
            sample.get("answer", "")
        )
        return {"prediction": predicted, "is_correct": is_correct, "invalid": False}

    if task_type == "qa":
        refs = sample.get("references", [])
        model_answer = extract_answer_text(response)
        em = max(
            [normalize_text(model_answer) == normalize_text(ref) for ref in refs]
            or [False]
        )
        f1 = max([qa_f1(model_answer, ref) for ref in refs] or [0.0])
        return {"model_answer": model_answer, "exact_match": em, "f1": f1}

    if task_type == "bbh":
        predicted = extract_bbh_prediction(response, sample.get("answer", ""))
        is_correct = normalize_bbh_answer(predicted) == normalize_bbh_answer(
            sample.get("answer", "")
        )
        return {
            "prediction": predicted,
            "is_correct": is_correct,
            "invalid": not bool(predicted.strip()),
        }

    if task_type == "instruction_following":
        return score_ifeval_sample(sample, response, args)

    if task_type == "code_generation":
        if args and args.humaneval_executor == "docker":
            return execute_humaneval_docker(sample, response, args)
        return {"model_answer": clean_code_completion(response), "executed": False}

    if task_type == "livecodebench":
        official_pending = bool(args and args.lcb_executor == "official_docker")
        return {
            "model_answer": clean_code_completion(response),
            "executed": False,
            "official_score": False,
            "official_pending": official_pending,
        }

    return {"model_answer": extract_answer_text(response)}


def process_sample(client: OpenAI, model: str, sample: dict, args=None) -> dict:
    response = call_model(client, model, sample)
    scored = score_sample(sample, response, args)
    return {
        "id": sample.get("id"),
        "_index": sample.get("_index"),
        "task_type": sample["task_type"],
        "question": sample.get("question"),
        "answer": sample.get("answer"),
        "reference": sample.get("reference"),
        "references": sample.get("references"),
        "response": response,
        "meta": sample.get("meta", {}),
        **scored,
    }


def summarize(
    dataset: str,
    split: str,
    task_type: str,
    details: List[dict],
    total: Optional[int] = None,
) -> dict:
    processed = len(details)
    if total is None:
        total = processed
    summary = {
        "dataset": dataset,
        "split": split,
        "task_type": task_type,
        "total": total,
        "processed": processed,
        "progress": round(processed / total, 4) if total else 0,
        "metrics": {},
    }

    if task_type in ["choice", "math", "bbh"]:
        correct = sum(1 for x in details if x.get("is_correct"))
        invalid = sum(1 for x in details if x.get("invalid"))
        summary["metrics"] = {
            "correct": correct,
            "accuracy": round(correct / processed, 4) if processed else 0,
            "invalid": invalid,
            "invalid_rate": round(invalid / processed, 4) if processed else 0,
        }
        if task_type == "bbh":
            task_stats = {}
            for item in details:
                task = item.get("meta", {}).get("task", "unknown")
                stats = task_stats.setdefault(task, {"total": 0, "correct": 0})
                stats["total"] += 1
                if item.get("is_correct"):
                    stats["correct"] += 1
            summary["metrics"]["task_accuracy"] = {
                task: round(stats["correct"] / stats["total"], 4)
                for task, stats in sorted(task_stats.items())
                if stats["total"]
            }
    elif task_type == "qa":
        em = sum(1 for x in details if x.get("exact_match"))
        f1 = sum(float(x.get("f1", 0)) for x in details)
        summary["metrics"] = {
            "exact_match": round(em / processed, 4) if processed else 0,
            "avg_f1": round(f1 / processed, 4) if processed else 0,
        }
    elif task_type == "instruction_following":
        strict_prompt = sum(1 for x in details if x.get("strict_follow_all"))
        loose_prompt = sum(1 for x in details if x.get("loose_follow_all"))
        strict_instruction_total = sum(
            len(x.get("strict_instruction_following_list") or []) for x in details
        )
        loose_instruction_total = sum(
            len(x.get("loose_instruction_following_list") or []) for x in details
        )
        strict_instruction_correct = sum(
            sum(x.get("strict_instruction_following_list") or []) for x in details
        )
        loose_instruction_correct = sum(
            sum(x.get("loose_instruction_following_list") or []) for x in details
        )
        evaluator_error = sum(1 for x in details if x.get("evaluator_error"))
        summary["metrics"] = {
            "strict_prompt_accuracy": round(strict_prompt / processed, 4)
            if processed
            else 0,
            "strict_instruction_accuracy": round(
                strict_instruction_correct / strict_instruction_total, 4
            )
            if strict_instruction_total
            else 0,
            "loose_prompt_accuracy": round(loose_prompt / processed, 4)
            if processed
            else 0,
            "loose_instruction_accuracy": round(
                loose_instruction_correct / loose_instruction_total, 4
            )
            if loose_instruction_total
            else 0,
            "evaluator_error": evaluator_error,
        }
    elif task_type == "code_generation":
        executed = sum(1 for x in details if x.get("executed"))
        passed = sum(1 for x in details if x.get("passed"))
        timeout = sum(1 for x in details if x.get("error_type") == "timeout")
        executor_error = sum(
            1 for x in details if x.get("error_type") == "docker_error"
        )
        failed = executed - passed
        metrics = {
            "record_only": executed == 0,
            "executed": executed,
            "passed": passed,
            "failed": failed,
            "timeout": timeout,
            "executor_error": executor_error,
        }
        if executed:
            metrics["pass@1"] = round(passed / executed, 4)
        summary["metrics"] = metrics
    elif task_type == "livecodebench":
        executed = sum(1 for x in details if x.get("executed"))
        passed = sum(1 for x in details if x.get("passed"))
        pending = sum(1 for x in details if x.get("official_pending"))
        timeout = sum(1 for x in details if x.get("error_type") == "timeout")
        evaluator_error = sum(
            1 for x in details if x.get("error_type") == "evaluator_error"
        )
        case_total = sum(int(x.get("case_total") or 0) for x in details)
        case_passed = sum(int(x.get("case_passed") or 0) for x in details)
        official_score = any(x.get("official_score") for x in details)
        metrics = {
            "record_only": executed == 0 and pending == 0,
            "official_score": official_score,
            "evaluation_pending": pending > 0 and not official_score,
            "pending": pending,
            "executed": executed,
            "passed": passed,
            "failed": executed - passed,
            "timeout": timeout,
            "evaluator_error": evaluator_error,
            "case_total": case_total,
            "case_passed": case_passed,
        }
        if executed:
            metrics["pass@1"] = round(passed / executed, 4)
        if case_total:
            metrics["case_accuracy"] = round(case_passed / case_total, 4)
        summary["metrics"] = metrics
    else:
        summary["metrics"] = {"record_only": True}

    return summary


def save_result(
    path: Optional[str],
    dataset: str,
    split: str,
    task_type: str,
    details: List[dict],
    total: int,
):
    if not path:
        return

    ordered = sorted(details, key=lambda x: x.get("_index", 0))
    clean_details = []
    for detail in ordered:
        item = dict(detail)
        item.pop("_index", None)
        clean_details.append(item)

    result = {
        "summary": summarize(dataset, split, task_type, clean_details, total),
        "details": clean_details,
    }

    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def run(args):
    key = canonical_dataset(args.dataset)
    meta = dataset_meta(key)
    split = resolve_split(key, args.split)
    samples = load_samples(args.dataset_root, key, split, args.limit)
    total = len(samples)

    if key == "humaneval" and args.humaneval_executor == "docker":
        docker_error = docker_available(args.humaneval_docker_image)
        if docker_error:
            raise RuntimeError(f"Docker executor unavailable: {docker_error}")
    client = OpenAI(api_key=args.api_key, base_url=args.base_url)
    details = []

    max_workers = max(1, args.max_workers)
    save_every = max(1, args.save_every)
    for idx, sample in enumerate(samples):
        sample["_index"] = idx

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(process_sample, client, args.model, s, args) for s in samples
        ]
        for idx, future in enumerate(as_completed(futures), start=1):
            details.append(future.result())
            print(f"[{idx}/{len(samples)}] done", flush=True)

            if idx % save_every == 0:
                save_result(
                    args.output, meta["name"], split, meta["type"], details, total
                )

    if key == "livecodebench" and args.lcb_executor == "official_docker":
        try:
            apply_lcb_official_docker_scores(args.dataset_root, samples, details, args)
        except Exception as e:
            for detail in details:
                detail.update(
                    {
                        "executed": False,
                        "passed": False,
                        "official_score": False,
                        "official_pending": False,
                        "error_type": "evaluator_error",
                        "error": truncate_text(str(e)),
                    }
                )

    save_result(args.output, meta["name"], split, meta["type"], details, total)

    if not args.output:
        ordered = sorted(details, key=lambda x: x.get("_index", 0))
        for detail in ordered:
            detail.pop("_index", None)
        result = {
            "summary": summarize(meta["name"], split, meta["type"], ordered, total),
            "details": ordered,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))


def main():
    args = parse_args()
    random.seed(args.seed)

    if args.action == "list":
        print(
            json.dumps(list_datasets(args.dataset_root), ensure_ascii=False, indent=2)
        )
    elif args.action == "inspect":
        print(
            json.dumps(
                inspect_dataset(args.dataset_root, args.dataset, args.split),
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        run(args)


if __name__ == "__main__":
    main()
