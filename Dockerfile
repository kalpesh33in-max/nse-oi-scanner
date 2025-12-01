# Dockerfile – Railway deploys this

FROM python:3.10

# Work directory inside container
WORKDIR /app

# Copy code
COPY . .

# Install dependencies
# Make sure requirements.txt has: requests, pytz, etc.
RUN pip install --no-cache-dir -r requirements.txt

# Run the 5-scanner runner
CMD ["python", "all_scanners_5_runner.py"]
