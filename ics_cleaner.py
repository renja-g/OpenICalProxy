import re
from icalendar import Calendar, Event
from typing import Callable


def clean_description(description: str) -> str:
    """Remove HTML tags and replace specific characters in the description."""
    description = re.sub(r"<[^>]*>", "", description)
    description = description.replace("&nbsp;", "")
    description = description.replace("l", "I")
    return description


def patch_clean_summary(component: Event) -> None:
    """Clean up the SUMMARY (get rid of the prefix)."""
    summary = component.get("summary", "")
    pattern = r"^(?:ETI\.\d+\.\d+\.\d+\.V\.\d+\s+)?(.+)$"
    match = re.match(pattern, summary)
    if match:
        component["summary"] = match.group(1)


def patch_informatik_tutorium(component: Event) -> None:
    """Patch for 'Einführung in die Informatik' tutorial."""
    summary = component.get("summary", "")
    description = component.get("description", "")

    if "Einführung in die Informatik" in summary and "Freies Tutorium" in description:
        component["description"] = clean_description(description)
        component["summary"] = f"{summary} Tutorium"


# List of patch functions to apply
PATCHES: list[Callable[[Event], None]] = [
    patch_clean_summary,
    patch_informatik_tutorium,
]


def modify_ics(ics_content: bytes) -> bytes:
    """Modify the entire iCal content."""
    calendar = Calendar.from_ical(ics_content)

    for component in calendar.walk():
        if isinstance(component, Event):
            for patch in PATCHES:
                patch(component)

    return calendar.to_ical()
