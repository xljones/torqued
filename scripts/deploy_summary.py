import datetime
import json
import os
import re
import subprocess


def relative_time(iso_string):
    ts = iso_string if iso_string.endswith("Z") else iso_string + "Z"
    dt = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    diff_sec = round((datetime.datetime.now(datetime.timezone.utc) - dt).total_seconds())
    diff_min = round(diff_sec / 60)
    diff_hour = round(diff_min / 60)
    diff_day = round(diff_hour / 24)
    diff_week = round(diff_day / 7)
    diff_month = round(diff_day / 30.5)
    if diff_sec < 60:   return f"{diff_sec} second{'s' if diff_sec != 1 else ''} ago"
    if diff_min < 60:   return f"{diff_min} minute{'s' if diff_min != 1 else ''} ago"
    if diff_hour < 24:  return f"{diff_hour} hour{'s' if diff_hour != 1 else ''} ago"
    if diff_day < 7:    return f"{diff_day} day{'s' if diff_day != 1 else ''} ago"
    if diff_week < 5:   return f"{diff_week} week{'s' if diff_week != 1 else ''} ago"
    if diff_month < 12: return f"{diff_month} month{'s' if diff_month != 1 else ''} ago"
    diff_year = round(diff_month / 12)
    return f"{diff_year} year{'s' if diff_year != 1 else ''} ago"


ver = re.search(r'version\s*=\s*"([^"]+)"', open("pyproject.toml").read())
ver = ver.group(1) if ver else "unknown"

dist_sha = subprocess.check_output(["git", "log", "-1", "--format=%h"]).decode().strip()
now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

bi = json.load(open("dist/build-info.json")) if os.path.exists("dist/build-info.json") else {}

print("")
print("════ Deployment complete ════════════════════════════")
print(f"  Version:     {ver}")
if bi:
    print(f"  Commit:      {bi.get('sha', '?')} — {bi.get('msg', '?')}")
    built_at = bi.get("built_at", "?")
    rel = f" ({relative_time(built_at)})" if built_at != "?" else ""
    print(f"  dist SHA:    {dist_sha}  (built {built_at}{rel})")
print(f"  Deployed at: {now}")
print("════════════════════════════════════════════════════")
print("Reload the web app in the PythonAnywhere Web tab.")
print("")
