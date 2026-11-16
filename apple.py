"""Read an Apple Health export (export.zip) into data/apple.json.

    python3 apple.py

Put export.zip in the garmin-dashboard folder first (iPhone: Health app >
profile picture > Export All Health Data). Everything stays on this device.
Re-run it whenever you drop in a newer export.
"""
import glob
import json
import os
import sys
import time
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")

QTY = {
    "HKQuantityTypeIdentifierHeartRateVariabilitySDNN": "hrv",
    "HKQuantityTypeIdentifierRestingHeartRate": "rhr",
    "HKQuantityTypeIdentifierVO2Max": "vo2max",
    "HKQuantityTypeIdentifierBodyMass": "weight_lb",
    "HKQuantityTypeIdentifierRespiratoryRate": "resp",
}
BP_SYS = "HKQuantityTypeIdentifierBloodPressureSystolic"
BP_DIA = "HKQuantityTypeIdentifierBloodPressureDiastolic"
SLEEP = "HKCategoryTypeIdentifierSleepAnalysis"
STAGE = {
    "HKCategoryValueSleepAnalysisAsleepDeep": "deep",
    "HKCategoryValueSleepAnalysisAsleepCore": "core",
    "HKCategoryValueSleepAnalysisAsleepREM": "rem",
    "HKCategoryValueSleepAnalysisAsleepUnspecified": "asleep",
    "HKCategoryValueSleepAnalysisAsleep": "asleep",
    "HKCategoryValueSleepAnalysisAwake": "awake",
}


def find_export():
    spots = [HERE, DATA, os.path.dirname(HERE)]
    found = []
    for spot in spots:
        found += glob.glob(os.path.join(spot, "*.zip"))
        x = os.path.join(spot, "apple_health_export", "export.xml")
        if os.path.exists(x):
            found.append(x)
    found = [f for f in found if "export" in os.path.basename(f).lower()
             or f.endswith("export.xml")]
    return max(found, key=os.path.getmtime) if found else None


def open_xml(path):
    if path.endswith(".xml"):
        return open(path, "rb")
    z = zipfile.ZipFile(path)
    names = [n for n in z.namelist() if n.endswith("/export.xml") or n == "export.xml"]
    if not names:
        print("That zip doesn't contain export.xml. Is it the Apple Health export?")
        sys.exit(1)
    return z.open(names[0])


def stamp(s):
    """'2026-11-14 06:31:02 -0700' -> seconds since epoch."""
    return time.mktime(time.strptime(s[:19], "%Y-%m-%d %H:%M:%S"))


def main():
    path = find_export()
    if not path:
        print("I couldn't find export.zip. Put it in the garmin-dashboard folder "
              "(Files app: On My iPad > a-Shell > garmin-dashboard) and try again.")
        sys.exit(1)
    print(f"Reading {os.path.basename(path)} (this can take a few minutes)...")

    daily = {k: defaultdict(list) for k in QTY.values()}
    bp = defaultdict(dict)                        # startDate -> {sys, dia}
    sleep = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    n = 0
    t0 = time.time()

    with open_xml(path) as f:
        ctx = ET.iterparse(f, events=("start", "end"))
        _, root = next(ctx)
        for ev, el in ctx:
            if ev != "end" or el.tag != "Record":
                if ev == "end" and el.tag in ("Workout", "ActivitySummary", "Correlation"):
                    el.clear()
                continue
            n += 1
            if n % 250000 == 0:
                print(f"    {n:,} records read ({time.time() - t0:.0f}s)")
            a = el.attrib
            typ = a.get("type")
            try:
                if typ in QTY:
                    key = QTY[typ]
                    v = float(a["value"])
                    if key == "weight_lb" and a.get("unit") == "kg":
                        v *= 2.20462
                    if key == "weight_lb" and a.get("unit") == "g":
                        v /= 453.592
                    daily[key][a["startDate"][:10]].append(v)
                elif typ in (BP_SYS, BP_DIA):
                    bp[a["startDate"][:16]]["sys" if typ == BP_SYS else "dia"] = float(a["value"])
                elif typ == SLEEP and a.get("value") in STAGE:
                    night = a["endDate"][:10]          # the morning you woke up
                    mins = (stamp(a["endDate"]) - stamp(a["startDate"])) / 60
                    if 0 < mins < 16 * 60:
                        sleep[night][a.get("sourceName", "?")][STAGE[a["value"]]] += mins
            except (KeyError, ValueError):
                pass
            el.clear()
            if n % 5000 == 0:
                root.clear()

    out = {"source": os.path.basename(path),
           "imported": time.strftime("%Y-%m-%d")}
    for key, days in daily.items():
        out[key] = {d: round(sum(v) / len(v), 1) for d, v in sorted(days.items())}

    # Several apps can log the same night; keep the one with the most detail.
    nights = {}
    for night, sources in sorted(sleep.items()):
        def score(st):
            staged = st.get("deep", 0) + st.get("core", 0) + st.get("rem", 0)
            return (staged > 0, staged + st.get("asleep", 0))
        best = max(sources.values(), key=score)
        total = sum(best.get(k, 0) for k in ("deep", "core", "rem", "asleep"))
        if total >= 60:
            nights[night] = {k: round(best.get(k, 0)) for k in
                             ("deep", "core", "rem", "asleep", "awake")}
            nights[night]["total"] = round(total)
    out["sleep"] = nights

    out["bp"] = [{"when": k, "sys": v["sys"], "dia": v["dia"]}
                 for k, v in sorted(bp.items()) if "sys" in v and "dia" in v]

    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(DATA, "apple.json"), "w") as f:
        json.dump(out, f, separators=(",", ":"))

    def span(dct):
        return f"({min(dct)} to {max(dct)})" if dct else ""

    print(f"\n=== Apple Health import complete ({n:,} records read) ===")
    print(f"HRV:              {len(out['hrv'])} days {span(out['hrv'])}")
    print(f"Resting HR:       {len(out['rhr'])} days {span(out['rhr'])}")
    print(f"Sleep:            {len(nights)} nights {span(nights)}")
    print(f"Blood pressure:   {len(out['bp'])} readings")
    print(f"Weight:           {len(out['weight_lb'])} days")
    print(f"VO2 max:          {len(out['vo2max'])} readings")
    print("\nSaved to data/apple.json. You can delete export.zip now to free up space,"
          "\nor keep it; a newer export will be picked up automatically.")


if __name__ == "__main__":
    main()
