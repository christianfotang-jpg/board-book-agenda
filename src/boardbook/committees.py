"""Standing committees of the University of Alberta General Faculties Council (GFC).

Used to populate the committee picker in the web UI and CLI so the user
doesn't have to type (or rely on Claude extracting) the exact committee name.
"""

GFC_COMMITTEES: tuple[str, ...] = (
    "GFC Academic Planning Committee",
    "GFC Committee on the Learning Environment and Student Affairs",
    "GFC Executive Committee",
    "GFC Executive Subcommittee on Governance and Procedural Oversight",
    "GFC Nominating Committee",
    "GFC Programs Committee",
    "GFC University Teaching Awards Committee",
    "GFC Committee for the Verification of First Nations, Métis and Inuit Documentation",
    "Council on Student Affairs",
)
