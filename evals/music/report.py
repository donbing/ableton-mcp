"""Summarise one run, or compare runs, as markdown.

    uv run python -m evals.music.report <run dir> [<run dir> ...] [--out report.md]

Pass rates come with 95% Wilson intervals. With two or more runs, each category also
shows how many items got better or worse against the first run, with a two-sided
sign test p-value over those items: a gap smaller than the noise is reported as such.
"""
import argparse
import collections
import json
import math
import os


def load(run):
    with open(os.path.join(run, "meta.json")) as f:
        meta = json.load(f)
    with open(os.path.join(run, "results.jsonl")) as f:
        rows = [json.loads(line) for line in f]
    return meta, rows


def wilson(k, n, z=1.96):
    if n == 0:
        return 0.0, 0.0
    p = k / float(n)
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, centre - half), min(1.0, centre + half)


def sign_test(better, worse):
    n = better + worse
    if n == 0:
        return 1.0
    k = min(better, worse)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2.0 ** n
    return min(1.0, 2 * tail)


def pct(x):
    return "%.0f%%" % (100 * x)


def item_rates(rows):
    by = collections.defaultdict(list)
    for r in rows:
        by[r["id"]].append(r["passed"])
    return {k: sum(v) / float(len(v)) for k, v in by.items()}


def summary(meta, rows):
    out = ["## %s · %s%s" % (meta["condition"], meta["model"], " · effort " + meta["effort"] if meta.get("effort") else ""),
           "", "%d items × %d samples, $%.2f" % (meta["items"], meta["samples"], sum(r["cost_usd"] or 0 for r in rows)), "",
           "| category | pass | 95% CI | items always right | always wrong | flaky | unreadable |",
           "|---|---|---|---|---|---|---|"]
    cats = collections.OrderedDict()
    for r in rows:
        cats.setdefault(r["category"], []).append(r)
    total = []
    for cat, rs in list(cats.items()) + [("**all**", rows)]:
        k, n = sum(r["passed"] for r in rs), len(rs)
        lo, hi = wilson(k, n)
        rates = item_rates(rs)
        unreadable = sum(1 for r in rs if r["checks"].get("readable") is False or r.get("error"))
        out.append("| %s | %s | %s–%s | %d | %d | %d | %d |" % (
            cat, pct(k / float(n)), pct(lo), pct(hi), sum(v == 1 for v in rates.values()),
            sum(v == 0 for v in rates.values()), sum(0 < v < 1 for v in rates.values()), unreadable))
        total.append(cat)
    spelled = [r["spelled"] for r in rows if "spelled" in r and r["passed"]]
    if spelled:
        out += ["", "Of the right note-name answers, %s were also spelled correctly (e.g. E# not F in F# harmonic minor)."
                % pct(sum(spelled) / float(len(spelled)))]
    fails = collections.Counter()
    for r in rows:
        for check, ok in r["checks"].items():
            if not ok:
                fails[(r["category"], check)] += 1
    if fails:
        out += ["", "Most failed checks:", ""]
        out += ["- %s · `%s` × %d" % (c, check, n) for (c, check), n in fails.most_common(12)]
    wrong = sorted({r["id"] for r in rows if not r["passed"]})
    if wrong:
        out += ["", "<details><summary>Items failed at least once (%d)</summary>" % len(wrong), ""]
        for id in wrong:
            r = next(x for x in rows if x["id"] == id and not x["passed"])
            out.append("- `%s`: %s" % (id, (r.get("detail") or "")[:200].replace("|", "/")))
        out += ["", "</details>"]
    return "\n".join(out)


def compare(runs):
    (base_meta, base_rows), others = runs[0], runs[1:]
    out = ["## Against %s" % base_meta["condition"], "",
           "| category | " + " | ".join("%s (%s)" % (m["condition"], m["model"]) for m, _ in runs) +
           " | better / worse items | sign test p |", "|---|" + "---|" * (len(runs) + 2)]
    base = item_rates(base_rows)
    cats = list(collections.OrderedDict((r["category"], 1) for r in base_rows))
    for cat in cats + ["**all**"]:
        cells = []
        for _, rows in runs:
            rs = [r for r in rows if cat == "**all**" or r["category"] == cat]
            cells.append(pct(sum(r["passed"] for r in rs) / float(len(rs))) if rs else "–")
        diffs = []
        for _, rows in others:
            rates = item_rates([r for r in rows if cat == "**all**" or r["category"] == cat])
            better = sum(1 for k, v in rates.items() if k in base and v > base[k])
            worse = sum(1 for k, v in rates.items() if k in base and v < base[k])
            diffs.append(("%d / %d" % (better, worse), "%.2f" % sign_test(better, worse)))
        out.append("| %s | %s | %s | %s |" % (cat, " | ".join(cells), "; ".join(d[0] for d in diffs),
                                              "; ".join(d[1] for d in diffs)))
    return "\n".join(out)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("runs", nargs="+")
    p.add_argument("--out")
    args = p.parse_args(argv)
    runs = [load(r) for r in args.runs]
    parts = ["# Music eval report", ""]
    if len(runs) > 1:
        parts += [compare(runs), ""]
    parts += [summary(m, r) + "\n" for m, r in runs]
    text = "\n".join(parts)
    if args.out:
        with open(args.out, "w") as f:
            f.write(text)
    print(text)


if __name__ == "__main__":
    main()
