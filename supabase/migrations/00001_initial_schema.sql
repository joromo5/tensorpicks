-- ============================================================================
-- TensorPicks SaaS Platform — Initial Schema
-- ============================================================================
-- Auth: Clerk (external). Supabase used as database only.
-- RLS policies use a custom auth.uid() that reads the Clerk user ID from
-- the JWT sub claim set via Supabase's request.jwt.claims.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 0. Helper: extract Clerk user_id from JWT for RLS
-- ----------------------------------------------------------------------------
-- When calling Supabase from the backend, set the JWT claims via:
--   SET LOCAL request.jwt.claims = '{"sub": "user_xxx"}';
-- This lets RLS policies work without Supabase Auth.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION auth.uid() RETURNS TEXT AS $$
  SELECT coalesce(
    current_setting('request.jwt.claims', true)::json->>'sub',
    ''
  );
$$ LANGUAGE sql STABLE;

-- ----------------------------------------------------------------------------
-- 1. user_profiles
-- ----------------------------------------------------------------------------
CREATE TABLE user_profiles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  clerk_user_id TEXT UNIQUE NOT NULL,
  email TEXT,
  display_name TEXT,
  avatar_url TEXT,
  stripe_customer_id TEXT,
  plan TEXT NOT NULL DEFAULT 'free'
    CHECK (plan IN ('free', 'starter', 'pro', 'agency')),
  max_agents INTEGER NOT NULL DEFAULT 1,
  max_runs_per_day INTEGER NOT NULL DEFAULT 5,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_user_profiles_clerk ON user_profiles(clerk_user_id);
CREATE INDEX idx_user_profiles_stripe ON user_profiles(stripe_customer_id)
  WHERE stripe_customer_id IS NOT NULL;

ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;

CREATE POLICY "users_read_own_profile"
  ON user_profiles FOR SELECT
  USING (clerk_user_id = auth.uid());

CREATE POLICY "users_update_own_profile"
  ON user_profiles FOR UPDATE
  USING (clerk_user_id = auth.uid());

-- Insert/delete managed by backend with service role key

-- ----------------------------------------------------------------------------
-- 2. api_keys (encrypted at rest)
-- ----------------------------------------------------------------------------
CREATE TABLE api_keys (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
  service TEXT NOT NULL
    CHECK (service IN ('anthropic', 'openai', 'groq', 'telegram', 'slack', 'discord')),
  encrypted_key TEXT NOT NULL,
  key_hint TEXT, -- last 4 chars for display: "...xK9m"
  is_valid BOOLEAN DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(user_id, service)
);

CREATE INDEX idx_api_keys_user ON api_keys(user_id);

ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;

CREATE POLICY "users_manage_own_keys"
  ON api_keys FOR ALL
  USING (
    user_id IN (
      SELECT id FROM user_profiles WHERE clerk_user_id = auth.uid()
    )
  );

-- ----------------------------------------------------------------------------
-- 3. agents
-- ----------------------------------------------------------------------------
CREATE TABLE agents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  description TEXT NOT NULL,
  system_prompt TEXT NOT NULL,
  config JSONB NOT NULL DEFAULT '{}'::jsonb,
  -- config shape: {
  --   "schedule": "0 9 * * *" | null,
  --   "tools": ["web_search", "telegram_notify"],
  --   "boundaries": {},
  --   "llm_provider": "anthropic",
  --   "llm_model": "claude-sonnet-4-6",
  --   "reflect_every": 10
  -- }
  memory JSONB NOT NULL DEFAULT '{}'::jsonb,
  -- memory shape: {
  --   "strategy_notes": "...",
  --   "lessons": [],
  --   "stats": {},
  --   "last_reflection": "ISO timestamp",
  --   "reflection_count": 0
  -- }
  status TEXT NOT NULL DEFAULT 'active'
    CHECK (status IN ('active', 'paused', 'error', 'archived')),
  output_channel TEXT
    CHECK (output_channel IS NULL OR output_channel IN ('telegram', 'slack', 'discord')),
  total_runs INTEGER NOT NULL DEFAULT 0,
  total_tokens INTEGER NOT NULL DEFAULT 0,
  last_run_at TIMESTAMPTZ,
  next_run_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

  -- Guard against unbounded memory growth (1MB limit)
  CONSTRAINT memory_size_limit CHECK (octet_length(memory::text) < 1048576)
);

CREATE INDEX idx_agents_user ON agents(user_id);
CREATE INDEX idx_agents_status ON agents(status) WHERE status = 'active';
CREATE INDEX idx_agents_next_run ON agents(next_run_at)
  WHERE status = 'active' AND next_run_at IS NOT NULL;

ALTER TABLE agents ENABLE ROW LEVEL SECURITY;

CREATE POLICY "users_manage_own_agents"
  ON agents FOR ALL
  USING (
    user_id IN (
      SELECT id FROM user_profiles WHERE clerk_user_id = auth.uid()
    )
  );

-- ----------------------------------------------------------------------------
-- 4. run_logs
-- ----------------------------------------------------------------------------
CREATE TABLE run_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
  status TEXT NOT NULL
    CHECK (status IN ('running', 'success', 'error')),
  output TEXT,
  error TEXT,
  tokens_used INTEGER DEFAULT 0,
  duration_ms INTEGER,
  metadata JSONB DEFAULT '{}'::jsonb,
  -- metadata: tool calls made, reflection triggered, etc.
  ran_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_run_logs_agent ON run_logs(agent_id, ran_at DESC);
CREATE INDEX idx_run_logs_user ON run_logs(user_id, ran_at DESC);
CREATE INDEX idx_run_logs_status ON run_logs(status) WHERE status = 'running';

ALTER TABLE run_logs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "users_read_own_logs"
  ON run_logs FOR SELECT
  USING (
    user_id IN (
      SELECT id FROM user_profiles WHERE clerk_user_id = auth.uid()
    )
  );

-- Only backend inserts logs (service role)

-- ----------------------------------------------------------------------------
-- 5. bot_connections (track OAuth state + channel config)
-- ----------------------------------------------------------------------------
CREATE TABLE bot_connections (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
  platform TEXT NOT NULL
    CHECK (platform IN ('telegram', 'slack', 'discord')),
  -- Platform-specific config
  config JSONB NOT NULL DEFAULT '{}'::jsonb,
  -- telegram: { "chat_id": "123", "bot_username": "mybot" }
  -- slack:    { "channel_id": "C0123", "team_id": "T0123", "channel_name": "#general" }
  -- discord:  { "guild_id": "123", "channel_id": "456" }
  is_active BOOLEAN NOT NULL DEFAULT true,
  connected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(user_id, platform)
);

CREATE INDEX idx_bot_connections_user ON bot_connections(user_id);

ALTER TABLE bot_connections ENABLE ROW LEVEL SECURITY;

CREATE POLICY "users_manage_own_bots"
  ON bot_connections FOR ALL
  USING (
    user_id IN (
      SELECT id FROM user_profiles WHERE clerk_user_id = auth.uid()
    )
  );

-- ----------------------------------------------------------------------------
-- 6. Helper: updated_at trigger
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_user_profiles_updated
  BEFORE UPDATE ON user_profiles
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_api_keys_updated
  BEFORE UPDATE ON api_keys
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_agents_updated
  BEFORE UPDATE ON agents
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ----------------------------------------------------------------------------
-- 7. Helper: daily run counter (for plan enforcement)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION get_daily_run_count(p_user_id UUID)
RETURNS INTEGER AS $$
  SELECT count(*)::integer
  FROM run_logs
  WHERE user_id = p_user_id
    AND ran_at >= date_trunc('day', now() AT TIME ZONE 'UTC');
$$ LANGUAGE sql STABLE;

-- ----------------------------------------------------------------------------
-- 8. Helper: agent count per user (for plan enforcement)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION get_agent_count(p_user_id UUID)
RETURNS INTEGER AS $$
  SELECT count(*)::integer
  FROM agents
  WHERE user_id = p_user_id
    AND status != 'archived';
$$ LANGUAGE sql STABLE;
