"""Demo member roster.

Members are a small fixed roster for the demo. There is deliberately no
persistent per-person identity system (CLAUDE.md "Out of Scope") -- these records
carry nothing but a name and a premium flag. The basic member exists so the
"only premium members may reserve" rejection path is demoable.
"""
from __future__ import annotations

from models import Member

DEFAULT_MEMBERS: tuple[Member, ...] = (
    Member("m-ada", "Ada Reyes", is_premium=True),
    Member("m-bo", "Bo Tanaka", is_premium=True),
    Member("m-dana", "Dana Okoro", is_premium=True),
    Member("m-cy", "Cy Morgan", is_premium=False),
)


def member_by_id(member_id: str) -> "Member | None":
    for m in DEFAULT_MEMBERS:
        if m.id == member_id:
            return m
    return None
