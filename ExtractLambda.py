import json
import boto3
import pandas as pd
import io
import os
import re
import logging
from datetime import datetime
import pytz

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Create AWS Clients
s3_client = boto3.client("s3")
lambda_client = boto3.client("lambda")

# Define IST timezone
ist = pytz.timezone("Asia/Kolkata")
# Get current time in IST
current_time_ist = datetime.now(ist)
# Format timestamp as "HH:MM:SS_DD-MM-YYYY"
timestamp_str = current_time_ist.strftime("%H:%M:%S_%d-%m-%Y")

# Environment variables
BUCKET_NAME = os.environ.get("S3_BUCKET_NAME", "price-inventory")
CALCULATE_LAMBDA_NAME = os.environ.get("CALCULATE_LAMBDA_NAME", "CostCalculationLambda")

# Fetch and read the Excel file from S3
def fetch_requirements_from_s3(bucket, file_key):
    try:
        s3_object = s3_client.get_object(Bucket=bucket, Key=file_key)
        file_stream = io.BytesIO(s3_object["Body"].read())
        df = pd.read_excel(file_stream)
        # Replace NaN values with None
        df = df.where(pd.notna(df), None)
        requirements = df.to_dict(orient="records")
        logger.info(f"Requirements fetched from S3: {requirements}")
        return requirements
    except Exception as e:
        logger.error(f"Error fetching file from S3: {e}")
        return []

# Extract CPU and RAM from requirements
def extract_cpu_ram(requirements):
    logger.info(f"Extracting CPU and RAM from requirements: {requirements}")
    filtered_requirements = []

    for req in requirements:
        try:
            cpu_text = str(req.get('CPU', '')).strip()
            ram_text = str(req.get('RAM', '')).strip()

            # Extract only numeric CPU value (e.g., "8" from "8 Cores @ 3.2GHz")
            cpu_match = re.search(r'(\d+)\s*Cores', cpu_text, re.IGNORECASE)
            # Extract RAM value (e.g., "16" from "16GB")
            ram_match = re.search(r'(\d+)', ram_text)

            if cpu_match and ram_match:
                filtered_requirements.append({
                    'Server Name': req.get('Server Name', 'Unknown'),
                    'IP Address': req.get('IP Address', 'Unknown'),
                    'Storage': req.get('Storage', 'Unknown'),
                    'Database': req.get('Database', 'Unknown'),
                    'CPU': int(cpu_match.group(1)),  # Extracted CPU cores
                    'RAM': int(ram_match.group(1))   # Extracted RAM in GB
                })
            else:
                logger.warning(f"Skipping entry with missing CPU/RAM: {req}")

        except Exception as e:
            logger.error(f"Error extracting CPU/RAM from {req}: {e}")

    return filtered_requirements  # Returns a list of cleaned CPU and RAM values

# Store results in S3 as CSV
def store_results_in_s3_csv(data, bucket, key):
    try:
        # Ensure data is a list of dictionaries
        if not isinstance(data, list) or not all(isinstance(i, dict) for i in data):
            logger.error(f"Invalid processed data format: {data}")
            return False

        df = pd.DataFrame(data)
        csv_buffer = io.StringIO()
        df.to_csv(csv_buffer, index=False)
        s3_client.put_object(Bucket=bucket, Key=key, Body=csv_buffer.getvalue(), ContentType="text/csv")
        logger.info(f"Results uploaded to S3: s3://{bucket}/{key}")
        return True
    except Exception as e:
        logger.error(f"Error uploading CSV to S3: {e}")
        return False

# Function to remove NaN values
def clean_nan_values(obj):
    """Recursively replaces NaN values with None in a dictionary."""
    if isinstance(obj, dict):
        return {k: clean_nan_values(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_nan_values(i) for i in obj]
    elif isinstance(obj, float) and pd.isna(obj):  # Check for NaN
        return None
    return obj

# Lambda handler function
def lambda_handler(event, context):
    try:
        bucket = event["Records"][0]["s3"]["bucket"]["name"]
        file_key = event["Records"][0]["s3"]["object"]["key"]

        # Extract base name of uploaded file (without extension)
        original_filename = os.path.splitext(os.path.basename(file_key))[0]
        # Create a filename with IST timestamp
        CSV_FILE_KEY = f"result_{original_filename}_{timestamp_str}.csv"
        
        requirements = fetch_requirements_from_s3(bucket, file_key)
        if not requirements:
            return {"statusCode": 500, "body": json.dumps("Failed to fetch requirements from S3.")}

        # Clean NaN values
        cleaned_requirements = clean_nan_values(requirements)
        extracted_requirements = extract_cpu_ram(cleaned_requirements)

        if not extracted_requirements:
            return {"statusCode": 500, "body": json.dumps("No valid CPU/RAM data found.")}

        logger.info(f"Extracted Requirements Before Sending to Lambda: {json.dumps(extracted_requirements, indent=2)}")

        # Invoke CostCalculationLambda
        response = lambda_client.invoke(
            FunctionName=CALCULATE_LAMBDA_NAME,
            InvocationType="RequestResponse",
            Payload=json.dumps({"requirements": extracted_requirements}, default=str)
        )

        response_payload = json.loads(response["Payload"].read())
        processed_data = json.loads(response_payload.get("body", "[]"))

        # Log and Validate processed data
        if not isinstance(processed_data, list) or not all(isinstance(i, dict) for i in processed_data):
            logger.error(f"Invalid processed data format received: {processed_data}")
            return {"statusCode": 500, "body": json.dumps("Invalid processed data format.")}

        if store_results_in_s3_csv(processed_data, bucket=BUCKET_NAME, key=CSV_FILE_KEY):
            return {"statusCode": 200, "body": json.dumps(f"CSV stored at s3://{BUCKET_NAME}/{CSV_FILE_KEY}")}

        return {"statusCode": 500, "body": json.dumps("Failed to store results in S3.")}

    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return {"statusCode": 500, "body": json.dumps(f"Unexpected error: {e}")}