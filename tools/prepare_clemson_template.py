"""Normalize signed chart axis identifiers in a separate template copy."""
import argparse
import json
import re
from pathlib import Path
from zipfile import ZipFile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    changed = {}
    with ZipFile(args.source) as source, ZipFile(args.output, "w") as output:
        for entry in source.infolist():
            content = source.read(entry.filename)
            if re.fullmatch(r"ppt/charts/chart\d+\.xml", entry.filename):
                content, count = re.subn(
                    rb'(<c:(?:axId|crossAx)\b[^>]*\bval=")(-\d+)(")',
                    lambda match: match[1] + str(int(match[2]) % (2**32)).encode() + match[3],
                    content,
                )
                if count:
                    changed[entry.filename] = count
            output.writestr(entry, content)
    print(json.dumps({"output": str(args.output), "normalized_axis_ids": changed}))


if __name__ == "__main__":
    main()
