import json
import boto3
import logging
import re

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# AWS Clients
bedrock_runtime = boto3.client('bedrock-runtime', region_name='us-east-1')
lambda_client = boto3.client('lambda')

def extract_configuration(query):
    """Extracts Server, CPU, RAM, Storage, and Database details using AWS Bedrock."""
    try:
        logger.info(f"Extracting config from: {query}")

        request_body = {
            "inputText": f"""
            You are a strict JSON generator.
            Based on the user requirement below, extract only the server configuration in valid, structured JSON format. No extra text, no markdown, no explanation.
            Expected format:
            {{
                "requirements": [
                    {{
                        "Server Name": "...",
                        "CPU": "...",
                        "RAM": "...",
                        "Storage": "...",
                        "Database": "..."
                    }}
                ]
            }}
            User Input: "{query}"
            Respond ONLY with valid JSON wrapped in a dictionary with a key "requirements".""",
            "textGenerationConfig": {
                "maxTokenCount": 500,  # Increased to avoid truncation
                "temperature": 0.2,  # Reduce randomness
                "topP": 1
            }
        }
        logger.info(f"Request body: {request_body}")

        response = bedrock_runtime.invoke_model(
            modelId='amazon.titan-text-express-v1',
            contentType='application/json',
            accept='application/json',
            body=json.dumps(request_body)
        )

        raw_response = response['body'].read().decode('utf-8')

        if not raw_response.strip():
            logger.error("Bedrock response is empty!")
            return {"error": "Bedrock returned an empty response"}

        try:
            # Try loading Bedrock response
            extracted_json = json.loads(raw_response)
            # If it's already the expected structure from Bedrock
            if isinstance(extracted_json, dict) and "results" in extracted_json:
                output_text = extracted_json["results"][0].get("outputText", "").strip()
            else:
                # If Bedrock directly returned an array or object
                output_text = raw_response.strip()

            # Clean up unwanted markdown formatting
            output_text = output_text.replace("```json", "").replace("```", "").strip()
            output_text = output_text.replace("```tabular-data-json", "").replace("```", "").strip()

            # Attempt to parse final cleaned JSON output
            extracted_config = json.loads(output_text)

            # Wrap if it’s a list
            if isinstance(extracted_config, list):
                extracted_config = {"requirements": extracted_config}

            if "requirements" not in extracted_config or not isinstance(extracted_config["requirements"], list):
                logger.error(f"Unexpected format from Bedrock: {extracted_config}")
                return {"error": "Invalid format in Bedrock response"}

            filtered_requirements = []
            for req in extracted_config["requirements"]:
                if isinstance(req, dict):
                    cpu_match = re.search(r'(\d+)\s*[cC]ores', req.get('CPU', ''))
                    ram_match = re.search(r'(\d+)\s*[gG][bB]', req.get('RAM', ''))

                    if cpu_match and ram_match:
                        filtered_req = {
                            'Server Name': req.get('Server Name', 'Unknown'),
                            'CPU': int(cpu_match.group(1)),
                            'RAM': int(ram_match.group(1)),
                            'Storage': req.get('Storage', 'Unknown'),
                            'Database': req.get('Database', 'Unknown')
                        }
                        filtered_requirements.append(filtered_req)

            logger.info(f"Filtered Requirements: {filtered_requirements}")
            return filtered_requirements
        except json.JSONDecodeError as e:
            logger.error(f"JSON Parsing Error: {str(e)} - Raw response: {raw_response}")
            return {"error": "Invalid JSON response from Bedrock"}

    except Exception as e:
        logger.error(f"Error extracting configuration: {str(e)}")
        raise

def invoke_cost_lambda(config_data):
    """Calls the existing Lambda function to estimate costs."""
    try:
        logger.info(f"Invoking cost Lambda with config: {config_data}")
        
        # Wrap the list inside a dictionary with "requirements" key
        payload = {"requirements": config_data}

        response = lambda_client.invoke(
            FunctionName="CostCalculationLambda",
            InvocationType="RequestResponse",
            Payload=json.dumps(payload)  # Ensure only one level of serialization
        )

        response_payload = json.loads(response['Payload'].read())
        logger.info(f"Lambda Response: {response_payload}")
        if "body" in response_payload:
            processed_data = json.loads(response_payload["body"])
        else:
            logger.error("Invalid response format from Cost Lambda")
            return {"error": "Invalid response from Cost Lambda"}
        logger.info(f"Processed Data: {processed_data}")
        return processed_data

    except Exception as e:
        logger.error(f"Error invoking cost estimation Lambda: {str(e)}")
        return {"error": "Failed to invoke cost Lambda"}

def lambda_handler(event, context):
    logger.info(f"Received event: {event}")
    try:
        # Extract request body properly
        body = json.loads(event.get("body", "{}"))

        query = body.get("query", "").strip() or body.get("message", "").strip()
        if not query:
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"error": "Missing 'query' parameter"})
            }

        # Extract parameters from user input
        config_data = extract_configuration(query)
        logger.info(f"Config Data: {config_data}")

        if "error" in config_data:
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps(config_data)
            }

        # Get cost estimation
        cost_estimate = invoke_cost_lambda(config_data)
        logger.info(f"Cost Estimate: {cost_estimate}")

        response_body = json.dumps({"cost_estimate": cost_estimate})
        logger.info(f"Response Body: {response_body}")

        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": response_body
        }

    except json.JSONDecodeError:
        logger.error("Invalid JSON format in request body")
        return {
            "statusCode": 400,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "Invalid JSON format in request body."})
        }

    except Exception as e:
        logger.error(f"Error processing request: {str(e)}")
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "Internal server error."})
        }