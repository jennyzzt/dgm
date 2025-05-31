# Use an official Python runtime as the base image
FROM python:3.10-slim

# Install system-level dependencies, including git and curl
RUN rm -rf /var/lib/apt/lists/* \
    && apt-get clean \
    && apt-get update \
    && apt-get install -y --fix-missing \
    build-essential \
    git \
    curl \
    ca-certificates \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Set the working directory inside the container
WORKDIR /dgm

# Copy the entire repository into the container
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Keep the container running by default
CMD ["tail", "-f", "/dev/null"]