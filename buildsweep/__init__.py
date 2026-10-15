"""buildsweep: find and remove regenerable build and dependency folders.

Python API:

    from buildsweep import scan
    result = scan(["~/code"])
    for a in result.artifacts:
        print(a.path, a.size, a.rule.ecosystem)
"""

from .rules import RULES, Rule
from .scanner import Artifact, ScanResult, scan

__version__ = "1.0.0"
__all__ = ["Artifact", "RULES", "Rule", "ScanResult", "scan", "__version__"]
