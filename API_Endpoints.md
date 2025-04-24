**📌 API Documentation**

**📍 Endpoint:** Calculate Pricing

**📌 Method:** POST

**📌 URL:** https://jvopmaa40h.execute-api.us-east-1.amazonaws.com/prod/chatbot

Request Body (JSON)
{
 \"query\": \"I need 16 Cores CPU, 128 GB RAM, 1TB SSD + 2TB HDD storage, and Microsoft SQL Server database for application server.\"
}


Response Body (JSON)
{
"cost_estimate": [
 { 
"Server Name": "Application Server", 
"CPU": 16, 
"RAM": 128, 
"InstanceType": "r8g.4xlarge", 
"Storage": "1TB SSD + 2TB HDD", 
"Database": "Microsoft SQL Server", 
"Monthly Server Cost": "$678.64", 
"Monthly Storage Cost": "$174.08", 
"Monthly Database Cost": "$204.80", 
"Total Pricing": "$1057.52" 
} ]
}
