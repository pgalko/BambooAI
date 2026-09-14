# Multi-stage build for optimization
FROM python:3.11-slim AS builder

# Install system dependencies for building
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Create requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --user --no-cache-dir -r requirements.txt

# Production stage
FROM python:3.11-slim

# Install runtime system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Create app directory
WORKDIR /app

# Copy Python packages from builder stage
COPY --from=builder /root/.local /home/appuser/.local

# Copy application code
COPY code_executor_api.py .

# The persistent kernel. kernel_service.py is the HTTP surface; the rest are
# vendored from delv-e UNCHANGED and must stay at the same version as the copy
# in <repo>/delve. These
# have to sit together in /app.
#
# Missing any of them is a QUIET failure: code_executor_api guards the import so
# the container still serves /execute, and deep mode simply never works.
COPY kernel_service.py .
COPY kernel.py .
COPY executor.py .
COPY dataio.py .
COPY logger_config.py .

# Create necessary directories
RUN mkdir -p datasets iframe_figures temp \
    && chown -R appuser:appuser /app

# Add health check
COPY healthcheck.py .

# Switch to non-root user
USER appuser

# Add local packages to PATH
ENV PATH=/home/appuser/.local/bin:$PATH

# Expose port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=3 \
    CMD python healthcheck.py

# Run the application
CMD ["python", "code_executor_api.py"]