"""Automated Board Book Generator.

Modules:
    parser     - freeform agenda text -> structured JSON (Claude structured outputs) + time math
    template   - Jinja2/HTML agenda cover page rendered to PDF
    compiler   - merges attachments after the cover page and stamps footer page numbers
    pipeline   - orchestrates the full run
    cli        - command line entry point
    api        - FastAPI service entry point
"""

__version__ = "0.1.0"
