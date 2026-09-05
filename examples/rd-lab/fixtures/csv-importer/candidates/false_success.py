import csv
import io
import json
import sys


def main():
    payload = json.load(sys.stdin)
    text = payload.get("csv", "")
    if not text.strip():
        print(json.dumps([]))
        return
    reader = csv.DictReader(io.StringIO(text), delimiter=",")
    rows = []
    for row in reader:
        rows.append({key.strip(): value for key, value in row.items() if key})
    print(json.dumps(rows))


if __name__ == "__main__":
    main()
