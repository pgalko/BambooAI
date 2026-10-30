-- Usage records kept whole (2026-10-31, the Usage dialog rebuilt - docs/USAGE_DESIGN.md; patch 0255).
-- Run once in the Supabase SQL editor of each hosted project BEFORE the app with 0255 is started there; safe to
-- run again. The self-hosted edition needs nothing: its SQLite file upgrades itself on the first start.
--
-- Each model call's row gains what the logger computes at the call and had only written to the JSON run log: the
-- prompt tokens served from cache and written to it, what the cache saved against an uncached prompt (negative on a
-- write-heavy turn), and the search and image fees inside the cost. Rows from before stay NULL there: the dialog
-- reads NULL as "not recorded", never as zero.

alter table public.usage add column if not exists cached_tokens integer;
alter table public.usage add column if not exists cache_write_tokens integer;
alter table public.usage add column if not exists cache_savings double precision;
alter table public.usage add column if not exists search_fee double precision;
alter table public.usage add column if not exists image_fee double precision;

-- the writer: the same function, the five fields taken from the payload when it carries them (an older app's
-- payload does not: its rows stay NULL there, as rows from before do). Replacing keeps the function's owner and grants.
create or replace function public.insert_usage_with_chain(p_usage_data jsonb, p_thread_id text) returns jsonb
    language plpgsql
    as $$
DECLARE
    v_thread_record RECORD;
    v_chain_record RECORD;
    v_usage_record RECORD;
    v_bamboo_user_id TEXT;
    v_chain_id TEXT;
BEGIN
    -- Extract required fields
    v_bamboo_user_id := p_usage_data->>'bamboo_user_id';
    v_chain_id := p_usage_data->>'chain_id';

    -- Validate inputs
    IF v_bamboo_user_id IS NULL OR v_chain_id IS NULL OR p_thread_id IS NULL THEN
        RETURN jsonb_build_object('success', false, 'error', 'missing_required_fields');
    END IF;

    -- Step 1: Create or get thread
    SELECT * INTO v_thread_record
    FROM threads
    WHERE thread_id = p_thread_id
    LIMIT 1;

    IF NOT FOUND THEN
        INSERT INTO threads (thread_id, bamboo_user_id)
        VALUES (p_thread_id, v_bamboo_user_id)
        RETURNING * INTO v_thread_record;
    END IF;

    -- Step 2: Create chain if it doesn't exist
    SELECT * INTO v_chain_record
    FROM chains
    WHERE chain_id = v_chain_id
    LIMIT 1;

    IF NOT FOUND THEN
        INSERT INTO chains (chain_id, thread_id, bamboo_user_id)
        VALUES (v_chain_id, v_thread_record.id, v_bamboo_user_id)
        RETURNING * INTO v_chain_record;
    END IF;

    -- Step 3: Insert usage record (the cache split, the savings and the fees since 2026-10-31; NULL when the payload has none)
    INSERT INTO usage (
        bamboo_user_id,
        agent,
        chain_id,
        timestamp,
        model,
        prompt_tokens,
        completion_tokens,
        elapsed_time,
        tokens_per_second,
        cost,
        cached_tokens,
        cache_write_tokens,
        cache_savings,
        search_fee,
        image_fee
    )
    VALUES (
        v_bamboo_user_id,
        p_usage_data->>'agent',
        v_chain_id,
        (p_usage_data->>'timestamp')::timestamp,
        p_usage_data->>'model',
        (p_usage_data->>'prompt_tokens')::integer,
        (p_usage_data->>'completion_tokens')::integer,
        (p_usage_data->>'elapsed_time')::double precision,
        (p_usage_data->>'tokens_per_second')::double precision,
        (p_usage_data->>'cost')::double precision,
        (p_usage_data->>'cached_tokens')::integer,
        (p_usage_data->>'cache_write_tokens')::integer,
        (p_usage_data->>'cache_savings')::double precision,
        (p_usage_data->>'search_fee')::double precision,
        (p_usage_data->>'image_fee')::double precision
    )
    RETURNING * INTO v_usage_record;

    -- Return JSONB structure
    RETURN jsonb_build_object(
        'success', true,
        'usage_id', v_usage_record.id,
        'chain_id', v_chain_id,
        'thread_id', p_thread_id,
        'message', 'Usage record inserted successfully'
    );

EXCEPTION
    WHEN OTHERS THEN
        -- Return error as JSONB instead of raising exception
        RETURN jsonb_build_object(
            'success', false,
            'error', SQLERRM
        );
END;
$$;

-- what it looks like after: the five columns on the table, and the function writing them
select column_name, data_type from information_schema.columns where table_schema = 'public' and table_name = 'usage'
  and column_name in ('cached_tokens', 'cache_write_tokens', 'cache_savings', 'search_fee', 'image_fee') order by column_name;
select proname, (prosrc like '%cache_savings%') as writes_the_cache_fields from pg_proc where proname = 'insert_usage_with_chain';
