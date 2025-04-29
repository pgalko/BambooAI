FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies required for bambooai
RUN apt-get update && apt-get install -y \
    build-essential \
    libffi-dev \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements.txt first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install additional dependencies
RUN pip install setuptools

# Copy the application code
COPY . .

# Create necessary directories
RUN mkdir -p web_app/storage/favourites web_app/storage/threads web_app/temp web_app/logs

# Expose the port
EXPOSE 5000

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Set the working directory to web_app
WORKDIR /app/web_app

# Start the Flask application
CMD ["python", "app.py"]