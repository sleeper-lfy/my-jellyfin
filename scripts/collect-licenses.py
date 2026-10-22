"""Collect installed distribution license files without embedding private machine paths."""
from importlib.metadata import distributions
from pathlib import Path
import shutil
import sys

output = Path(sys.argv[1])
output.mkdir(parents=True, exist_ok=True)
for distribution in distributions():
    name = distribution.metadata['Name']
    for entry in distribution.files or []:
        if any(word in entry.name.lower() for word in ['license','copying','copyright']) and '.py' not in entry.suffix:
            source = Path(distribution.locate_file(entry))
            if source.is_file():
                target = output / name / entry.name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
