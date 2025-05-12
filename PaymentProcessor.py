import json
import psycopg2
import os
from datetime import datetime
from psycopg2.extras import RealDictCursor
import logging
import razorpay

# Configure logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)

try:
    razorpay_client = razorpay.Client(auth=(
        os.environ['RAZORPAY_KEY_ID'],
        os.environ['RAZORPAY_KEY_SECRET']
    ))
except Exception as e:
    logger.error(f"Razorpay client initialization failed: {str(e)}")
    raise e

# Database connection helper
def get_db_connection():
    conn = psycopg2.connect(
        host=os.environ['DB_HOST'],
        database=os.environ['DB_NAME'],
        user=os.environ['DB_USER'],
        password=os.environ['DB_PASSWORD'],
        port=os.environ.get('DB_PORT', '5432')
    )
    return conn

def lambda_handler(event, context):
    logger.info(f"Received event: {event}")
    logger.info(f"Body type: {type(event.get('body'))}")
    logger.info(f"Body: {event.get('body')}")
    
    try:
        # Parse the incoming event
        body = json.loads(event['body']) if event.get('body') else {}
        logger.info(f"Parsed body: {body}")
        action = body.get('action')
        email = body.get('email', '').lower().strip()
        
        # Route based on action
        if action == 'processPayment':
            return handle_payment(body)
        elif action == 'checkStatus':
            return handle_status_check(body)
        elif action == 'incrementCounter':
            return handle_counter_increment(body)
        elif action == 'verifyUser':
            return handle_user_verification(body)
        else:
            return {
                'statusCode': 400,
                'body': json.dumps({'success': False, 'message': 'Invalid action specified'})
            }
            
    except json.JSONDecodeError:
        return {
            'statusCode': 400,
            'body': json.dumps({'success': False, 'message': 'Invalid JSON format'})
        }
    except KeyError as e:
        return {
            'statusCode': 400,
            'body': json.dumps({'success': False, 'message': f'Missing required field: {str(e)}'})
        }
    except Exception as e:
        print(f"Error in unified lambda: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'success': False, 
                'message': 'Internal server error',
                'error': str(e)
            })
        }

def handle_user_verification(body):
    """Verify user exists in bbt_oauthusers table"""
    try:
        email = body.get('email', '').lower().strip()
        if not email:
            return {
                'statusCode': 400,
                'headers': {
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Headers": "Content-Type",
                    "Access-Control-Allow-Methods": "POST,OPTIONS"
                },
                'body': json.dumps({'isValidUser': False, 'message': 'Email is required'})
            }
            
        logger.info(f"Verifying user: {email}")
    
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                # Check if user exists in oauth table
                cursor.execute("""
                    SELECT EXISTS(
                        SELECT 1 FROM public.bbt_oauthusers 
                        WHERE LOWER(TRIM(email)) = %s
                    ) AS user_exists
                """, (email,))
                result = cursor.fetchone()
                user_exists = result['user_exists'] if result else False
                logger.info(f"User exists in oauth table: {bool(user_exists)}")
                logger.info(f"User data: {user_exists}")    
        return {
            'statusCode': 200,
            'headers': {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type",
                "Access-Control-Allow-Methods": "POST,OPTIONS"
            },
            'body': json.dumps({
                'isValidUser':  result['user_exists'],
                'email': email,
            })
        }
    except Exception as e:
        logger.error(f"Error in user verification: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type",
                "Access-Control-Allow-Methods": "POST,OPTIONS"
            },
            'body': json.dumps({
                'isValidUser': False,
                'message': 'Internal server error'
            })
        }    

def handle_payment(body):
    """Handle payment processing and store in bbt_premiumusers"""
    try:
        txn_id = body['paymentId']
        email = body['email'].lower().strip()
        name = body['name']
        phone = body['phone']
        txn_time = datetime.now()
    
        # Verify payment with Razorpay API (simplified)
        is_payment_valid = verify_razorpay_payment(txn_id)
        logger.info(f"Payment verification result: {is_payment_valid}")
    
        if not is_payment_valid:
            logger.info(f"Payment verification failed for transaction ID: {txn_id}")
            return {
                'statusCode': 400,
                'headers': {
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Headers": "Content-Type",
                    "Access-Control-Allow-Methods": "POST,OPTIONS"
                },
                'body': json.dumps({'success': False, 'message': 'Payment verification failed'})
            }
    
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    INSERT INTO public.bbt_premiumusers (
                        name, email, phone, txn_id
                    ) VALUES (%s, %s, %s, %s)
                    RETURNING *
                """, (
                    name,
                    email,
                    phone,
                    txn_id
                ))
                # conn.commit()

                cursor.execute("""
                    INSERT INTO public.pricingcalculator (
                        name, email, phone, txn_id, txn_time, subscribed
                    ) VALUES (%s, %s, %s, %s, %s, true)
                    ON CONFLICT (email)
                    DO UPDATE SET 
                    name = EXCLUDED.name,
                    phone = EXCLUDED.phone,
                    txn_id = EXCLUDED.txn_id,
                    txn_time = EXCLUDED.txn_time,
                    subscribed = EXCLUDED.subscribed
                    RETURNING *
                """, (
                    name,
                    email,
                    phone,
                    txn_id,
                    txn_time
                ))
                conn.commit()
        return {
            'statusCode': 200,
            'headers': {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type",
                "Access-Control-Allow-Methods": "POST,OPTIONS"
            },
            'body': json.dumps({
                'success': True,
                'message': 'Payment processed successfully',
                'user': email,
                'subscription': 'active'
            })
        }
    except Exception as e:
        logger.error(f"Payment processing error: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type",
                "Access-Control-Allow-Methods": "POST,OPTIONS"
            },
            'body': json.dumps({
                'success': False,
                'message': 'Internal server error during payment processing'
            })
        }
def verify_razorpay_payment(txn_id):
    """Verify payment with Razorpay API"""
    try:
        payment = razorpay_client.payment.fetch(txn_id)
        logger.info(f"Razorpay payment verification response: {payment}")
        # payment.get('status') == 'status'
        if(payment.get('status') == 'refunded'):
            with get_db_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute("""
                        UPDATE pricingcalculator
                        SET subscribed = false
                        WHERE txn_id = %s
                        RETURNING *
                    """, (txn_id,))
                conn.commit()
            return False
        else:
            return True
    except Exception as e:
        logger.error(f"Razorpay verification error: {str(e)}")
        return False 

def handle_status_check(body):
    """Check user subscription status"""
    email = body['email'].lower().strip()
    
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("""
                SELECT subscribed
                FROM pricingcalculator 
                WHERE email = %s
            """, (email,))
            user = cursor.fetchone()
    
    if not user:
        return {
            'statusCode': 404,
            'headers': {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type",
                "Access-Control-Allow-Methods": "POST,OPTIONS"
            },
            'body': json.dumps({
                'isSubscribed': False,
                # 'queryCount': 0,
                # 'uploadCount': 0,
                # 'remainingQueries': 6,  
                # 'remainingUploads': 3
            })
        }
    
    subscribed = user['subscribed']
    if subscribed:
        query_count = 20
        upload_count = 5
    else:
        query_count = 6
        upload_count = 3
    
    # Calculate remaining counts
    if subscribed:
        remaining_queries = max(0, 20 - query_count)  # limits for subscribed users
        remaining_uploads = max(0, 5 - upload_count)
    else:
        remaining_queries = max(0, 6 - query_count)  # Free tier
        remaining_uploads = max(0, 3 - upload_count)  
    
    return {
        'statusCode': 200,
        'headers': {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Allow-Methods": "POST,OPTIONS"
        },
        'body': json.dumps({
            'isSubscribed': subscribed,
            # 'queryCount': query_count,
            # 'uploadCount': upload_count,
            # 'remainingQueries': remaining_queries,
            # 'remainingUploads': remaining_uploads
        })
    }

def handle_counter_increment(body):
    """Increment usage counters with subscription check"""
    email = body['email'].lower().strip()
    counter_type = body['counterType']  # 'queryCount' or 'uploadCount'
    
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # First check user status
            cursor.execute("""
                SELECT subscribed
                FROM pricingcalculator 
                WHERE email = %s
            """, (email,))
            user = cursor.fetchone()
            
            if not user:
                return {
                    'statusCode': 404,
                    'headers': {
                        "Access-Control-Allow-Origin": "*",
                        "Access-Control-Allow-Headers": "Content-Type",
                        "Access-Control-Allow-Methods": "POST,OPTIONS"
                    },
                    'body': json.dumps({'success': False, 'message': 'User not found'})
                }
            
            # If user is subscribed more access unlocked
            if user['subscribed']:
                if counter_type == 'queryCount':
                    query_count = query_count + 1
                else:
                    upload_count = upload_count + 1
                return {
                    'statusCode': 200,
                    'headers': {
                        "Access-Control-Allow-Origin": "*",
                        "Access-Control-Allow-Headers": "Content-Type",
                        "Access-Control-Allow-Methods": "POST,OPTIONS"
                    },
                    'body': json.dumps({
                        'success': True,
                        'message': 'User is subscribed',
                        'queryCount': updated_counts['query_count'],
                        'uploadCount': updated_counts['upload_count'],
                    })
                }
            
            # For non-subscribed users, increment the counter
            if counter_type == 'queryCount':
                query_count = query_count + 1
            else:
                upload_count = upload_count + 1
    return {
        'statusCode': 200,
        'headers': {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Allow-Methods": "POST,OPTIONS"
        },
        # 'headers': {
        #     'Content-Type': 'application/json',
        #     'Access-Control-Allow-Origin': '*'
        # },
        'body': json.dumps({
            'success': True,
            'queryCount': updated_counts['query_count'],
            'uploadCount': updated_counts['upload_count']
        })
    }