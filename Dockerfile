FROM bitnami/spark:3.5.0

# Install Python and pip
USER root
RUN apt-get update && apt-get install -y python3-pip

# Copy and install requirements
COPY requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt

# Use Spark's user again
USER 1001