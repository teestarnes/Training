"""Step 3: check that the key works and show your 5 latest activities."""
import sys

import garmin


def main():
    try:
        garmin.token(force=True)
        print("Connected: Garmin accepted your key.\n")
        acts = garmin.get("/activitylist-service/activities/search/activities",
                          {"start": 0, "limit": 5}) or []
    except garmin.KeyProblem as e:
        print(e)
        sys.exit(1)
    if not acts:
        print("Connected, but no activities came back.")
        return
    print("Your 5 latest activities:")
    for a in acts:
        date = (a.get("startTimeLocal") or "")[:10]
        kind = ((a.get("activityType") or {}).get("typeKey") or "?").replace("_", " ")
        m = a.get("distance") or 0
        print(f"  {date}  {kind:<20} {m/1000:7.1f} km  ({m/1609.344:6.1f} mi)")


if __name__ == "__main__":
    main()
