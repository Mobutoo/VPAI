-- Flash Suite event pipeline schema
-- Mounted as /docker-entrypoint-initdb.d/init.sql in docker-compose.yml

CREATE SCHEMA IF NOT EXISTS suite;

CREATE TABLE IF NOT EXISTS suite.events (
  id SERIAL PRIMARY KEY,
  event_id TEXT NOT NULL UNIQUE,
  type TEXT NOT NULL,
  source TEXT NOT NULL,
  user_id TEXT NOT NULL,
  tenant_id TEXT,
  payload JSONB NOT NULL,
  correlation_id TEXT NOT NULL,
  causation_id TEXT,
  depth INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'pending',
  dispatched BOOLEAN NOT NULL DEFAULT FALSE,
  dispatched_at TIMESTAMPTZ,
  dispatch_results JSONB,
  retry_count INTEGER NOT NULL DEFAULT 0,
  next_retry_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_events_status ON suite.events(status);
CREATE INDEX IF NOT EXISTS idx_events_next_retry ON suite.events(next_retry_at) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_events_event_id ON suite.events(event_id);

-- ============================================================
-- Gamification Engine Tables
-- ============================================================

-- User XP, level, streak, referral tracking
CREATE TABLE IF NOT EXISTS suite.gamification_progress (
  user_id TEXT PRIMARY KEY,
  total_xp INTEGER NOT NULL DEFAULT 0,
  level INTEGER NOT NULL DEFAULT 1,
  current_streak INTEGER NOT NULL DEFAULT 0,
  longest_streak INTEGER NOT NULL DEFAULT 0,
  last_active_date DATE,
  referral_code TEXT UNIQUE NOT NULL,
  referred_by TEXT,
  referral_count INTEGER NOT NULL DEFAULT 0,
  streak_freezes_remaining INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- XP transaction log (audit trail, enables recalculation)
CREATE TABLE IF NOT EXISTS suite.xp_transactions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id TEXT NOT NULL REFERENCES suite.gamification_progress(user_id),
  xp_amount INTEGER NOT NULL,
  source_event_type TEXT NOT NULL,
  source_app TEXT NOT NULL,
  source_event_id TEXT UNIQUE,
  metadata JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_xp_transactions_user ON suite.xp_transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_xp_transactions_date ON suite.xp_transactions(created_at);
CREATE INDEX IF NOT EXISTS idx_xp_transactions_daily_cap ON suite.xp_transactions(user_id, source_event_type, created_at);

-- Features unlocked per user
CREATE TABLE IF NOT EXISTS suite.unlocked_features (
  user_id TEXT NOT NULL REFERENCES suite.gamification_progress(user_id),
  feature_id TEXT NOT NULL,
  unlocked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (user_id, feature_id)
);

-- Badge definitions (what badges exist)
CREATE TABLE IF NOT EXISTS suite.badge_definitions (
  badge_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT NOT NULL,
  icon TEXT NOT NULL,
  category TEXT NOT NULL DEFAULT 'general',
  hint TEXT,
  condition JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Badges earned per user
CREATE TABLE IF NOT EXISTS suite.user_badges (
  user_id TEXT NOT NULL REFERENCES suite.gamification_progress(user_id),
  badge_id TEXT NOT NULL REFERENCES suite.badge_definitions(badge_id),
  earned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (user_id, badge_id)
);

-- Daily impact metrics (aggregated)
CREATE TABLE IF NOT EXISTS suite.daily_impact (
  user_id TEXT NOT NULL,
  date DATE NOT NULL,
  app TEXT NOT NULL,
  metric_type TEXT NOT NULL,
  value NUMERIC NOT NULL DEFAULT 0,
  event_count INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (user_id, date, app, metric_type)
);
CREATE INDEX IF NOT EXISTS idx_daily_impact_user_date ON suite.daily_impact(user_id, date);

-- Pre-computed wraps
CREATE TABLE IF NOT EXISTS suite.wraps (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id TEXT NOT NULL,
  wrap_type TEXT NOT NULL,
  period_start DATE NOT NULL,
  period_end DATE NOT NULL,
  data JSONB NOT NULL,
  viewed BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (user_id, wrap_type, period_start)
);
CREATE INDEX IF NOT EXISTS idx_wraps_unviewed ON suite.wraps(user_id) WHERE viewed = false;

-- Impact multipliers (admin-configurable)
CREATE TABLE IF NOT EXISTS suite.impact_multipliers (
  event_type TEXT NOT NULL,
  metric_type TEXT NOT NULL,
  value NUMERIC NOT NULL,
  unit TEXT NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (event_type, metric_type)
);

-- Level name presets (admin-configurable)
CREATE TABLE IF NOT EXISTS suite.level_presets (
  preset_id TEXT PRIMARY KEY,
  names JSONB NOT NULL,
  is_active BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_one_active_preset ON suite.level_presets(is_active) WHERE is_active = true;

-- ============================================================
-- Seed Data
-- ============================================================

INSERT INTO suite.impact_multipliers (event_type, metric_type, value, unit) VALUES
  ('meal.planned', 'money_saved', 7.50, '€'),
  ('meal.planned', 'time_saved', 10, 'min'),
  ('grocery.purchased', 'money_saved', 3.00, '€'),
  ('receipt.processed', 'time_saved', 5, 'min'),
  ('task.completed', 'time_saved', 8, 'min'),
  ('workflow.triggered', 'time_saved', 15, 'min')
ON CONFLICT DO NOTHING;

INSERT INTO suite.badge_definitions (badge_id, name, description, icon, category, hint, condition) VALUES
  ('first_meal', 'Premier Repas', 'Planifie ton premier repas', 'utensils', 'mastery', 'Utilise la planification de repas', '{"event_type": "meal.planned", "count": 1}'),
  ('meal_master', 'Chef Cuistot', 'Planifie 50 repas', 'chef-hat', 'mastery', 'Continue à planifier tes repas', '{"event_type": "meal.planned", "count": 50}'),
  ('streak_7', 'Semaine de Feu', '7 jours de streak', 'flame', 'streak', 'Utilise la suite 7 jours de suite', '{"streak": 7}'),
  ('streak_30', 'Mois Infernal', '30 jours de streak', 'fire', 'streak', 'Utilise la suite 30 jours de suite', '{"streak": 30}'),
  ('cross_app', 'Explorateur', 'Utilise 3 apps en un jour', 'compass', 'general', 'Essaie toutes les apps', '{"cross_app_count": 3}'),
  ('level_7', 'Ceinture Noire', 'Atteins le niveau maximum', 'award', 'mastery', 'Continue ta progression', '{"level": 7}'),
  ('referral_1', 'Premier Parrain', 'Parraine 1 ami actif', 'user-plus', 'referral', 'Invite un ami', '{"referral_count": 1}'),
  ('referral_3', 'Ambassadeur', 'Parraine 3 amis actifs', 'users', 'referral', 'Invite tes amis', '{"referral_count": 3}'),
  ('referral_10', 'Recruteur d''Elite', 'Parraine 10 amis actifs', 'crown', 'referral', 'Tu es un vrai ambassadeur', '{"referral_count": 10}')
ON CONFLICT DO NOTHING;

INSERT INTO suite.level_presets (preset_id, names, is_active) VALUES
  ('martial_arts', '["Blanche","Jaune","Orange","Verte","Bleue","Marron","Noire"]', true),
  ('cuisine', '["Commis","Cuisinier","Chef de Partie","Sous-Chef","Chef","Chef Étoilé","Maître"]', false),
  ('numeric', '["Niveau 1","Niveau 2","Niveau 3","Niveau 4","Niveau 5","Niveau 6","Niveau 7"]', false)
ON CONFLICT DO NOTHING;
