URGENT_TYPES = {"sos", "possible_fall"}

def active_emergencies(events):
    """Backend must supply authoritative current event states, not historical events.
    A CO event is urgent only when evidence.level == 'urgent'.
    Workflow acknowledgement does NOT clear a locally active emergency.
    Unknown local state is treated conservatively when event remains unresolved.
    """
    urgent = []
    for event in events:
        typ = event.get("event_type")
        evidence = event.get("evidence") or {}
        if typ not in URGENT_TYPES and not (typ == "co" and evidence.get("level") == "urgent"):
            continue
        local = event.get("local_state", "unknown")
        if local in ("cleared", "physically_acknowledged"):
            continue
        if local == "active" or (local == "unknown" and event.get("workflow_state") != "resolved"):
            urgent.append({"rule": typ, "source_event_key": event.get("source_event_key"), "priority": 1, "overrides_model": True})
    return urgent

def resolve(predicted_level, events):
    urgent = active_emergencies(events)
    return ("critical" if urgent else predicted_level), urgent
