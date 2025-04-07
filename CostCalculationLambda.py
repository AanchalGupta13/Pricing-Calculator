import json
import boto3
import re
import logging

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Create AWS Clients
ec2_client = boto3.client('ec2')
pricing_client = boto3.client("pricing", region_name="us-east-1")

# Fetch Available EC2 instance types
def fetch_ec2_instance_types():
    try:
        response = ec2_client.describe_instance_types()
        instance_data = {
            instance['InstanceType']: {
                "vCPUs": instance['VCpuInfo']['DefaultVCpus'],
                "MemoryMiB": instance['MemoryInfo']['SizeInMiB'] // 1024  # Convert MB to GB
            }
            for instance in response['InstanceTypes']
        }      
        return instance_data
    except Exception as e:
        logger.error(f"Error fetching EC2 instance types: {e}")
        return {}
      
# Find best matching instances
def find_best_match(requirements, ec2_instances):
    if not requirements or not ec2_instances:
        logger.warning("Empty requirements or EC2 instances")
        return []
    matched_instances = []
    for req in requirements:
        best_match = None
        int(req["CPU"])
        int(req["RAM"])
        for instance_name, instance in ec2_instances.items():
            if instance["vCPUs"] >= req["CPU"] and instance["MemoryMiB"] >= req["RAM"]:
                if best_match is None or (instance["vCPUs"] < best_match["vCPUs"] or instance["MemoryMiB"] < best_match["MemoryMiB"]):
                    best_match = {
                        "InstanceType": instance_name,
                        "vCPUs": instance["vCPUs"],
                        "MemoryMiB": instance["MemoryMiB"]
                    }
        if best_match:
            matched_instances.append({
                "Server Name": req["Server Name"],
                "CPU": best_match["vCPUs"],
                "RAM": best_match["MemoryMiB"],
                "InstanceType": best_match["InstanceType"],
                "Storage": req["Storage"],
                "Database": req["Database"]
            })
    return matched_instances

# Get instance pricing
def get_instance_price(instance_type, region="US East (N. Virginia)"):
    try:
        response = pricing_client.get_products(
            ServiceCode="AmazonEC2",
            Filters=[
                {"Type": "TERM_MATCH", "Field": "instanceType", "Value": instance_type},
                {"Type": "TERM_MATCH", "Field": "location", "Value": region},
                {"Type": "TERM_MATCH", "Field": "operatingSystem", "Value": "Linux"},
                {"Type": "TERM_MATCH", "Field": "tenancy", "Value": "Shared"},
                {"Type": "TERM_MATCH", "Field": "preInstalledSw", "Value": "NA"},
                {"Type": "TERM_MATCH", "Field": "capacitystatus", "Value": "Used"}
            ]
        )
        price_data = response["PriceList"]
        if not price_data:
            return None
        price_json = json.loads(price_data[0])
        price_per_hour = float(price_json['terms']['OnDemand'].values().__iter__().__next__()['priceDimensions'].values().__iter__().__next__()['pricePerUnit']['USD'])
        return price_per_hour
    except Exception as e:
        logger.error(f"Error fetching price for {instance_type}: {e}")
        return None

# Calculate storage cost
def calculate_storage_cost(storage_str):
    storage_cost_per_gb = {"SSD": 0.08, "HDD": 0.045, "NVME": 0.10}
    total_cost = 0
    storage_items = storage_str.split("+")
    for storage in storage_items:
        storage = storage.strip()
        size_match = re.search(r'(\d+)(TB|GB)', storage, re.IGNORECASE)
        type_match = re.search(r'(SSD|HDD|NVMe)', storage, re.IGNORECASE)
        if not size_match or not type_match:
            continue
        size_value = int(size_match.group(1))
        storage_type = type_match.group(1).strip().upper()  # Convert to uppercase
        # Convert TB to GB
        size_gb = size_value * 1024 if size_match.group(2).upper() == "TB" else size_value
        storage_type = type_match.group(1).upper()
        if storage_type in storage_cost_per_gb:
            total_cost += size_gb * storage_cost_per_gb[storage_type]
    return round(total_cost, 2)

# Calculate database cost
def calculate_database_cost(database, storage_str):
    database_cost_per_gb = {"MySQL": 0.10, "PostgreSQL": 0.10, "Microsoft SQL Server": 0.20, "Oracle Database": 0.30, "Redis": 0.15}
    if database == "None" or database not in database_cost_per_gb:
        return 0.0
    size_match = re.search(r'(\d+)(TB|GB)', storage_str, re.IGNORECASE)
    if not size_match:
        return 0.0
    size_value = int(size_match.group(1))
    size_gb = size_value * 1024 if size_match.group(2).upper() == "TB" else size_value
    return round(size_gb * database_cost_per_gb[database], 2)

# Lambda handler function
def lambda_handler(event, context):
    logger.info("Received event: " + json.dumps(event))
    ec2_instances = fetch_ec2_instance_types()
    try:
        requirements = event.get("requirements", [])
        logger.info("Extracted requirements: " + json.dumps(requirements))

        matched_instances = find_best_match(requirements, ec2_instances)
        
        # Calculate pricing
        for instance in matched_instances:
            hourly_price = get_instance_price(instance['InstanceType'])
            instance["Monthly Server Cost"] = f"${round(hourly_price * 24 * 30, 2)}" if hourly_price else "Price Not Available"
            instance["Monthly Storage Cost"] = f"${calculate_storage_cost(instance['Storage']):.2f}"
            instance["Monthly Database Cost"] = f"${calculate_database_cost(instance['Database'], instance['Storage']):.2f}"
            instance["Total Pricing"] = f"${round(float(instance['Monthly Server Cost'][1:]) + float(instance['Monthly Storage Cost'][1:]) + float(instance['Monthly Database Cost'][1:]), 2)}"
        
        logger.info(f"Final matched instances: {json.dumps(matched_instances)}")
        return {"statusCode": 200, "body": json.dumps(matched_instances)}
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return {"statusCode": 500, "body": json.dumps(f"Unexpected error: {e}")}