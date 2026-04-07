FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends     supervisor     && rm -rf /var/lib/apt/lists/*

# Install any needed packages specified in requirements.txt
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the current directory contents into the container at /app
COPY . .

# Create logs directory
RUN mkdir -p /var/log/supervisor

# Use supervisord to manage multiple processes
CMD ["/usr/bin/supervisord", "-c", "/app/supervisord.conf"]
