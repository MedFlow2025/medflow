import argparse
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

from openai import OpenAI
from pydantic import BaseModel

os.makedirs("../benchmark/logs", exist_ok=True)


class OutputFormat(BaseModel):
    analyze: Optional[str] = None
    answer: str


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-key", default="EMPTY")
    parser.add_argument("--base-url", default="http://10.130.35.2:8000/v1")
    parser.add_argument("--model", default="model_medical_20250630")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output", default=None)
    parser.add_argument("--max-workers", type=int, default=1)
    parser.add_argument("--sleep", type=float, default=0.0)
    parser.add_argument("--save-every", type=int, default=2)
    parser.add_argument("--mode", default="eval", choices=["eval", "medbench"])
    return parser.parse_args()


def normalize_item(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "question": item.get("question") or item.get("prompt"),
        "answer": (item.get("answer") or item.get("label") or "").upper(),
        "options": item.get("options", None),
    }


def detect_options(item: Dict[str, Any]) -> List[str]:
    """Detect available options (A/B/C/...) from a question item."""

    if item.get("options"):
        return sorted(list(item["options"].keys()))

    question = item.get("question", "")

    pattern = r"\b([A-Z])[\.\、\)\．]"
    matches = re.findall(pattern, question)

    if matches:
        return sorted(list(set(matches)))

    return list("ABCDE")


def normalize_answer(ans: str) -> set:
    if not ans:
        return set()
    return set(re.findall(r"[A-Z]", ans.upper()))


def extract_answer_fallback(text: str, valid_options: List[str]) -> Optional[str]:
    """Extract the answer letter (A~Z) from the model response."""

    if not text:
        return None

    options_str = "".join(valid_options)
    if len(options_str) == 1:
        option_pattern = options_str
    elif all(
        ord(options_str[i + 1]) == ord(options_str[i]) + 1
        for i in range(len(options_str) - 1)
    ):
        option_pattern = f"{options_str[0]}-{options_str[-1]}"
    else:
        option_pattern = "(" + "|".join(valid_options) + ")"

    patterns = [
        rf"答案[：:]\s*([{option_pattern}])",
        rf"选项[：:]\s*([{option_pattern}])",
        rf"选择[：:]\s*([{option_pattern}])",
        rf"正确答案[：:]\s*([{option_pattern}])",
        rf"^\s*([{option_pattern}])\s*$",
        rf"\b([{option_pattern}])\b(?!\.\d)",  # Match a single letter not followed by a digit.
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).upper()

    # Try to find a single letter at the beginning or end of the response.
    words = text.split()
    for word in words:
        if len(word) == 1 and word.upper() in valid_options:
            return word.upper()

    return None


def call_model(
    client: OpenAI,
    model: str,
    question: str,
    ground_truth: str,
    options: List[str],
    max_retries: int = 3,
    timeout: int = 30,
):
    option_str = "/".join(options)
    prompt = f"""
{question}

你必须严格从选项中选择正确答案。

要求：
1. 只能输出JSON
2. 不要输出多余字段
3. answer只能在 {option_str} 中

格式：
{{"answer": "A"}}
或
{{"answer": "AC"}}
"""

    last_error = None
    for attempt in range(max_retries):
        try:
            resp = client.chat.completions.parse(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                top_p=1,
                max_tokens=4096,
                response_format=OutputFormat,
                timeout=timeout,
                # extra_body={"chat_template_kwargs": {"enable_thinking": True}}
            )
            return resp.choices[0].message.parsed

        except Exception as e:
            last_error = e

            sleep_time = 1 * (2**attempt)
            time.sleep(sleep_time)

    return f"ERROR: {last_error}"


def process_one(client, model, idx, item):
    item = normalize_item(item)
    question = item["question"]
    ground_truth = item["answer"]
    options = detect_options(item)

    response = call_model(client, model, question, ground_truth, options)

    predicted = None

    if isinstance(response, OutputFormat):
        predicted = response.answer
    else:
        predicted = extract_answer_fallback(str(response), options)
        # predicted = None

    if predicted:
        if not set(predicted).issubset(set(options)):
            predicted = None

    gt_set = normalize_answer(ground_truth)
    pred_set = normalize_answer(predicted)

    is_correct = pred_set == gt_set

    if gt_set and pred_set:
        precision = len(gt_set & pred_set) / len(pred_set)
        recall = len(gt_set & pred_set) / len(gt_set)
        f1 = (
            round(2 * precision * recall / (precision + recall), 4)
            if precision + recall
            else 0
        )
    else:
        f1 = 0

    return {
        "index": idx,
        "question": question,
        "ground_truth": ground_truth,
        "predicted": predicted,
        "is_correct": is_correct,
        "f1": f1,
        "invalid": predicted is None,
        "response": response.model_dump()
        if isinstance(response, OutputFormat)
        else str(response),
    }


def run_eval(args):
    client = OpenAI(api_key=args.api_key, base_url=args.base_url)

    with open(args.dataset, "r", encoding="utf-8") as f:
        data = json.load(f)

    results = []
    lock = threading.Lock()

    correct = 0
    invalid = 0
    f1_sum = 0

    def update_metrics(res):
        nonlocal correct, invalid, f1_sum
        if res["is_correct"]:
            correct += 1
        if res["invalid"]:
            invalid += 1
        f1_sum += res["f1"]

    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futures = [
            executor.submit(process_one, client, args.model, i + 1, item)
            for i, item in enumerate(data)
        ]
        total = len(data)

        for idx, future in enumerate(as_completed(futures), start=1):
            res = future.result()

            with lock:
                results.append(res)
                update_metrics(res)

                if idx % args.save_every == 0:
                    save_partial(
                        args.output, results, correct, invalid, f1_sum, total, idx
                    )

            print(f"[{idx}/{total}] done")

            if args.sleep:
                time.sleep(args.sleep)

    save_partial(args.output, results, correct, invalid, f1_sum, total, total)
    print("DONE")


def save_partial(path, results, correct, invalid, f1_sum, total, processed):
    if path is None:
        return

    summary = {
        "total": total,
        "processed": processed,
        "progress": round(processed / total, 4) if total else 0,
        "correct": correct,
        "accuracy": round(correct / processed, 4) if processed else 0,
        "invalid": invalid,
        "invalid_rate": round(invalid / processed, 4) if processed else 0,
        "avg_f1": round(f1_sum / processed, 4) if processed else 0,
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            {"summary": summary, "details": results}, f, ensure_ascii=False, indent=2
        )


def call_model_medbench(
    client: OpenAI, model: str, question: str, max_retries: int = 3, timeout: int = 30
):
    last_error = None
    for attempt in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": question}],
                temperature=0,
                top_p=1,
                max_tokens=8192,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )
            # timeout=timeout,
            return resp.choices[0].message.content.strip()

        except Exception as e:
            last_error = e
            sleep_time = 1 * (2**attempt)
            time.sleep(sleep_time)
    return f"ERROR: {last_error}"


def process_one_medbench(input_path, output_path, client, model):
    with (
        open(input_path, "r", encoding="utf-8") as fin,
        open(output_path, "w", encoding="utf-8") as fout,
    ):
        for line in fin:
            obj = json.loads(line)

            question = obj.get("question", "")

            answer = call_model_medbench(client, model, question)

            obj["answer"] = answer

            fout.write(json.dumps(obj, ensure_ascii=False) + "\n")


def run_medbench(args):
    client = OpenAI(api_key=args.api_key, base_url=args.base_url)

    os.makedirs(args.output, exist_ok=True)

    if os.path.isdir(args.dataset):
        files = [f for f in os.listdir(args.dataset) if f.endswith(".jsonl")]

        for f in files:
            input_path = os.path.join(args.dataset, f)
            output_path = os.path.join(args.output, f)

            print(f"Processing {f}...")

            process_one_medbench(input_path, output_path, client, args.model)

    else:
        base_name = os.path.basename(args.dataset)
        output_path = os.path.join(args.output, base_name)
        process_one_medbench(args.dataset, output_path, client, args.model)


if __name__ == "__main__":
    args = parse_args()

    if args.mode == "eval":
        run_eval(args)
    elif args.mode == "medbench":
        run_medbench(args)
