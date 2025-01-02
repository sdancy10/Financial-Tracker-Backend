FROM python:3.9-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Set environment variables
ENV GOOGLE_CLOUD_PROJECT=your-project-id
ENV PYTHONUNBUFFERED=1

# Run the application
CMD ["python", "main.py"] 