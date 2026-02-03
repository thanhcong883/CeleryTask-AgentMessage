FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Install any needed packages specified in requirements.txt
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the current directory contents into the container at /app
COPY . .


# Command to run the Celery worker (this will be overridden by docker-compose for worker and beat)
CMD ["celery", "--app=tasks", "worker", "--loglevel=info"]
