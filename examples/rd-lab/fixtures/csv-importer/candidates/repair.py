import csv
import io
import json
import re
import sys


ERROR_EMPTY = {"error": "empty_csv", "rows": []}
ERROR_INVALID = {"error": "invalid_csv", "rows": []}
DECIMAL_COMMA = re.compile(r"^-?\d+,\d+$")


def main():
    payload = json.load(sys.stdin)
    text = payload.get("csv", "")
    if not isinstance(text, str) or not text.strip():
        print(json.dumps(ERROR_EMPTY))
        return
    rows = parse_rows(text)
    print(json.dumps(rows if rows is not None else ERROR_INVALID))


def parse_rows(text):
    delimiter = choose_delimiter(text)
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    if not reader.fieldnames or any(not field.strip() for field in reader.fieldnames):
        return None
    rows = []
    for row in reader:
        if None in row or any(value is None for value in row.values()):
            return None
        rows.append({key.strip(): normalize(value) for key, value in row.items()})
    return rows or None


def choose_delimiter(text):
    header = next((line for line in text.splitlines() if line.strip()), "")
    return ";" if header.count(";") > header.count(",") else ","


def normalize(value):
    cleaned = value.strip()
    if DECIMAL_COMMA.fullmatch(cleaned):
        return cleaned.replace(",", ".")
    return cleaned


if __name__ == "__main__":
    main()
