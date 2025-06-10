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
        email = body.get("email")
        email = email.lower().strip() if email else None
        
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
        email = body.get("email")
        email = email.lower().strip() if email else None
        provider_user_id = body.get('provider_user_id', '') or None
        logger.info(f"Verifying user: {email}, {provider_user_id}")
    
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                # Check if user exists in oauth table
                if provider_user_id:
                    provider = 'linkedin'
                    # Check with provider user ID
                    cursor.execute("""
                        SELECT EXISTS(
                            SELECT 1 FROM public.bbt_oauthusers 
                            WHERE provider = %s AND provider_user_id = %s
                        ) AS user_exists
                    """, (provider, provider_user_id))
                else:
                    # Check with email
                    cursor.execute("""
                        SELECT EXISTS(
                            SELECT 1 FROM public.bbt_oauthusers 
                            WHERE LOWER(TRIM(email)) = %s
                        ) AS user_exists
                    """, (email,))
                result = cursor.fetchone()
                user_exists = result['user_exists'] if result else False
                logger.info(f"User data: {user_exists}")

                # Check if user already exists in pricingcalculator
                if provider_user_id:
                    # Check with provider user ID
                    cursor.execute("""
                        SELECT * FROM pricingcalculator 
                        WHERE provider_user_id = %s OR (provider_user_id IS NULL AND email = %s)
                        LIMIT 1
                    """, (provider_user_id, email))
                else:
                    # Check with email
                    cursor.execute("""
                        SELECT * FROM pricingcalculator 
                        WHERE email = %s AND (provider_user_id IS NULL OR provider_user_id = '')
                        LIMIT 1
                    """, (email,))
                user = cursor.fetchone()
                logger.info(f"User data: {user}")
                if not user:
                    # Insert new free-tier user with NULL provider_user_id if empty
                    provider_id = provider_user_id if provider_user_id else None
                    cursor.execute("""
                        INSERT INTO pricingcalculator (
                            email, provider_user_id, query_count, upload_count, subscribed
                        ) VALUES (%s, %s, 0, 0, false)
                        """, (email, provider_user_id))
                    conn.commit()
                    user = {'subscribed': False, 'query_count': 0, 'upload_count': 0}
            
                subscribed = user['subscribed']    
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
                'provider_user_id': provider_user_id,
                'isSubscribed': subscribed,
                'queryCount': user['query_count'],
                'uploadCount': user['upload_count'],
                'maxQueries': 20 if subscribed else 6,
                'maxUploads': 5 if subscribed else 3
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
        provider_user_id = body.get('provider_user_id', '')
        email = body['email'].lower().strip()
        name = body['name']
        phone = body['phone']
        txn_time = datetime.now()
        app_id = body['appId']
        order_id = body['paymentId']
    
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
                    INSERT INTO public.bbt_tempusers (
                        name, email, phone, app_id, order_id
                    ) VALUES (%s, %s, %s, %s, %s)
                    RETURNING *
                """, (
                    name,
                    email,
                    phone,
                    app_id,
                    order_id
                ))
                if provider_user_id:
                    # Check if the new email already exists in another row
                    cursor.execute("""
                        SELECT 1 FROM pricingcalculator
                        WHERE email = %s AND provider_user_id IS DISTINCT FROM %s
                    """, (email, provider_user_id))

                    email_exists = cursor.fetchone()

                    if email_exists:
                        # Just update other fields without changing the email
                        cursor.execute("""
                            UPDATE pricingcalculator
                            SET name = %s,
                                phone = %s,
                                txn_id = %s,
                                txn_time = %s,
                                subscribed = true,
                                query_count = 0,
                                upload_count = 0
                            WHERE provider_user_id = %s
                        """, (
                            name,
                            phone,
                            txn_id,
                            txn_time,
                            provider_user_id
                        ))
                    else:
                        # Safe to update email
                        cursor.execute("""
                            UPDATE pricingcalculator
                            SET email = %s,
                                name = %s,
                                phone = %s,
                                txn_id = %s,
                                txn_time = %s,
                                subscribed = true,
                                query_count = 0,
                                upload_count = 0
                            WHERE provider_user_id = %s
                        """, (
                            email,
                            name,
                            phone,
                            txn_id,
                            txn_time,
                            provider_user_id
                        ))
                else :
                    cursor.execute("""
                        UPDATE public.pricingcalculator
                            SET name = %s,
                            phone = %s,
                            txn_id = %s,
                            txn_time = %s,
                            subscribed = true,
                            query_count = 0,
                            upload_count = 0
                        WHERE email = %s
                        RETURNING *
                    """, (
                        name,
                        phone,
                        txn_id,
                        txn_time,
                        email
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
    email = body.get("email")
    email = email.lower().strip() if email else None
    provider_user_id = body.get('provider_user_id', '')
    logger.info(f"Checking subscription status for: {email}, {provider_user_id}")
    
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            if provider_user_id:
                cursor.execute("""
                    SELECT subscribed, query_count, upload_count, txn_time 
                    FROM pricingcalculator 
                    WHERE provider_user_id = %s
                """, (provider_user_id,))
            else:
                cursor.execute("""
                    SELECT subscribed, query_count, upload_count, txn_time 
                    FROM pricingcalculator 
                    WHERE email = %s
                """, (email,))
            user = cursor.fetchone()

            # Check if subscription has expired (24 hours after txn_time)
            if user and user['subscribed'] and user['txn_time']:
                subscription_time = user['txn_time']
                logger.info(f"subscription_time: {subscription_time}")
                current_time = datetime.now()
                logger.info(f"current_time: {current_time}")
                hours_elapsed = (current_time - subscription_time).total_seconds() / 3600
                logger.info(f"hours_elapsed: {hours_elapsed}")
                
                if hours_elapsed >= 24:
                    logger.info(f"Subscription Expired")
                    # Update subscription status to expired
                    if provider_user_id:
                        cursor.execute("""
                            UPDATE pricingcalculator
                            SET subscribed = false
                            WHERE provider_user_id = %s
                        """, (provider_user_id,))
                    else:
                        cursor.execute("""
                            UPDATE pricingcalculator
                            SET subscribed = false
                            WHERE email = %s
                        """, (email,))
                    conn.commit()
                    user['subscribed'] = False
                    logger.info(f"Subscription expired for user: {email}")
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
                'queryCount': 0,
                'uploadCount': 0,
                'maxQueries': 6,
                'maxUploads': 3
            })
        }
    subscribed = user['subscribed']
    query_count = user['query_count'] or 0
    upload_count = user['upload_count'] or 0
    max_queries = 20 if subscribed else 6
    max_uploads = 5 if subscribed else 3

    return {
        'statusCode': 200,
        'headers': {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Allow-Methods": "POST,OPTIONS"
        },
        'body': json.dumps({
            'isSubscribed': subscribed,
            'queryCount': query_count,
            'uploadCount': upload_count,
            'maxQueries': max_queries,
            'maxUploads': max_uploads,
            'remainingQueries': max_queries - query_count,
            'remainingUploads': max_uploads - upload_count
        })
    }

def handle_counter_increment(body):
    """Increment usage counters with subscription check"""
    email = body.get("email")
    email = email.lower().strip() if email else None
    provider_user_id = body.get('provider_user_id', '')
    counter_type = body['counterType']  # 'queryCount' or 'uploadCount'
    
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            if provider_user_id:
                cursor.execute("""
                    SELECT subscribed, query_count, upload_count 
                    FROM pricingcalculator 
                    WHERE provider_user_id = %s
                """, (provider_user_id,))
            else:
                cursor.execute("""
                    SELECT subscribed, query_count, upload_count 
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
            subscribed = user['subscribed']
            query_count = user['query_count'] or 0
            upload_count = user['upload_count'] or 0
            max_queries = 20 if subscribed else 6
            max_uploads = 5 if subscribed else 3

            if counter_type == 'queryCount':
                if query_count >= max_queries:
                    return {
                        'statusCode': 400,
                        'headers': {
                            "Access-Control-Allow-Origin": "*",
                            "Access-Control-Allow-Headers": "Content-Type",
                            "Access-Control-Allow-Methods": "POST,OPTIONS"
                        },
                        'body': json.dumps({'success': False, 'message': 'Query limit reached'})
                    } 
                query_count += 1
                if provider_user_id:
                    cursor.execute("""
                        UPDATE pricingcalculator
                        SET query_count = %s
                        WHERE provider_user_id = %s
                    """, (query_count, provider_user_id,))
                else:
                    cursor.execute("""
                        UPDATE pricingcalculator
                        SET query_count = %s
                        WHERE email = %s
                    """, (query_count, email,))
                conn.commit()
            elif counter_type == 'uploadCount':
                if upload_count >= max_uploads:
                    return {
                        'statusCode': 400,
                        'headers': {
                            "Access-Control-Allow-Origin": "*",
                            "Access-Control-Allow-Headers": "Content-Type",
                            "Access-Control-Allow-Methods": "POST,OPTIONS"
                        },
                        'body': json.dumps({'success': False, 'message': 'Upload limit reached'})
                    }
                upload_count += 1
                if provider_user_id:
                    cursor.execute("""
                        UPDATE pricingcalculator
                        SET upload_count = %s
                        WHERE provider_user_id = %s
                    """, (upload_count, provider_user_id,))
                else:
                    cursor.execute("""
                        UPDATE pricingcalculator
                        SET upload_count = %s
                        WHERE email = %s
                    """, (upload_count, email,))
                conn.commit()
            else:
                return {
                    'statusCode': 400,
                    'headers': {
                        "Access-Control-Allow-Origin": "*",
                        "Access-Control-Allow-Headers": "Content-Type",
                        "Access-Control-Allow-Methods": "POST,OPTIONS"
                    },
                    'body': json.dumps({'success': False, 'message': 'Invalid counterType'})
                }
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
                    'queryCount': query_count,
                    'uploadCount': upload_count,
                    'remainingQueries': max_queries - query_count,
                    'remainingUploads': max_uploads - upload_count
                })
            }
