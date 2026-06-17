"""Core types shared by every rule."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Severity(str, Enum):
    GATE = "GATE"   # a FAIL here blocks the model (NOT READY)
    WARN = "WARN"   # reported, does not block by default
    OFF = "OFF"     # disabled


class Status(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    MANUAL = "MANUAL"   # cannot be verified from TMDL, surfaced as a checklist item


class Section(str, Enum):
    STRUCTURE = "Structure"
    METADATA = "Metadata"
    CALCULATIONS = "Calculations"
    CONFIG = "Configuration"


@dataclass
class Finding:
    rule_id: str
    section: Section
    title: str
    obj: str                 # the model object the finding is about
    status: Status
    severity: Severity
    message: str
    observed: Optional[str] = None
    auto_verified: bool = True

    @property
    def is_blocking(self) -> bool:
        return self.status == Status.FAIL and self.severity == Severity.GATE
