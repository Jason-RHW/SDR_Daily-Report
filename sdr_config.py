"""
Shared config: SDR roster, Aircall name normalization, and tag definitions.
Single source of truth so fetch/compute/send never disagree on names.
"""

SDR_NAMES = [
    "Lhoreto Bamiano",
    "Maria Gladys Palmares",
    "Basilio Asuncion",
    "Stephanie Ong",
    "Harhel Grace Manansala",
]

SDR_SHORT = {
    "Lhoreto Bamiano":        "Lhoreto",
    "Maria Gladys Palmares":  "Maria",
    "Basilio Asuncion":       "Basilio",
    "Stephanie Ong":          "Stephanie",
    "Harhel Grace Manansala": "Harhel",
}

# Maps every name variant Aircall might return -> canonical SDR name.
# Add new variants here the moment you spot one in "Unassigned" totals.
AIRCALL_USER_MAP = {
    "Lhoreto Bamiano":        "Lhoreto Bamiano",
    "Maria Gladys Palmares":  "Maria Gladys Palmares",
    "Basilio Asuncion":       "Basilio Asuncion",
    "Stephanie Ong":          "Stephanie Ong",
    "Harhel Grace Manansala": "Harhel Grace Manansala",
    "Grace Manansala":        "Harhel Grace Manansala",
    "Harhel Manansala":       "Harhel Grace Manansala",
}

# A call counts as "connected" if it carries any of these tags -
# tag-based, not answered_at (a call can be answered but still be a
# wrong number, IVR bounce, etc.)
CONNECTED_TAGS = {
    "Spoke with Contact",
    "Interested New Lead",
    "Not Interested",
    "Reception/Gatekeeper",
    "Customer hang up",
    "Callback/Follow up",
    "Send Sample",
    "DNC",
}

SAMPLE_TAG = "Send Sample"

# SDRs who've left the company but whose Aircall seat/extension is still
# misattributing calls to their name (stale user profile, reassigned
# extension not renamed, etc.) - excluded from all reports regardless of
# what Aircall's API says. This is a safety net, not a fix: the underlying
# Aircall seat issue should still get sorted out, since it likely means
# whoever's actually making these calls isn't getting credit for them.
TERMINATED_SDRS = {
    "Lhoreto Bamiano",
    "Stephanie Ong",
}
