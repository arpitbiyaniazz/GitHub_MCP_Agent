# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Install system dependencies including the Docker CLI 
# (Required because github_agent.py executes docker commands to run the MCP server)
RUN apt-get update && apt-get install -y \
    docker.io \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY github_agent.py .

# Expose port 8501 for Streamlit
EXPOSE 8501

# Command to run the application
CMD ["streamlit", "run", "github_agent.py", "--server.port=8501", "--server.address=0.0.0.0"]
