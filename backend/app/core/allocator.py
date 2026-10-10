"""Exact allocation for the six-service software catalog."""

def feasible(mask, services, capacity_w, feeder_limits, feeder_available):
    source = 0
    feeders = {"A": 0, "B": 0}
    for i, svc in enumerate(services):
        if not mask & (1 << i):
            continue
        feeder = svc["feeder"]
        source += svc["watts"]
        feeders[feeder] += svc["watts"]
        if not feeder_available.get(feeder, False) or feeders[feeder] > feeder_limits.get(feeder, 0):
            return False
    return source <= capacity_w


def allocate(services, capacity_w, feeder_limits, feeder_available, requested_mask,
             activity, previous_mask=0):
    """Enumerate every mask; score fixed critical loads before evidence-ranked rooms."""
    best = None
    best_score = None
    for mask in range(1 << len(services)):
        if mask & ~requested_mask or not feasible(mask, services, capacity_w, feeder_limits, feeder_available):
            continue
        served = lambda bit: int(bool(mask & (1 << bit)))
        active = sum(served(bit) for bit, cid in ((3, "CR1"), (4, "CR2"), (5, "CR3"))
                     if activity.get(cid, {}).get("state") == "ACTIVE")
        unknown = sum(served(bit) for bit, cid in ((3, "CR1"), (4, "CR2"), (5, "CR3"))
                      if activity.get(cid, {}).get("state") == "UNKNOWN")
        inactive_w = sum(services[bit]["watts"] for bit, cid in ((3, "CR1"), (4, "CR2"), (5, "CR3"))
                         if activity.get(cid, {}).get("state") == "INACTIVE" and served(bit))
        watts = sum(s["watts"] for bit, s in enumerate(services) if served(bit))
        # L0/L1 remain fixed critical priorities; evidence ranks requested classrooms;
        # the water pump follows ACTIVE and UNKNOWN rooms by explicit policy.
        score = (served(0), served(1), active, unknown, served(2), -inactive_w,
                 -((mask ^ previous_mask).bit_count()), watts, -mask)
        if best_score is None or score > best_score:
            best, best_score = mask, score
    return best or 0


def fixed_priority_mask(services, capacity_w, feeder_limits, feeder_available, requested_mask):
    """Fixed-order reference allocation over the same demand and physical limits."""
    order = (0, 1, 2, 3, 4, 5)
    mask = 0
    for bit in order:
        candidate = mask | (1 << bit)
        if requested_mask & (1 << bit) and feasible(candidate, services, capacity_w, feeder_limits, feeder_available):
            mask = candidate
    return mask


def allocate_appliances(appliances, capacity_w, feeder_limits, feeder_available, activity, active_classroom_ids):
    """Greedy solver for individual appliances."""
    # Build list of active appliances (requested)
    requested = []
    for app in appliances:
        # Determine if requested based on room
        room = app["room"]
        is_requested = True
        
        # Classroom logic
        if room in ("CR1", "CR2", "CR3"):
            is_requested = (room in active_classroom_ids)
            
        if is_requested:
            requested.append(app)
            
    # Sort greedily by Tier priority (T1 first, then T2, T3)
    # Then by watts ascending to maximize count
    requested.sort(key=lambda x: (
        0 if x["tier"] == "T1" else 1 if x["tier"] == "T2" else 2,
        x["watts"]
    ))
    
    served_ids = set()
    source_used = 0
    feeder_used = {"A": 0, "B": 0}
    
    for app in requested:
        feeder = app["feeder"]
        if not feeder_available.get(feeder, False):
            continue
            
        if source_used + app["watts"] <= capacity_w and feeder_used[feeder] + app["watts"] <= feeder_limits.get(feeder, 0):
            served_ids.add(app["id"])
            source_used += app["watts"]
            feeder_used[feeder] += app["watts"]
            
    return served_ids
