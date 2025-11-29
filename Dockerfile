# ---- Python Base ----
FROM python:3.10-slim

# ---- Work Directory ----
WORKDIR /app

# ---- Copy Project ----
COPY . .

# ---- Install Requirements ----
RUN pip install --no-cache-dir -r requirements.txt

# ---- Start the 5 Scanners ----
CMD ["python3", "all_scanners_5_runner.py"]
