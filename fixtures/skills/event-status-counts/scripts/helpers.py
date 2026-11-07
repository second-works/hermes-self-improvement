"""PUBLIC baseline defect: duplicates are incorrectly collapsed."""
def accumulate(events):
    counts, seen = {}, set()
    for event in events:
        identity = (event['category'], event['status'])
        if identity in seen:
            continue
        seen.add(identity)
        counts.setdefault(event['category'], {'ok': 0, 'failed': 0})[event['status']] += 1
    return counts
