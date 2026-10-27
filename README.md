# Curriculum Comparison (site)

Interactive views comparing the University of Cincinnati CS BS (normalized to four
years) with fifteen other CS programs. Published with GitHub Pages:
https://jauri.github.io/curriculum-comparison-site/web/

This repo is generated: everything here is copied from the (private) project repo by
its `publish_site.sh` (this README comes from its `site_README.md`). Don't edit it here.

## What's here

- `web/`: the pages (plain HTML + D3 / Observable Plot, no build step)
- `data/processed/<school>/`: the generated tables the pages read (CSV and JSON)
- `src/`: the Python scripts that collect the schools' catalog pages and build those
  tables (`collect_<school>.py`, `parse_<school>.py`, `parse_<school>_descriptions.py`
  per school; shared steps like `normalize.py`, `describe.py`, `build_outputs.py`,
  `validate.py`, `build_combined.py`, `build_concepts.py` take `--school <id>` or run
  on all schools)
- `data/reference/`: hand-reviewed inputs: the school registry, canonical course list,
  subject areas, concept vocabulary, and per-school course matches, generic
  descriptions, and concept tags
- `specs/`: the rules the scripts follow (sources, co-op normalization, output schema,
  concepts, and each view), with `specs/plan.md` as the step-by-step plan

The raw downloads (`data/raw/`) are not included: they are the universities' own
catalog pages. The `collect_<school>.py` scripts download them again (the catalogs may
have changed since). To rerun for one school:

```sh
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python src/collect_uc.py && python src/collect_uc_courses.py
python src/parse_uc.py && python src/parse_uc_descriptions.py
python src/normalize.py --school uc && python src/describe.py --school uc
python src/build_outputs.py --school uc && python src/validate.py --school uc
```

Course descriptions are the schools' own catalog text, except those marked "generic",
which were written for the project.
