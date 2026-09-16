"""Generate deterministic, explicitly synthetic MCNP-like regression outputs.

These files exercise the parser and GUI workflow. They are not physics results and
must never be used for dose, shielding, criticality, or safety decisions.
"""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "training_data" / "synthetic"


def supported_case(name: str, *, nps: int, minutes: float, total: float, error: float, missed: int, fom: int, bins: list[tuple[float, float, float]]) -> str:
    zero_bins = sum(value == 0 for _, value, _ in bins)
    high_bins = sum(rel > 0.10 for _, _, rel in bins)
    passed = ["yes"] * 10
    if missed >= 1: passed[7] = "no"
    if missed >= 2: passed[9] = "no"
    warning_lines = [
        " warning.  Physics models disabled.",
        " warning.  material        1 has been set to a conductor.",
    ]
    if missed:
        warning_lines.append(f" warning.  the tally in the tally fluctuation chart bin did not pass  {missed} of the 10 statistical checks.")
    if high_bins:
        warning_lines.append(" warning.       1 of the     1 tallies had bins with relative errors greater than recommended.")
    lines = [
        "          Code Name & Version = MCNP6, 1.0",
        "1mcnp     version 6     ld=05/08/13                     01/02/30 03:04:05",
        " *************************************************************************                 probid =  01/02/30 03:04:05",
        f" i={name}.inp o={name}.out",
        *warning_lines[:1],
        "         1-       c cell",
        "         2-       1 1 -1.0 -1",
        "         3-       2 0 1",
        "         4-       c surface",
        "         5-       1 so 10",
        "         6-       c data",
        "         7-       mode p",
        "         8-       imp:p 1 1",
        "         9-       m1 26000 -1",
        "        10-       sdef par=p erg=0.05 pos=0 0 0",
        "        11-       f4:p 2",
        "        12-       e4 0.001 0.010 0.100",
        f"        13-       nps {nps}",
        "1cells                                                                                                  print table 60",
        "        1        1        1  8.00000E-02 7.80000E+00 1.00000E+01 7.80000E+01           0  1.0000E+00",
        "        2        2        0  0.00000E+00 0.00000E+00 4.00000E+03 0.00000E+00           0  1.0000E+00",
        "1cross-section tables                                                                                   print table 100",
        "     XSDIR used: SYNTHETIC/xsdir",
        "                        tables from file synthetic/mcplib",
        "  26000.84p    5794  SYNTHETIC TEST TABLE 01/02/30",
        "1particles and energy limits                                                                            print table 101",
        "    2  p    photon      1.0000E-03    1.0000E+02    1.0000E+05    1.0000E+05    1.0000E+36    1.0000E+36",
        *warning_lines[1:2],
        "1problem summary",
        f"      run terminated when    {nps}  particle histories were done.",
        f" source            {nps}    1.0000E+00    5.0000E-02          escape              1000    1.0000E-03    5.0000E-05",
        f" computer time so far in this run     {minutes:.2f} minutes",
        f" source particles per minute            {nps / max(minutes, 0.01):.4E}",
        "1photon   activity in each cell                                                                         print table 126",
        f"        1        1    {nps}     {nps}     {nps // 2}    5.0000E-01   4.0000E-02   4.0000E-02   1.0000E+00   5.0000E-02",
        f"1tally        4        nps =    {nps}",
        "           tally type 4    track length estimate of particle flux.      units   1/cm**2",
        "           particle(s): photons",
        "           volumes",
        "                   cell:       2",
        "                         4.00000E+03",
        " cell  2",
        "      energy",
    ]
    lines.extend(f"    {energy:.4E}   {value:.5E} {rel:.4f}" for energy, value, rel in bins)
    lines.extend([
        f"      total      {total:.5E} {error:.4f}",
        "           results of 10 statistical checks for the estimated answer for the tally fluctuation chart (tfc) bin of tally        4",
        " desired      random       <0.10      yes      1/sqrt(nps)       <0.10      yes        1/nps           constant    random      >3.00",
        f" observed     random        {error:.2f}      yes          yes            0.01      yes         yes            {'increase' if missed else 'constant'}    random      {'2.50' if missed > 1 else '10.00'}",
        " passed?        " + "          ".join(passed),
    ])
    lines.extend(warning_lines[2:3])
    lines.extend([
        f"1analysis of the results in the tally fluctuation chart bin (tfc) for tally        4 with nps =    {nps}  print table 160",
        f" normed average tally per history  = {total:.5E}          unnormed average tally per history  = {total * 25:.5E}",
        f" estimated tally relative error    = {error:.4f}               estimated variance of the variance  = 0.0010",
        "1unnormed tally density for tally        4          nonzero tally mean(m) = 1.000E+00   nps =    1000000  print table 161",
        " abscissa              ordinate",
        " 1.58-01      2 3.07-03  -2.513 synthetic",
        " 1.00+00     10 1.25-02  -1.903 synthetic",
        "  total      12 1.56-02",
        "1status of the statistical checks used to form confidence intervals for the mean for each tally bin",
        f"        4   missed  {missed} of 10 tfc bin checks: synthetic regression case",
        f"         missed all bin error check:  {len(bins) + 1} tally bins had  {zero_bins} bins with zeros and   {high_bins} bins with relative errors exceeding 0.10",
    ])
    lines.extend(warning_lines[3:4])
    lines.extend([
        "1tally fluctuation charts",
        "                            tally        4",
        "          nps      mean     error   vov  slope    fom",
    ])
    for fraction, scale in [(0.2, 1.8), (0.4, 1.35), (0.6, 1.12), (0.8, 1.04), (1.0, 1.0)]:
        point_nps = max(1, int(nps * fraction))
        point_fom = int(fom * (0.85 + 0.15 * fraction))
        lines.append(f"      {point_nps:8d}   {total * scale:.4E} {error / fraction ** 0.5:.4f} 0.0001 10.0 {point_fom}")
    lines.extend([
        f"         {len(warning_lines)} warning messages so far.",
        f" run terminated when    {nps}  particle histories were done.",
        f" computer time =    {minutes:.2f} minutes",
        " mcnp     version 6     05/08/13                     01/02/30 03:05:06                     probid =  01/02/30 03:04:05",
    ])
    return "\n".join(lines) + "\n"


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    cases = {
        "normal_low_error.out": dict(nps=1_000_000, minutes=0.42, total=2.5e-4, error=0.0200, missed=0, fom=125000, bins=[(0.001, 0.0, 0.0), (0.01, 1.1e-4, 0.04), (0.1, 1.4e-4, 0.03)]),
        "high_error_bins.out": dict(nps=250_000, minutes=0.31, total=8.2e-6, error=0.1200, missed=2, fom=18000, bins=[(0.001, 0.0, 0.0), (0.01, 2.0e-6, 0.30), (0.1, 6.2e-6, 0.14)]),
        "stable_high_precision.out": dict(nps=5_000_000, minutes=2.20, total=7.75e-3, error=0.0050, missed=0, fom=420000, bins=[(0.001, 1.0e-4, 0.02), (0.01, 2.65e-3, 0.01), (0.1, 5.0e-3, 0.006)]),
    }
    manifest: dict[str, object] = {"notice": "SYNTHETIC REGRESSION DATA - NOT PHYSICS RESULTS", "cases": {}}
    for filename, settings in cases.items():
        (ROOT / filename).write_text(supported_case(filename[:-4], **settings), encoding="ascii")
        manifest["cases"][filename] = settings

    (ROOT / "truncated.out").write_text("Code Name & Version = MCNP6, 1.0\n1mcnp     version 6     ld=05/08/13\n         1-       mode p\n1tally        4        nps = 1000\n", encoding="ascii")
    (ROOT / "unsupported_version.out").write_text("Code Name & Version = MCNP6, 6.3.1\n", encoding="ascii")
    (ROOT / "unknown_table.out").write_text("Code Name & Version = MCNP6, 1.0\n1mcnp     version 6     ld=05/08/13\n         1-       mode p\n1synthetic future table\n run terminated when 1000 particle histories were done.\n", encoding="ascii")
    manifest["cases"].update({"truncated.out": {"expected": "partial"}, "unsupported_version.out": {"expected": "unsupported"}, "unknown_table.out": {"expected": "audit-or-strict-failure"}})
    (ROOT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
