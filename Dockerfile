# Use an official Python runtime as a parent image
FROM python:3.9-slim-buster

# Set the working directory in the container
WORKDIR /app

# Install any needed packages specified in requirements.txt
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the current directory contents into the container at /app
COPY . .

# Define environment variable for Celery broker (optional, can be overridden by docker-compose.yml)
ENV REDIS_URL=redis://redis:6379/0

# Command to run the Celery worker (this will be overridden by docker-compose for worker and beat)
CMD ["celery", "--app=tasks", "worker", "--loglevel=info"]
