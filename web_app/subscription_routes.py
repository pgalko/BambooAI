# subscription_routes.py - PAYG version (cleaned up)

from flask import Blueprint, request, jsonify, redirect
from auth import requires_auth, get_current_user_id
from datetime import datetime
import logging
try:
    import stripe
except ImportError:                                     # the self-hosted edition has no billing; the routes answer locally
    stripe = None
import os

if stripe is not None:
    stripe.api_key = os.getenv('STRIPE_SECRET_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
YOUR_DOMAIN = os.getenv('YOUR_DOMAIN')

# Import your billing functions
from auth.supabase_client import (
    set_user_subscription,
    get_user_subscription,
    get_balance,
    add_funds,
    get_user_llm_config,
    get_monthly_usage,
    get_tier_limits
)

# Import the config builder
from llm_config_builder import build_user_config

# Create Blueprint
subscription_bp = Blueprint('subscription', __name__, url_prefix='/api')

@subscription_bp.route('/subscription', methods=['GET'])
@requires_auth
def get_subscription():
    """Get user's current subscription with PAYG pricing info"""
    try:
        user_id = get_current_user_id()
        if not user_id:
            return jsonify({
                'data': {
                    'model_tier': 'free',
                    'compute_tier': 'free',
                    'integration_config': {},
                    'per_query_cost': 0.00,
                    'max_queries': 20,
                    'max_data_days': 14
                }
            }), 200
        
        result = get_user_subscription(user_id)
        
        if result.get('ok'):
            data = result.get('data')
            if data:
                # Ensure PAYG fields are included
                if 'per_query_cost' not in data:
                    data['per_query_cost'] = 0.00
                if 'integration_config' not in data or data['integration_config'] is None:
                    data['integration_config'] = {}
                
            return jsonify({'data': data}), 200
        else:
            return jsonify({'error': result.get('error', 'Failed to get subscription')}), 500
            
    except Exception as e:
        logging.error(f"Error getting subscription: {e}", exc_info=True)
        return jsonify({'error': f'Error getting subscription: {str(e)}'}), 500


@subscription_bp.route('/subscription', methods=['POST'])
@requires_auth
def save_subscription():
    try:
        user_id = get_current_user_id()
        if not user_id:
            return jsonify({'error': 'Not available in demo mode'}), 400
        
        data = request.json
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        model_tier = data.get('model_tier', 'free')
        compute_tier = data.get('compute_tier', 'free')
        integration_config = data.get('integration_config', {})
        
        result = set_user_subscription(
            auth0_id=user_id,
            model_tier=model_tier,
            compute_tier=compute_tier,
            integration_config=integration_config
        )
        
        if not result.get('ok'):
            return jsonify({'error': result.get('error', 'Failed to save subscription')}), 500
        
        # Force rebuild LLM config
        subscription_data = {
            'model_tier': model_tier,
            'compute_tier': compute_tier,
            'integration_config': integration_config
        }
        
        # Check for beta credit (Subsidised tier only)
        if model_tier == 'sub':
            balance_result = get_balance(user_id)
            if balance_result.get('ok') and balance_result.get('data', {}).get('balance', 0) == 0:
                # Add beta credit
                credit_result = add_funds(
                    auth0_id=user_id,
                    amount=10.00,
                    source='beta_credit',
                    reference='Beta testing credit',
                    idempotency_key=f'beta_credit_{user_id}'
                )
                
                if credit_result.get('ok'):
                    logging.info(f'Beta credit added for user {user_id}')
        
        # Get pricing info for response
        limits_result = get_tier_limits('compute')
        per_query_cost = 0.00
        
        if limits_result.get('ok'):
            for tier_info in limits_result.get('data', []):
                if tier_info['tier'] == compute_tier:
                    per_query_cost = float(tier_info.get('variable_rate', 0))
                    break
        
        # Add SweatStack cost if enabled
        if integration_config.get('sweatstack_extended'):
            per_query_cost += 0.01
        
        return jsonify({
            'message': 'Subscription saved successfully',
            'model_tier': model_tier,
            'compute_tier': compute_tier,
            'per_query_cost': per_query_cost,
            'integration_config': integration_config
        }), 200
            
    except Exception as e:
        logging.error(f"Error saving subscription: {e}", exc_info=True)
        return jsonify({'error': f'Error saving subscription: {str(e)}'}), 500


@subscription_bp.route('/monthly-usage', methods=['GET'])
@requires_auth
def get_monthly_usage_endpoint():
    """Get current anniversary period usage"""
    try:
        user_id = get_current_user_id()
        if not user_id:
            return jsonify({'data': {'queries_used': 0, 'max_queries': 20}}), 200
        
        result = get_monthly_usage(user_id)
        
        if result.get('ok'):
            return jsonify({'data': result.get('data', {})}), 200
        else:
            return jsonify({'error': result.get('error', 'Failed to get usage')}), 500
            
    except Exception as e:
        logging.error(f"Error getting usage: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@subscription_bp.route('/tier-limits', methods=['GET'])
@requires_auth  
def get_tier_limits_endpoint():
    """Get tier pricing and limits for UI display"""
    try:
        category = request.args.get('category', 'compute')
        result = get_tier_limits(category)
        
        if result.get('ok'):
            # Format data for frontend
            tiers = {}
            for tier_data in result.get('data', []):
                tier_name = tier_data['tier']
                tiers[tier_name] = {
                    'per_query_cost': float(tier_data.get('variable_rate', 0)),
                    'max_queries': tier_data.get('max_queries'),
                    'max_data_days': tier_data.get('max_data_days')
                }
            
            return jsonify({'data': tiers}), 200
        else:
            return jsonify({'error': result.get('error', 'Failed to get tier limits')}), 500
            
    except Exception as e:
        logging.error(f"Error getting tier limits: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@subscription_bp.route('/balance', methods=['GET'])
@requires_auth
def get_user_balance():
    """Get user's current account balance"""
    try:
        user_id = get_current_user_id()
        if not user_id:
            return jsonify({'data': {'balance': 0, 'last_updated': None}}), 200
        
        result = get_balance(user_id)
        
        if result.get('ok'):
            return jsonify({'data': result.get('data')}), 200
        else:
            return jsonify({'error': result.get('error', 'Failed to get balance')}), 500
            
    except Exception as e:
        return jsonify({'error': f'Error getting balance: {str(e)}'}), 500
    
### Stripe Payments ###

@subscription_bp.route('/payment-success')
def payment_success():
    """Handle successful payment return"""
    # Simply redirect to main app with success message
    return redirect('/?payment=success')

@subscription_bp.route('/payment-cancelled')
def payment_cancelled():
    """Handle cancelled payment"""
    # Redirect to main app with cancelled message
    return redirect('/?payment=cancelled')

@subscription_bp.route('/create-checkout-session', methods=['POST'])
@requires_auth
def create_checkout_session():
    """Create Stripe checkout session for adding funds"""
    try:
        user_id = get_current_user_id()
        if not user_id:
            return jsonify({'error': 'Not available in demo mode'}), 400
        
        data = request.json
        amount = data.get('amount', 10)  # Default $10
        
        # Enforce minimum
        if amount < 10:
            return jsonify({'error': 'Minimum amount is $10'}), 400
        
        # Create Stripe checkout session
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {
                        'name': 'Account Credit',
                        'description': f'Add ${amount:.2f} USD to your account'
                    },
                    'unit_amount': int(amount * 100),  # Convert to cents
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=f"{YOUR_DOMAIN}/api/payment-success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{YOUR_DOMAIN}/api/payment-cancelled",
            metadata={
                'auth0_id': user_id,
                'amount': str(amount)
            }
        )
        
        return jsonify({'checkout_url': session.url}), 200
        
    except Exception as e:
        logging.error(f"Error creating checkout session: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@subscription_bp.route('/stripe-webhook', methods=['POST'])
def stripe_webhook():
    """Handle Stripe webhook events"""
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get('Stripe-Signature')
    
    try:
        # Verify webhook signature
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        logging.error("Invalid payload")
        return jsonify({'error': 'Invalid payload'}), 400
    except stripe.error.SignatureVerificationError:
        logging.error("Invalid signature")
        return jsonify({'error': 'Invalid signature'}), 400
    
    # Handle the checkout.session.completed event
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        
        # Get metadata
        auth0_id = session['metadata']['auth0_id']
        amount = float(session['amount_total'] / 100)  # Convert from cents
        
        # Add funds using your existing function
        result = add_funds(
            auth0_id=auth0_id,
            amount=amount,
            source='stripe',
            reference=session['id'],
            idempotency_key=session['payment_intent'],
            skip_validation=True  # Skip validation for webhooks
        )
        
        if result.get('ok'):
            logging.info(f"Successfully credited ${amount} to user {auth0_id}")
        else:
            logging.error(f"Failed to credit funds: {result.get('error')}")
    
    return jsonify({'received': True}), 200
