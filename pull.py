"""Step 5: download your Garmin history into data/ as JSON (read-only).

    python3 pull.py         last 12 months (or whatever is new since last time)
    python3 pull.py --all   your full history (takes a few more minutes)

Re-running only fetches what is new.
"""
import datetime as dt
import json
import os
import sys

import garmin

DATA = garmin.DATA
TODAY = dt.date.today()


# ---------- small helpers ----------

def load(name, default):
    path = os.path.join(DATA, name)
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except (ValueError, OSError):
            pass
    return default


def save(name, obj):
    os.makedirs(DATA, exist_ok=True)
    path = os.path.join(DATA, name)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, separators=(",", ":"))
    os.replace(tmp, path)


def d(s):
    return dt.date.fromisoformat(s[:10])


def dig(obj, path):
    for key in path.split("."):
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


def find_list(resp, *keys):
    """Return the list of items from a response, whatever its wrapper."""
    if isinstance(resp, list):
        return resp
    if isinstance(resp, dict):
        for k in keys:
            if isinstance(resp.get(k), list):
                return resp[k]
        for v in resp.values():
            if isinstance(v, list):
                return v
    return []


def item_date(item, *keys):
    for k in keys + ("calendarDate", "summaryDate", "date"):
        v = item.get(k) if isinstance(item, dict) else None
        if isinstance(v, str) and len(v) >= 10:
            return v[:10]
    return None


def chunks(start, end, days):
    """Yield (from, to) date pairs covering start..end, newest first."""
    hi = end
    while hi >= start:
        lo = max(start, hi - dt.timedelta(days=days - 1))
        yield lo, hi
        hi = lo - dt.timedelta(days=1)


def fetch_range(fetch, lo, hi):
    """Call fetch(lo, hi); if Garmin says it's too big, split it in half."""
    try:
        return fetch(lo, hi)
    except garmin.TooBig:
        if lo >= hi:
            print(f"    skipped {lo} (Garmin could not return it)")
            return []
        mid = lo + (hi - lo) // 2
        return (fetch_range(fetch, lo, mid) +
                fetch_range(fetch, mid + dt.timedelta(days=1), hi))


# ---------- activities ----------

def pull_activities(target_from, meta):
    acts = {str(a["activityId"]): a for a in load("activities.json", [])}
    have_back_to = meta.get("activities_from")
    complete = (have_back_to == "all" or
                (have_back_to and target_from and d(have_back_to) <= target_from))
    # If our saved history is already deep enough, only re-check the last
    # couple of weeks (catches new rides and edits); otherwise go all the way.
    newest = max((d(a["startTimeLocal"]) for a in acts.values()), default=None)
    stop_at = (newest - dt.timedelta(days=14)) if (complete and newest) else target_from

    print("Activities:")
    start, limit, new = 0, 20, 0
    while True:
        try:
            page = garmin.get("/activitylist-service/activities/search/activities",
                              {"start": start, "limit": limit}) or []
        except garmin.TooBig:
            if limit > 1:
                limit = max(1, limit // 2)   # answer too big: ask for fewer
                continue
            print(f"    skipped one activity Garmin could not return (#{start})")
            start += 1
            continue
        for a in page:
            key = str(a.get("activityId"))
            if key not in acts:
                new += 1
            acts[key] = a
        start += len(page)
        oldest = page[-1].get("startTimeLocal", "")[:10] if page else ""
        print(f"    {len(acts)} activities saved, back to {oldest or '-'}")
        if len(page) < limit:            # reached your very first activity
            meta["activities_from"] = "all"
            break
        if stop_at and oldest and d(oldest) < stop_at:
            break
        limit = 20
    if meta.get("activities_from") != "all":
        prev = meta.get("activities_from")
        meta["activities_from"] = (min(prev, target_from.isoformat())
                                   if prev else target_from.isoformat())
    ordered = sorted(acts.values(), key=lambda a: a.get("startTimeLocal", ""),
                     reverse=True)
    save("activities.json", ordered)
    print(f"    done: {new} new")
    return ordered


# ---------- day-by-day data ----------

def pull_days(name, label, start, days, fetch, has_data, meta, date_keys=()):
    store = load(name, {})
    checked = meta.setdefault("checked", {}).get(name)  # [from, to] already asked
    if checked:
        c_lo, c_hi = d(checked[0]), d(checked[1])
        ranges = [(max(start, c_hi - dt.timedelta(days=3)), TODAY)]
        if start < c_lo:
            ranges.append((start, c_lo - dt.timedelta(days=1)))
    else:
        ranges = [(start, TODAY)]
    print(f"{label}:")
    added = 0
    lo_done = d(checked[0]) if checked else TODAY
    for r_lo, r_hi in ranges:
        if r_lo > r_hi:
            continue
        for lo, hi in chunks(r_lo, r_hi, days):
            try:
                items = fetch_range(fetch, lo, hi)
            except garmin.KeyProblem:
                raise
            except Exception as e:  # never let one bad range stop everything
                print(f"    {lo} to {hi}: skipped ({e.__class__.__name__})")
                continue
            lo_done = min(lo_done, lo)
            for it in items:
                day = item_date(it, *date_keys)
                if day and has_data(it):
                    if day not in store:
                        added += 1
                    store[day] = it
            print(f"    {lo} to {hi}: {len(store)} days with data so far")
    save(name, store)
    meta["checked"][name] = [lo_done.isoformat(), TODAY.isoformat()]
    print(f"    done: {added} new")
    return store


def fetch_daily(lo, hi):
    return find_list(garmin.get("/usersummary-service/v2/dailysummaries",
                                {"startDate": lo.isoformat(), "endDate": hi.isoformat()}),
                     "data")


def daily_has_data(it):
    return any(dig(it, p) not in (None, 0) for p in (
        "movement.steps.value", "heartRate.restingValue", "stress.avgLevel",
        "bodyBattery.maxValue", "intensityMinutes.moderate",
        "intensityMinutes.vigorous", "respiration.avgValue"))


def fetch_sleep(lo, hi):
    return find_list(garmin.get("/sleep-service/sleep/dailySleepSummariesByDate",
                                {"startDate": lo.isoformat(), "endDate": hi.isoformat()}))


def sleep_has_data(it):
    return bool(it.get("sleepTimeSeconds"))


def fetch_hrv(lo, hi):
    return find_list(garmin.get(f"/hrv-service/hrv/daily/{lo}/{hi}"), "hrvSummaries")


def hrv_has_data(it):
    return it.get("lastNightAvg") is not None or it.get("weeklyAvg") is not None


def fetch_weight(lo, hi):
    return find_list(garmin.get(f"/weight-service/weight/range/{lo}/{hi}"),
                     "dailyWeightSummaries")


def weight_has_data(it):
    return bool(dig(it, "latestWeight.weight"))


# ---------- main ----------

def main():
    full = "--all" in sys.argv
    meta = load("meta.json", {})
    os.makedirs(DATA, exist_ok=True)
    try:
        garmin.token()
    except garmin.KeyProblem as e:
        print(e)
        sys.exit(1)

    target_from = None if full else TODAY - dt.timedelta(days=365)
    print("Downloading " + ("your full history" if full else "the last 12 months")
          + " (re-runs only fetch what's new).\n")

    acts = pull_activities(target_from, meta)
    if full:
        first = min((d(a["startTimeLocal"]) for a in acts), default=TODAY)
        day_from = first
    else:
        day_from = d(meta["days_from"]) if meta.get("days_from") else target_from
        day_from = min(day_from, target_from)
    meta["days_from"] = day_from.isoformat()

    sections = [
        ("daily.json", "Daily summaries", 60, fetch_daily, daily_has_data, ()),
        ("sleep.json", "Sleep", 31, fetch_sleep, sleep_has_data, ()),
        ("hrv.json", "HRV", 365, fetch_hrv, hrv_has_data, ()),
        ("weight.json", "Weight", 365, fetch_weight, weight_has_data, ("summaryDate",)),
    ]
    counts = {}
    for name, label, days, fetch, has, keys in sections:
        try:
            counts[label] = len(pull_days(name, label, day_from, days, fetch, has, meta, keys))
        except garmin.KeyProblem as e:
            print(e)
            sys.exit(1)
        except Exception as e:
            print(f"    {label} skipped ({e.__class__.__name__}); everything else is fine.")
            counts[label] = len(load(name, {}))

    for name, path in (("fitness_age.json", f"/fitnessage-service/fitnessage/v2/{TODAY}"),
                       ("hr_zones.json", "/biometric-service/heartRateZones/v2")):
        try:
            resp = garmin.get(path)
            if resp:
                save(name, resp)
        except Exception:
            pass

    meta["last_pull"] = dt.datetime.now().isoformat(timespec="seconds")
    save("meta.json", meta)

    print("\n=== Download complete ===")
    if acts:
        print(f"Activities:      {len(acts)}  ({acts[-1]['startTimeLocal'][:10]} "
              f"to {acts[0]['startTimeLocal'][:10]})")
    else:
        print("Activities:      0")
    for label in ("Daily summaries", "Sleep", "HRV", "Weight"):
        print(f"{label + ':':<17}{counts.get(label, 0)} days")
    print("\nSaved in the data/ folder.")


if __name__ == "__main__":
    main()
