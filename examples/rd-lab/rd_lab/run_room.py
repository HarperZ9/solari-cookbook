"""Offline view of observed experiments. No model calls or report execution."""
import argparse
from html import escape
import json
from pathlib import Path


# Restrained product adaptation of the committed portfolio's ink and copper.
# A reviewer compares evidence on a small screen in daylight; white surfaces
# and dark text keep the source diff readable without decorative effects.
STYLE = """
:root{color-scheme:light;--ink:#17181c;--muted:#565b66;--accent:#714226;
--surface:#f5f6f8;--line:#c7cbd2;--pass:#176344;--fail:#9b3030}
*{box-sizing:border-box}html{scroll-behavior:smooth}
body{margin:0;color:var(--ink);background:#fff;font:1rem/1.55 system-ui,sans-serif}
a{color:var(--accent);text-underline-offset:3px}a:hover{text-decoration-thickness:2px}
:focus-visible{outline:3px solid var(--accent);outline-offset:4px}
.skip{position:absolute;top:-5rem;left:1rem;background:#fff;padding:.75rem}
.skip:focus{top:.5rem}header{border-bottom:1px solid var(--line)}
.masthead,main,footer{max-width:1120px;margin:auto;padding:1rem 1.5rem}
.masthead{display:flex;align-items:center;justify-content:space-between;gap:1rem;flex-wrap:wrap}
.brand{font-weight:750}.brand span{font-weight:400;color:var(--muted)}
nav{display:flex;gap:1rem;flex-wrap:wrap;font-size:.9rem}
main{padding-top:2rem}h1,h2,h3{line-height:1.2;text-wrap:balance}
h1{font-size:1.75rem;margin:.5rem 0 1rem;letter-spacing:-.02em}
h2{font-size:1.2rem;margin:0 0 1rem}h3{font-size:1rem;margin:.25rem 0}
p{max-width:72ch;margin:.65rem 0}small,.muted{color:var(--muted)}
section{margin:2rem 0;scroll-margin-top:1rem}code,pre{font-family:ui-monospace,monospace}
code{overflow-wrap:anywhere}pre{font-size:.875rem;white-space:pre-wrap;overflow-wrap:anywhere;margin:0}
.mode{display:inline-block;border:1px solid var(--line);padding:.2rem .55rem;font-size:.85rem;border-radius:4px}
.decision{display:flex;gap:2rem;justify-content:space-between;align-items:start;flex-wrap:wrap}
.decision p{margin-top:0}.decision strong{font-size:1.1rem}
.summary{width:100%;border-collapse:collapse;font-size:.95rem}
.summary th,.summary td{padding:.8rem .5rem;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}
.summary th{font-weight:600}.summary caption{text-align:left;color:var(--muted);padding:0 0 .7rem}
.summary td:first-child{font-weight:650}.summary .chosen{background:var(--surface)}
.ratio{font-variant-numeric:tabular-nums;white-space:nowrap}
meter{width:5rem;height:.65rem;display:block;margin-top:.3rem;accent-color:var(--pass)}
.table-scroll{overflow:auto}.pass{color:var(--pass)}.fail{color:var(--fail)}
details{border-bottom:1px solid var(--line)}summary{cursor:pointer;padding:.85rem 0}
summary:hover{color:var(--accent)}summary .status{float:right;margin-left:1rem}
.case{padding:0 .75rem 1rem}.case-meta{font-size:.85rem;color:var(--muted)}
.pair{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:1rem}
.pair pre,.diff{background:var(--surface);padding:1rem;border-radius:4px}
.hash{font-size:.8rem;color:var(--muted);margin:.5rem 0 1rem}
.experiment{margin:1.5rem 0 2rem}.diff span{display:block;min-height:1.35em}
.diff .add{color:var(--pass)}.diff .remove{color:var(--fail)}
ul{padding-left:1.25rem}li{margin:.5rem 0;max-width:75ch}
footer{font-size:.85rem;color:var(--muted);border-top:1px solid var(--line)}
@media(max-width:600px){.masthead,main,footer{padding-left:1rem;padding-right:1rem}
main{padding-top:1rem}.pair{grid-template-columns:minmax(0,1fr)}
.summary th,.summary td{padding:.6rem .25rem}.summary{font-size:.85rem}
meter{width:3rem}summary .status{float:none;display:block;margin:0}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
@media(forced-colors:active){.pass,.fail,.diff .add,.diff .remove{color:CanvasText}
.chosen,.pair pre,.diff{border:1px solid CanvasText}meter{forced-color-adjust:auto}}
@media print{nav,.skip{display:none}main{padding:0}.table-scroll{overflow:visible}
details::details-content{display:block;content-visibility:visible}details>*{display:block}summary{list-style:none}
.pair{grid-template-columns:1fr}pre{white-space:pre-wrap}section{break-inside:auto}}
"""


def text(value):
    return escape(str(value), quote=True)


def json_text(value):
    return text(json.dumps(value, indent=2, ensure_ascii=False))


def _selection(report):
    chosen = report.get("selected_candidate")
    if chosen is None:
        return None
    matches = [e for e in report["experiments"]
               if e["candidate_id"] == chosen["id"]]
    if len(matches) != 1 or chosen["id"] == "baseline":
        raise ValueError("Selected repair must identify one non-baseline experiment")
    match = matches[0]
    if (not match["cases"] or not match["passed"]
            or any(c["status"] != "passed" for c in match["cases"])
            or chosen["source_sha256"] != match["source_sha256"]):
        raise ValueError("Selected repair conflicts with experiment evidence")
    return chosen


def _comparison(experiments, chosen):
    rows = []
    for index, experiment in enumerate(experiments):
        cases = experiment["cases"]
        passed = sum(c["status"] == "passed" for c in cases)
        count = len(cases)
        selected = chosen and chosen["id"] == experiment["candidate_id"]
        verdict = "Selected" if selected else ("Baseline" if experiment["candidate_id"] == "baseline" else "Not selected")
        meter = (f'<meter min="0" max="{count}" value="{passed}" '
                 f'aria-label="{passed} of {count} cases passed"></meter>') if count else ""
        rows.append(f'<tr class="{"chosen" if selected else ""}"><td>'
                    f'<a href="#experiment-{index}">{text(experiment["candidate_id"])}</a></td>'
                    f'<td class="ratio">{passed} / {count}{meter}</td>'
                    f'<td>{text(verdict)}</td></tr>')
    if not rows:
        return "<p>No experiments recorded. No result can be inferred.</p>"
    return ('<div class="table-scroll" role="region" aria-label="Candidate comparison" tabindex="0">'
            '<table class="summary"><caption>Literal case matches, not general correctness.</caption>'
            '<thead><tr><th scope="col">Program</th><th scope="col">Cases passed</th>'
            '<th scope="col">Decision</th></tr></thead><tbody>' + "".join(rows) + '</tbody></table></div>')


def _case(case):
    status = case["status"].replace("_", " ").capitalize()
    css = "pass" if case["status"] == "passed" else "fail"
    return (f'<details><summary>{text(case["id"])} '
            f'<span class="status {css}">{text(status)}</span></summary><div class="case">'
            f'<p class="case-meta">Exit code: {text(case["exit_code"])} · '
            f'Elapsed: {text(case["duration_ms"])} ms</p><div class="pair">'
            f'<div><h3>Expected</h3><pre>{json_text(case["expected"])}</pre></div>'
            f'<div><h3>Observed</h3><pre>{json_text(case["actual"])}</pre></div>'
            '</div></div></details>')


def _experiments(experiments):
    sections = []
    for index, experiment in enumerate(experiments):
        sections.append(f'<div class="experiment" id="experiment-{index}">'
                        f'<h3>{text(experiment["candidate_id"])}</h3>'
                        f'<p class="hash">Source SHA256 <code>{text(experiment["source_sha256"])}</code></p>'
                        + "".join(_case(c) for c in experiment["cases"]) + '</div>')
    return "".join(sections)


def _diff(chosen):
    if not chosen:
        return '<p>No selected repair, so no selected source change is shown.</p>'
    lines = []
    for line in chosen.get("unified_diff", "").splitlines():
        css = "add" if line.startswith("+") else ("remove" if line.startswith("-") else "")
        lines.append(f'<span class="{css}">{text(line)}</span>')
    return '<pre class="diff" aria-label="Selected repair source diff">' + "".join(lines) + '</pre>'


def render_report(report):
    """Render an existing report; never execute or fetch any report content."""
    if report.get("schema") != "rd-lab.run/v1":
        raise ValueError("Expected rd-lab.run/v1 report")
    chosen = _selection(report)
    title = text(report["mission"])
    mode = report["execution_mode"]
    mode_label = "Local trusted execution" if mode == "local_trusted_subprocess" else text(mode)
    decision = f'Selected repair: {text(chosen["id"])}' if chosen else "No repair selected"
    boundary = ("Local subprocesses are not a security sandbox. "
                "This report is not evidence of a Solari run.") if mode == "local_trusted_subprocess" else "Execution mode is reported by the runner; this view does not attest it."
    limitations = "".join(f'<li>{text(item)}</li>' for item in report.get("limitations", []))
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="referrer" content="no-referrer"><title>{title} | R&amp;D Lab</title><style>{STYLE}</style></head>
<body><a class="skip" href="#main">Skip to results</a><header><div class="masthead">
<div class="brand">Flywheel <span>/ R&amp;D Lab</span></div>
<nav aria-label="Report"><a href="#comparison">Compare</a><a href="#evidence">Inspect</a>
<a href="#change">Source change</a><a href="#scope">Limits</a></nav></div></header>
<main id="main" tabindex="-1"><span class="mode">{mode_label}</span><h1>{title}</h1>
<div class="decision"><div><strong>{decision}</strong>
<p class="muted">Compare what each program returned with what the mission required.</p></div>
<a href="#change">Inspect the source change ↓</a></div>
<section id="comparison" aria-labelledby="comparison-heading"><h2 id="comparison-heading">Which repair held up?</h2>
{_comparison(report["experiments"], chosen)}</section>
<section id="evidence" aria-labelledby="evidence-heading"><h2 id="evidence-heading">Inspect the evidence</h2>
<p class="muted">Open a case to compare expected and observed output. A clean exit alone does not pass a case.</p>
{_experiments(report["experiments"])}</section>
<section id="change" aria-labelledby="change-heading"><h2 id="change-heading">Selected source change</h2>
{_diff(chosen)}</section>
<section id="scope" aria-labelledby="scope-heading"><h2 id="scope-heading">What this run establishes</h2>
<p>{text(boundary)}</p><p>Selection covers only the recorded cases. It is not a claim of general correctness.</p>
<ul>{limitations}</ul><p class="muted">Started: {text(report["started_at"])}<br>
Finished: {text(report["finished_at"])}</p></section></main>
<footer>Offline report view · No scripts, remote fonts, trackers or network requests. Rendered from rd-lab.run/v1.</footer>
</body></html>'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    html = render_report(report)
    # Refuse to overwrite source reports or previous views silently.
    with args.out.open("x", encoding="utf-8") as output:
        output.write(html)
    print(args.out)


if __name__ == "__main__":
    main()
