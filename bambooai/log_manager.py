import json
import time
from json import JSONEncoder
import logging
from logging.handlers import RotatingFileHandler
import os
import threading
from typing import Optional

logger = logging.getLogger(__name__)


class FlexibleJSONEncoder(JSONEncoder):
    def default(self, obj):
        if hasattr(obj, '__dict__'):
            return self.serialize_custom_object(obj)
        elif isinstance(obj, dict):
            return {k: self.default(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self.default(item) for item in obj]
        return super().default(obj)

    def serialize_custom_object(self, obj):
        obj_dict = obj.__dict__.copy()
        obj_dict['__custom_class__'] = obj.__class__.__name__
        return obj_dict


class LogAndCallManager:
    def __init__(self, token_cost_dict, user_id: str = None, thread_id: str = None):
        self._lock = threading.RLock()  # Reentrant lock for thread safety
        self.token_summary = {}
        self.token_cost_dict = token_cost_dict
        self.user_id = user_id
        self.thread_id = thread_id

        self.log_dir = os.path.join('logs', self.user_id) if self.user_id else 'logs'
        os.makedirs(self.log_dir, exist_ok=True)

        self.run_log_file_path = os.path.join(self.log_dir, 'bambooai_run_log.json')
        self.consolidated_log_file_path = os.path.join(self.log_dir, 'consolidated_logs.json')

        self.logger = logging.getLogger(f'bambooai_json_logger_{self.user_id}')
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False

        for handler in list(self.logger.handlers):
            self.logger.removeHandler(handler)

        handler = RotatingFileHandler(self.consolidated_log_file_path, maxBytes=5*1024*1024, backupCount=3)
        self.logger.addHandler(handler)
        
        # Initialize Supabase client if AUTH_MODE is auth0
        self.supabase_client = None
        if os.getenv('AUTH_MODE') == 'auth0':
            try:
                from bambooai.db.supabase_client import SupabaseClient
                self.supabase_client = SupabaseClient()
            except ImportError as e:
                logging.warning(f"Failed to import SupabaseClient: {e}")
            except Exception as e:
                logging.warning(f"Failed to initialize SupabaseClient: {e}")
        
    def update_token_summary(self, chain_id, prompt_tokens, completion_tokens, total_tokens, elapsed_time, cost, grounding_cost=0.0, image_cost=0.0, cached_tokens=0, cache_write_tokens=0, cache_savings=0.0):
        """Update token summary with separate tracking for grounding, image and
        prompt-cache costs.

        cache_savings is what the uncached prompt WOULD have cost minus what it
        actually did, net of the write premium. Without it the benefit of
        caching is invisible in the UI and impossible to reason about."""
        with self._lock:
            if chain_id not in self.token_summary:
                self.token_summary[chain_id] = {
                    'prompt_tokens': 0, 
                    'completion_tokens': 0, 
                    'total_tokens': 0, 
                    'elapsed_time': 0,
                    'total_cost': 0,
                    'web_search_cost': 0,
                    'image_cost': 0,
                    'cached_tokens': 0,
                    'cache_write_tokens': 0,
                    'cache_savings': 0
                }
            
            self.token_summary[chain_id]['prompt_tokens'] += prompt_tokens
            self.token_summary[chain_id]['completion_tokens'] += completion_tokens
            self.token_summary[chain_id]['total_tokens'] += total_tokens
            self.token_summary[chain_id]['elapsed_time'] += elapsed_time
            self.token_summary[chain_id]['total_cost'] += cost
            self.token_summary[chain_id]['web_search_cost'] += grounding_cost
            self.token_summary[chain_id]['image_cost'] += image_cost
            self.token_summary[chain_id]['cached_tokens'] += cached_tokens
            self.token_summary[chain_id]['cache_write_tokens'] += cache_write_tokens
            self.token_summary[chain_id]['cache_savings'] += cache_savings

    def print_summary_to_terminal(self, output_manager):
        """Print summary including web search and image costs"""
        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0
        elapsed_time = 0
        total_cost = 0
        web_search_cost = 0
        image_cost = 0

        cached_tokens = 0
        cache_savings = 0.0
        for chain_id, tokens in self.token_summary.items():
            prompt_tokens += tokens['prompt_tokens']
            completion_tokens += tokens['completion_tokens']
            total_tokens += tokens['total_tokens']
            elapsed_time += tokens['elapsed_time']
            total_cost += tokens['total_cost']
            web_search_cost += tokens.get('web_search_cost', 0)
            image_cost += tokens.get('image_cost', 0)
            cached_tokens += tokens.get('cached_tokens', 0)
            cache_savings += tokens.get('cache_savings', 0)

        avg_speed = completion_tokens / elapsed_time if elapsed_time > 0 else 0

        summary_text = ""
        summary_text += f"Chain ID: {chain_id}\n"
        summary_text += f"Total Prompt Tokens: {prompt_tokens}\n"
        summary_text += f"Total Completion Tokens: {completion_tokens}\n"
        summary_text += f"Total Tokens: {total_tokens}\n"
        summary_text += f"Total Time (LLM Interact.): {elapsed_time:.2f} seconds\n"
        summary_text += f"Average Response Speed: {avg_speed:.2f} tokens/second\n"
        # CACHE VISIBILITY. The append-only Investigator history is designed
        # to cache; the F1 run measured only a 20% hit ratio on it, most
        # likely because OpenRouter re-routes across upstream hosts and
        # implicit caches are per-host. The ratio was invisible outside the
        # raw run log, so the OPENROUTER_PROVIDER_ORDER experiment could not
        # be judged from the journal. Now every chain summary states it.
        cache_ratio = (100.0 * cached_tokens / prompt_tokens) if prompt_tokens else 0.0
        summary_text += f"Cached Prompt Tokens: {cached_tokens} ({cache_ratio:.0f}% of prompt)\n"
        summary_text += f"Prompt Cache Savings: ${cache_savings:.4f}\n"
        summary_text += f"Web Search Cost: ${web_search_cost:.4f}\n"
        summary_text += f"Image Generation Cost: ${image_cost:.4f}\n"
        summary_text += f"Total Cost: ${total_cost:.4f}\n"

        output_manager.display_call_summary(summary_text)

    def _write_to_database(self, agent, chain_id, timestamp, model, prompt_tokens, 
                          completion_tokens, elapsed_time, tokens_per_second, cost):
        """Write usage data to Supabase database with chain/thread support"""
        if not self.supabase_client or not self.supabase_client.is_available():
            return False
        
        if not self.thread_id:
            print(f"thread_id is required but not available for chain_id: {chain_id}")
            return False
        
        usage_data = {
            'bamboo_user_id': self.user_id,
            'agent': agent,
            'chain_id': chain_id,
            'timestamp': timestamp,
            'model': model,
            'prompt_tokens': prompt_tokens,
            'completion_tokens': completion_tokens,
            'elapsed_time': round(elapsed_time, 4),
            'tokens_per_second': round(tokens_per_second, 4),
            'cost': round(cost, 4)
        }
        
        # Use the new method that handles chain/thread creation
        return self.supabase_client.insert_usage_with_chain(usage_data, self.thread_id)
    
    def charge_for_completed_query(self, chain_id: str) -> bool:
        """
        Charge for a completed query (call this after all usage records are written)

        AT MOST ONCE PER CHAIN. Two call sites can legitimately reach this for
        the same chain - _process_question's finally settles it when the query
        ends, and cleanup() settles self.chain_id again when the instance is
        torn down - and a production log showed two "Charged query completion"
        lines per round, including for a chain that produced nothing. Whether
        the Supabase RPC dedupes is its own business; the duplicate CALL is
        suppressed here, and LOGGED, so the journal now names the phase that
        re-fired instead of silently absorbing it.
        """
        if not self.supabase_client or not self.supabase_client.is_available():
            return True
        if not self.user_id or not chain_id:
            return True
        with self._lock:
            already = getattr(self, '_settled_chains', None)
            if already is None:
                already = self._settled_chains = set()
            if chain_id in already:
                logging.info("Chain %s is already settled; suppressing a "
                             "duplicate charge call.", chain_id)
                return True
            already.add(chain_id)
        try:
            result = self.supabase_client.charge_query_completion(
                bamboo_user_id=self.user_id,
                chain_id=chain_id
            )
            if result.get('ok'):
                return True
            else:
                # The charge did not go through; let a later phase try again.
                with self._lock:
                    self._settled_chains.discard(chain_id)
                return False
        except Exception:
            with self._lock:
                self._settled_chains.discard(chain_id)
            return False  # Do not break flow

    def write_to_log(self, agent, chain_id, timestamp, model, messages, content,
                    prompt_tokens, completion_tokens, total_tokens, elapsed_time, tokens_per_second,
                    cached_tokens=0, cache_write_tokens=0, call_meta=None):
        """
        Compute total cost = token_cost + (optional) grounding per-request fee.
        The grounding fee is inferred from a __billing_meta__ sidecar inside messages
        and configured per model via token_cost_dict[model]['grounding_search_request'].
        """
        # --- Extract optional billing meta from messages (non-breaking) ---
        search_billed = 0
        images_generated = 0
        try:
            if isinstance(messages, list):
                for m in messages:
                    if isinstance(m, dict) and m.get('role') == 'system':
                        c = m.get('content', '')
                        if isinstance(c, str) and c.startswith('__billing_meta__:'):
                            meta_json = c.split('__billing_meta__:', 1)[1].strip()
                            meta = json.loads(meta_json)
                            search_billed = int(meta.get('search_billed', 0))
                            images_generated = int(meta.get('images_generated', 0))
                            break
        except Exception:
            search_billed = 0
            images_generated = 0

        # --- Strip the sidecar so it doesn't appear in file logs ---
        def _strip_billing_meta(msgs):
            if not isinstance(msgs, list):
                return msgs
            return [
                m for m in msgs
                if not (
                    isinstance(m, dict)
                    and m.get('role') == 'system'
                    and isinstance(m.get('content', ''), str)
                    and m['content'].startswith('__billing_meta__:')
                )
            ]
        messages_clean = _strip_billing_meta(messages)

        # Token costs.
        #
        # prompt_tokens is the TOTAL input, cached portions included - the
        # providers normalise that before calling here (Anthropic reports
        # input_tokens excluding cache, OpenAI reports it including cache).
        # Three tranches are priced separately:
        #
        #   uncached  full rate
        #   cached    a read discount (Anthropic 0.1x; overridable per model)
        #   written   a write premium (Anthropic 1.25x; overridable per model)
        #
        # Getting this wrong is silent: bill reads at the full rate and caching
        # shows no saving, ignore the write premium and long runs under-bill.
        token_costs = self.token_cost_dict.get(model, {})
        prompt_token_cost = token_costs.get('prompt_tokens', 0.0)
        completion_token_cost = token_costs.get('completion_tokens', 0.0)
        cache_read_cost = token_costs.get('cache_read_tokens', prompt_token_cost * 0.1)
        cache_write_cost = token_costs.get('cache_write_tokens', prompt_token_cost * 1.25)

        cached_tokens = max(0, int(cached_tokens or 0))
        cache_write_tokens = max(0, int(cache_write_tokens or 0))
        uncached_tokens = max(0, prompt_tokens - cached_tokens - cache_write_tokens)

        token_cost = (
            (uncached_tokens * prompt_token_cost) / 1000.0
            + (cached_tokens * cache_read_cost) / 1000.0
            + (cache_write_tokens * cache_write_cost) / 1000.0
            + (completion_tokens * completion_token_cost) / 1000.0
        )

        # What the same prompt would have cost with no cache, minus what it did.
        # Negative on a write-heavy turn, which is correct and worth seeing.
        cache_savings = (
            ((cached_tokens + cache_write_tokens) * prompt_token_cost) / 1000.0
            - ((cached_tokens * cache_read_cost) / 1000.0
               + (cache_write_tokens * cache_write_cost) / 1000.0)
        )

        # Grounding fee with quota check
        grounding_fee = 0.0
        per_request_fee = token_costs.get('grounding_search_request', 0.0)

        if search_billed and per_request_fee:
            if self.supabase_client and self.supabase_client.is_available():
                quota_result = self.supabase_client.check_grounding_search_quota(search_billed)
                if quota_result:
                    if quota_result.get('should_charge', True):
                        grounding_fee = float(per_request_fee) * search_billed
                else:
                    grounding_fee = float(per_request_fee) * search_billed
            else:
                grounding_fee = float(per_request_fee) * search_billed

        # Image output fee (follows grounding pattern)
        image_fee = 0.0
        per_image_fee = token_costs.get('per_image_output', 0.0)
        if images_generated and per_image_fee:
            image_fee = float(per_image_fee) * images_generated

        cost = token_cost + grounding_fee + image_fee  
        
        # Thread-safe: update in-memory summary (RLock allows re-entrant call)
        self.update_token_summary(chain_id, prompt_tokens, completion_tokens, total_tokens, 
                                elapsed_time, cost, grounding_fee, image_fee,
                                cached_tokens, cache_write_tokens, cache_savings)
        
        # DB write with thread_id check
        if os.getenv('AUTH_MODE') == 'auth0' and self.user_id:
            if not self.thread_id:
                print(f"thread_id not available, skipping DB write for chain: {chain_id}")
            else:
                self._write_to_database(agent, chain_id, timestamp, model, prompt_tokens, 
                                    completion_tokens, elapsed_time, tokens_per_second, cost)

        # Build log entry outside the lock (no shared state)
        json_entry = {
            # What the request was CONFIGURED with, first so it reads before the
            # numbers it explains. Absent from entries written before this
            # existed, so anything reading this file must tolerate that.
            **(call_meta or {}),
            'agent': agent,
            'chain_id': chain_id,
            'timestamp': timestamp,
            'model': model,
            'messages': messages_clean,
            'content': content,
            'prompt_tokens': prompt_tokens,
            'completion_tokens': completion_tokens,
            'total_tokens': total_tokens,
            'elapsed_time': elapsed_time,
            'tokens_per_second': tokens_per_second,
            'cost': cost,
            'cached_tokens': cached_tokens,
            'cache_write_tokens': cache_write_tokens,
            'cache_savings': cache_savings,
            'grounding_requests': search_billed,
            'grounding_fee': grounding_fee,
            'images_generated': images_generated,
            'image_fee': image_fee,
        }

        # Thread-safe: atomic read-modify-write on log file
        with self._lock: # Lock to ensure only one thread writes to the log file at a time
            try:
                with open(self.run_log_file_path, 'r') as json_file:
                    file_content = json_file.read()
                    existing_json_logs = json.loads(file_content) if file_content.strip() else []
                if not isinstance(existing_json_logs, list):
                    raise ValueError("run log is not a list")
            except FileNotFoundError:
                existing_json_logs = []
            except (json.JSONDecodeError, UnicodeDecodeError, ValueError, OSError) as exc:
                aside = self.run_log_file_path + time.strftime('.corrupt-%Y%m%d-%H%M%S')
                try:
                    os.replace(self.run_log_file_path, aside)
                except OSError:
                    pass
                logger.warning("Run log unreadable (%s); set aside as %s and starting fresh", exc, aside)
                existing_json_logs = []

            existing_json_logs.append(json_entry)

            with open(self.run_log_file_path, 'w') as json_file:
                json.dump(existing_json_logs, json_file, indent=2, cls=FlexibleJSONEncoder)

    def consolidate_logs(self):     
        # Read current run logs
        if os.path.exists(self.run_log_file_path):
            with open(self.run_log_file_path, 'r') as json_file:
                existing_json_logs = json.load(json_file)
        else:
            existing_json_logs = []
        
        # Read existing consolidated. A corrupt or unreadable file is set aside
        # (renamed) rather than allowed to fail every reset (2026-09-05: an
        # 829 MB consolidated log with an invalid control character made
        # /new_conversation return 500).
        consolidated_logs = {}
        if os.path.exists(self.consolidated_log_file_path):
            try:
                with open(self.consolidated_log_file_path, 'r') as json_file:
                    file_content = json_file.read()
                    if file_content.strip():
                        consolidated_logs = json.loads(file_content)
            except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
                aside = self.consolidated_log_file_path + time.strftime('.corrupt-%Y%m%d-%H%M%S')
                try:
                    os.replace(self.consolidated_log_file_path, aside)
                except OSError:
                    pass
                logger.warning("Consolidated log unreadable (%s); set aside as %s and starting fresh", exc, aside)
                consolidated_logs = {}
        
        # Merge
        for entry in existing_json_logs:
            chain_id = entry['chain_id']
            model = entry['model']
            
            if chain_id not in consolidated_logs:
                consolidated_logs[chain_id] = {
                    'chain_details': [],
                    'chain_summary': {},
                    'summary_per_model': {}
                }
            
            if model not in consolidated_logs[chain_id]['summary_per_model']:
                consolidated_logs[chain_id]['summary_per_model'][model] = {
                    'LLM Calls': 0,
                    'Prompt Tokens': 0,
                    'Completion Tokens': 0,
                    'Total Tokens': 0,
                    'Total Time': 0, 
                    'Tokens per Second': 0,
                    'Total Cost': 0
                }
            
            consolidated_logs[chain_id]['chain_details'].append(entry)
            consolidated_logs[chain_id]['summary_per_model'][model]['LLM Calls'] += 1
            consolidated_logs[chain_id]['summary_per_model'][model]['Prompt Tokens'] += entry['prompt_tokens']
            consolidated_logs[chain_id]['summary_per_model'][model]['Completion Tokens'] += entry['completion_tokens']
            consolidated_logs[chain_id]['summary_per_model'][model]['Total Tokens'] += entry['total_tokens']
            consolidated_logs[chain_id]['summary_per_model'][model]['Total Time'] += entry['elapsed_time']
            consolidated_logs[chain_id]['summary_per_model'][model]['Tokens per Second'] = round(
                consolidated_logs[chain_id]['summary_per_model'][model]['Completion Tokens'] /
                max(consolidated_logs[chain_id]['summary_per_model'][model]['Total Time'], 1e-9), 2)
            consolidated_logs[chain_id]['summary_per_model'][model]['Total Cost'] += entry['cost']
            
        # Update chain summaries
        for chain_id, summary_data in self.token_summary.items():
            if chain_id in consolidated_logs:
                summary = {}
                summary['Total LLM Calls'] = len(consolidated_logs[chain_id]['chain_details'])
                summary['Prompt Tokens'] = summary_data['prompt_tokens']
                summary['Completion Tokens'] = summary_data['completion_tokens']
                summary['Total Tokens'] = summary_data['total_tokens']
                summary['Total Time'] = round(summary_data['elapsed_time'], 2)
                summary['Tokens per Second'] = round(
                    summary_data['completion_tokens'] / max(summary_data['elapsed_time'], 1e-9), 2)
                summary['Total Cost'] = round(summary_data['total_cost'], 4)
                
                consolidated_logs[chain_id]['chain_summary'] = summary
        
        with open(self.consolidated_log_file_path, 'w') as json_file:
            json.dump(consolidated_logs, json_file, indent=2, cls=FlexibleJSONEncoder)

    def clear_run_logs(self):
        self.token_summary.clear()
        with open(self.run_log_file_path, 'w') as json_file:
            json.dump([], json_file, indent=2, cls=FlexibleJSONEncoder)