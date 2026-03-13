import os, time
log_path = "logs/app.log"
# Get last 100 lines
with open(log_path, encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()
for line in lines[-80:]:
    print(line.rstrip())
