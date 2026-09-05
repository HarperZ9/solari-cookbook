import csv
import io
import json
import sys


def main():
    payload = json.load(sys.stdin)
    text = payload.get("csv", "")
    reader = csv.DictReader(io.StringIO(text), delimiter=",")
    rows = []
    for row in reader:
        rows.append({key.strip(): value.strip() for key, value in row.items()})
    print(json.dumps(rows))


if __name__ == "__main__":
    main()
