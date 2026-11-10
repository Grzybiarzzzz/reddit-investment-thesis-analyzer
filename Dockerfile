# Use Python 3.12 on a slim Debian base (~150MB vs ~1GB for full image)
FROM python:3.12-slim

# Prevent Python from writing .pyc files and enable unbuffered output
# so logs appear in real-time in `docker logs`
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DASHBOARD_HOST=0.0.0.0

# Set the working directory inside the container
WORKDIR /app

# Copy only requirements first — Docker caches each layer, so if
# requirements.txt hasn't changed, pip install is skipped on rebuild
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the project into the container
COPY . .

# Expose the dashboard port
EXPOSE 8050

# Default command: run the dashboard, listening on all interfaces
# (0.0.0.0 is required — without it, the container only listens on
# localhost which is unreachable from outside the container)
CMD ["python", "main.py", "dashboard"]
