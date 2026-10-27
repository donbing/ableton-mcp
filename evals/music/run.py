"""Run the music evals against Claude through the `claude` CLI and grade the replies.

    uv run python -m evals.music.run --condition baseline --samples 3
    uv run python -m evals.music.run --condition reference-docs --samples 3
    uv run python -m evals.music.report evals/music/results/<run> [<other run>]

A condition is a markdown file in conditions/ appended to the system prompt: baseline
is the bare task framing; anything else is the same framing plus the knowledge a
skill would add. Comparing two runs tells us whether that knowledge moves the score.
Each call runs with no tools, no MCP servers and no settings, in an empty directory,
so nothing but the condition reaches the model.
"""
import argparse
import concurrent.futures
import datetime
import json
import os
import subprocess
import tempfile
import time

from . import graders, items

HERE = os.path.dirname(os.path.abspath(__file__))


def system_prompt(condition):
    with open(os.path.join(HERE, "conditions", "baseline.md")) as f:
        text = f.read()
    if condition != "baseline":
        with open(os.path.join(HERE, "conditions", condition + ".md")) as f:
            text += "\n\n" + f.read()
    return text


def ask(prompt, system, model, effort, workdir, retries=2):
    cmd = ["claude", "-p", prompt, "--system-prompt", system, "--tools", "", "--strict-mcp-config",
           "--setting-sources", "", "--no-session-persistence", "--output-format", "json", "--model", model]
    if effort:
        cmd += ["--effort", effort]
    for attempt in range(retries + 1):
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=600, cwd=workdir)
            data = json.loads(out.stdout)
            if data.get("is_error") or not data.get("result"):
                raise RuntimeError(data.get("result") or out.stderr[-500:])
            return {"text": data["result"], "cost_usd": data.get("total_cost_usd", 0.0),
                    "duration_ms": data.get("duration_ms")}
        except (ValueError, RuntimeError, subprocess.TimeoutExpired) as e:
            if attempt == retries:
                return {"text": "", "error": repr(e)[:500], "cost_usd": 0.0}
            time.sleep(5 * (attempt + 1))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--condition", default="baseline", help="a conditions/<name>.md file (default baseline)")
    p.add_argument("--model", default="claude-opus-5-5")
    p.add_argument("--effort", default=None, help="low|medium|high|xhigh|max (default: the CLI's)")
    p.add_argument("--samples", type=int, default=3, help="replies per item, to measure consistency")
    p.add_argument("--category", action="append", help="only these categories (repeatable)")
    p.add_argument("--limit", type=int, default=None, help="only the first N items (smoke test)")
    p.add_argument("--jobs", type=int, default=8)
    p.add_argument("--out", default=None)
    args = p.parse_args(argv)

    bank = [i for i in items.all_items() if not args.category or i["category"] in args.category][:args.limit]
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = args.out or os.path.join(HERE, "results", "%s_%s_%s" % (stamp, args.condition, args.model))
    os.makedirs(out, exist_ok=True)
    system = system_prompt(args.condition)
    meta = {"condition": args.condition, "model": args.model, "effort": args.effort, "samples": args.samples,
            "items": len(bank), "started": stamp, "system_prompt": system}
    with open(os.path.join(out, "meta.json"), "w") as f:
        json.dump(meta, f, indent=2)

    jobs = [(i, s) for i in bank for s in range(args.samples)]
    print("%d items x %d samples = %d calls -> %s" % (len(bank), args.samples, len(jobs), out))
    workdir = tempfile.mkdtemp(prefix="music-eval-")
    total_cost, done, passed = 0.0, 0, 0
    with open(os.path.join(out, "results.jsonl"), "w") as f, \
            concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
        futures = {pool.submit(ask, i["prompt"], system, args.model, args.effort, workdir): (i, s) for i, s in jobs}
        for fut in concurrent.futures.as_completed(futures):
            item, sample = futures[fut]
            reply = fut.result()
            graded = graders.grade(item, reply["text"]) if reply["text"] else \
                {"passed": False, "checks": {"call_failed": False}, "detail": reply.get("error")}
            row = {"id": item["id"], "category": item["category"], "sample": sample, **graded,
                   "reply": reply["text"], "cost_usd": reply["cost_usd"], "error": reply.get("error")}
            f.write(json.dumps(row) + "\n")
            f.flush()
            total_cost += reply["cost_usd"] or 0.0
            done += 1
            passed += graded["passed"]
            if done % 10 == 0 or done == len(jobs):
                print("  %d/%d  pass %.0f%%  $%.2f" % (done, len(jobs), 100.0 * passed / done, total_cost))
    print("wrote", out)
    return out


if __name__ == "__main__":
    main()
