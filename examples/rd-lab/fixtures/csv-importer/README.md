# CSV Importer Mission

This owned synthetic mission repairs a CSV-to-JSON importer. The baseline and
candidate programs are local fixtures. They are supplied inputs for the lab and
must not be described as model-discovered or autonomous repairs.

Expected output is a list of normalized row objects for valid CSV input. Amount
values keep their source precision as strings, with decimal comma values
normalized to a dot. Invalid inputs use this explicit error contract:

```json
{"error": "empty_csv", "rows": []}
```

or:

```json
{"error": "invalid_csv", "rows": []}
```
