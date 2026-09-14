"""
Enhanced LLM Configuration Builder with Subscription Tier Support
Builds user configs based on template, subscription tier, and available API keys.
"""
import json
import os

from logger_config import get_logger
logger = get_logger(__name__)


def build_user_config(user_id: str, api_keys: dict = None, subscription_data: dict = None, model_preference: str = 'cost', force_rebuild: bool = False) -> bool:
    """
    Build user-specific LLM configuration from template based on subscription tier and API keys.
    
    Args:
        user_id: User identifier (truncated version for filesystem)
        api_keys: Dict of provider->bool mappings (for 'managed' tier)
        subscription_data: Dict with model_tier, compute_tier, data_tier
        model_preference: 'cost', 'performance' or 'max' for managed tier
        force_rebuild: Force rebuild even if file exists
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Ensure we're using the truncated user_id (remove 'auth0|' prefix if present)
        if '|' in user_id:
            user_id = user_id.split('|')[1]
        
        template_path = "LLM_CONFIG_template.json"
        user_config_path = os.path.join("config", user_id, "LLM_CONFIG.json")
        
        # Skip if file exists and not forcing rebuild
        if not force_rebuild and os.path.exists(user_config_path):
            return True
            
        # Load template
        if not os.path.exists(template_path):
            return False
            
        with open(template_path, 'r') as f:
            template = json.load(f)
        
        # Determine model tier (default to 'free' if not provided)
        model_tier = 'free'
        if subscription_data:
            model_tier = subscription_data.get('model_tier', 'free')
        
        # Build agent configs based on tier
        agent_configs = []
        effective_tier = 'free'
        
        if model_tier == 'free':
            # ALWAYS use default Groq configurations from template for free tier
            agent_configs = template.get('free_agent_configs', []).copy()
            logger.info(f"Using FREE tier config with Groq models for user {user_id}")
            
        elif model_tier == 'managed':
            # Handle managed tier based on preference
            if model_preference == 'performance':
                agent_configs = template.get('performance_agent_configs', []).copy()
                effective_tier = 'performance'
            elif model_preference == 'max':
                agent_configs = template.get('max_agent_configs', []).copy()
                effective_tier = 'max'
            else:  # Default to 'cost'
                agent_configs = template.get('cost_agent_configs', []).copy()
                effective_tier = 'cost'
            
        elif model_tier == 'sub':
            agent_configs = template.get('cost_agent_configs', []).copy()
            effective_tier = 'cost'
        else:
            # Default fallback to free tier (Groq)
            agent_configs = template.get('free_agent_configs', [])
            logger.info(f"Fallback to FREE tier config for user {user_id}")
        
        # Tier budgets (flattened): the investigation loop's reasoning room
        # is a tier attribute of the template. An absent block or key falls
        # back to the historical 8/3, so hand-maintained live configs keep
        # working untouched until the keys are added.
        tier_props = template.get('tier_properties', {}).get(effective_tier, {})

        # Create the final config. TIER KNOBS PASS THROUGH GENERICALLY
        # (2026-08-18): this dict used to copy tier_properties by
        # explicit name ("ONLY the necessary keys"), which silently
        # dropped every knob added to the template afterwards - the
        # four adaptive_* budget keys shipped for the delve runner
        # never reached the built user config, and the runner fell
        # back to its module defaults (Log_21 ran 30/9 despite the
        # raised template). Every key in the selected tier's
        # properties now lands flattened in the built config, exactly
        # as the two originals always did; the legacy pair keeps its
        # historical 8/3 fallback so a template without the block
        # still builds an unchanged config; and reserved top-level
        # keys can never be shadowed by a tier property.
        final_config = {
            'agent_configs': agent_configs,
            'model_properties': template.get('model_properties', {}),
            'user_tier': model_tier,
            'model_preference': model_preference,
        }
        tier_knobs = {k: v for k, v in tier_props.items()
                      if k not in final_config}
        tier_knobs.setdefault('analyst_turns_quick', 2)
        tier_knobs.setdefault('analyst_turns_deep', 15)
        tier_knobs.setdefault('analyst_turns_adaptive', 50)
        final_config.update(tier_knobs)
        
        # Write config file
        os.makedirs(os.path.dirname(user_config_path), exist_ok=True)
        with open(user_config_path, 'w') as f:
            json.dump(final_config, f, indent=2)
            
        logger.info(f"Successfully built LLM config for user {user_id} with {len(agent_configs)} agents")
        return True
        
    except Exception as e:
        logger.error(f"Error building config for user {user_id}: {str(e)}")
        return False

def needs_rebuild(user_id: str) -> bool:
    """Check if user config needs rebuilding (template newer than user config)."""
    try:
        template_path = "LLM_CONFIG_template.json"
        user_config_path = os.path.join("config", user_id, "LLM_CONFIG.json")
        
        if not os.path.exists(user_config_path):
            return True
            
        template_time = os.path.getmtime(template_path)
        user_config_time = os.path.getmtime(user_config_path)

        # Print if template needs a rebuild
        if template_time > user_config_time:
            logger.info(f"Template is newer than user config for user {user_id}, rebuild needed.")
            
        return template_time > user_config_time
        
    except Exception:
        return True