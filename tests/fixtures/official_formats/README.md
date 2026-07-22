# Official-format minimized fixtures

These fixtures exercise the documented file schemas without redistributing a
bulk dataset. Bibliographic identifiers are public records for three domains:
solid-state batteries, carbon capture and industrial robotics. Text has been
shortened for deterministic parser tests and is not an expert relevance label.

- `google_patents_sample.jsonl` follows Google Patents Public Data's BigQuery
  export field names (`*_localized`, `ipc`, `cpc`, `citation`). Google and IFI
  CLAIMS publish that dataset under CC BY 4.0.
- `uspto_grant_sample.xml` is a minimized USPTO grant full-text XML document.
- `uspto_file_wrapper_sample.json` is a minimized Patent File Wrapper response.

The acquisition/query recipes in `samples/official/` are the source of truth
for producing a larger local validation dataset.
