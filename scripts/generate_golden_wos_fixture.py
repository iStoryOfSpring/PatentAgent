"""Generate the committed deterministic WoS regression fixture.

This script is the only supported way to replace tests/fixtures/wos_golden.
Review both the fixture and golden expectation changes before committing.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


THEMES = [
    ("solid electrolyte battery", "H01M-010/056", "energy storage"),
    ("carbon capture membrane", "B01D-053/22", "gas separation"),
    ("photovoltaic coating", "H01L-031/021", "solar conversion"),
    ("hydrogen catalyst", "C25B-011/04", "water electrolysis"),
    ("thermal management", "F28D-020/00", "heat transfer"),
    ("robotic sensor", "G01D-005/00", "precision measurement"),
]


def build_records(count: int = 300) -> str:
    records = ["FN Clarivate Analytics Web of Science\nVR 1.0\nER\n"]
    for index in range(count):
        year = 2019 + index // 50
        theme, ipc, use = THEMES[index % len(THEMES)]
        number = f"EP{year}{index:06d}-A1"
        family = f"WO{year}{index:06d}-A1"
        applicants = [f"Applicant {index % 12:02d} Corp"]
        if index % 5 == 0:
            applicants.append(f"Research Institute {index % 7:02d}")
        lines = [
            "PT P",
            f"UT SYNTHETIC:{index:04d}",
            f"PN {number}; {family}",
            f"TI {theme.title()} apparatus generation {index % 10}",
            (
                f"AB NOVELTY - improved {theme} structure generation {index % 10}. "
                f"USE - {use}. ADVANTAGE - stable efficiency and reduced energy loss."
            ),
            "AE " + ";".join(applicants),
            f"AU Inventor {index % 20:02d}",
            f"IP {ipc}",
            f"PI PRIORITY{index:06d} 01 Jan {year - 1}",
            f"PD {number} 02 Jan {year}",
        ]
        if index > 0:
            previous_year = 2019 + (index - 1) // 50
            lines.append(f"CP EP{previous_year}{index - 1:06d}-A1")
        lines.extend(["CR JOURNAL OF SYNTHETIC PATENTS 2018", "ER"])
        records.append("\n".join(lines) + "\n")
    records.append("EF\n")
    return "\n".join(records)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path,
        default=Path("tests/fixtures/wos_golden"),
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "synthetic_wos.txt").write_text(
        build_records(), encoding="utf-8",
    )
    (args.output / "manifest.json").write_text(json.dumps({
        "dataset_id": "synthetic-wos-golden-v1",
        "schema_version": 1,
        "license": "CC0-1.0 synthetic test data",
        "record_count": 300,
        "generator": "scripts/generate_golden_wos_fixture.py",
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
