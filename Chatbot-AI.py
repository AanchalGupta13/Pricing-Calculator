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
                Extract Server, CPU, RAM, Storage, and Database details from this requirement: '{query}'. 
                Provide only a valid JSON object without markdown, explanations, or formatting tags.
            """,
            "textGenerationConfig": {
                "maxTokenCount": 100,  # Increased to avoid truncation
                "temperature": 0.2,  # Reduce randomness
                "topP": 1
            }
        }

        response = bedrock_runtime.invoke_model(
            modelId='amazon.titan-text-express-v1',
            contentType='application/json',
            accept='application/json',
            body=json.dumps(request_body)
        )

        raw_response = response['body'].read().decode('utf-8')
        logger.info(f"Bedrock Raw Response: {raw_response}")

        if not raw_response.strip():
            logger.error("Bedrock response is empty!")
            return {"error": "Bedrock returned an empty response"}

        response_data = json.loads(raw_response)
        logger.info(f"Bedrock Response Data: {response_data}")

        # Ensure "results" exists and is not empty
        if "results" not in response_data or not response_data["results"]:
            logger.error(f"Unexpected Bedrock response format: {response_data}")
            return {"error": "Invalid response from Bedrock"}
        
        # if "results" in response_data and response_data["results"]:
        output_text = response_data["results"][0].get("outputText", "").strip()
        logger.info(f"Bedrock Output Text: {output_text}")

        # Remove unwanted markdown-style JSON formatting
        output_text = output_text.replace("```tabular-data-json", "").replace("```", "").strip()
        logger.info(f"Cleaned Bedrock Output Text: {output_text}")
        output_text = output_text.replace("rows", "requirements")
        logger.info(f"Cleaned Bedrock Output Text: {output_text}")
        # data = output_text
        # output_text = {"requirements": data.pop("rows")}

        try:
            extracted_config = json.loads(output_text)
            logger.info(f"Extracted Config: {extracted_config}")

            # Fix structure if Bedrock returns a list instead of dictionary
            if isinstance(extracted_config, list):
                extracted_config = {"requirements": extracted_config}
            logger.info(f"Fixed Extracted Config: {extracted_config}")
            logger.info(type(extracted_config))
            # Ensure extracted_config has "requirements" key and it's a list
            if not isinstance(extracted_config, dict) or "requirements" not in extracted_config:
                logger.error(f"Unexpected Bedrock response format: {extracted_config}")
                return {"error": "Invalid response format from Bedrock"}
                
            requirements = extracted_config["requirements"]

            if not isinstance(requirements, list):
                logger.error(f"Expected 'requirements' to be a list, but got: {type(requirements)}")
                return {"error": "Invalid response structure"}

            logger.info(f"Valid Requirements List: {requirements}")

            # return extracted_config

            # Extract CPU and RAM from requirements
            filtered_requirements = []
            for req in requirements:
                if isinstance(req, dict):
                    cpu_match = re.search(r'(\d+)\s*[cC]ores', req.get('CPU', ''))
                    ram_match = re.search(r'(\d+)\s*[gG][bB]', req.get('RAM', ''))
                    logger.info(f"CPU Match: {cpu_match}, RAM Match: {ram_match}")

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

                # # Convert list of key-value pairs to dictionary if required
                # if "rows" in extracted_config and isinstance(extracted_config["rows"], list):
                #     extracted_config = {row["System"]: row["Value"] for row in extracted_config["rows"] if "System" in row and "Value" in row}

                # logger.info(f"Extracted Config: {extracted_config}")
                # return {extracted_config} if isinstance(extracted_config, list) else extracted_config

        except json.JSONDecodeError as e:
            logger.error(f"JSON Parsing Error: {str(e)} - Raw response: {output_text}")
            return {"error": "Invalid JSON response from Bedrock"}

        # else:
        #     logger.error(f"Unexpected response format from Bedrock: {response_data}")
        #     return {"error": "Invalid response from Bedrock"}

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

    # except Exception as e:
    #     logger.error(f"Error invoking cost estimation Lambda: {str(e)}")
    #     raise

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
        logger.info(type(cost_estimate))    

        response_body = json.dumps({"cost_estimate": cost_estimate})
        logger.info(f"Response Body: {response_body}")
        logger.info(type(response_body))

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
