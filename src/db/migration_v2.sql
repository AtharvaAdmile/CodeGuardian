-- =============================================================
-- CodeGuardian Schema Migration v2
-- =============================================================
-- This migration is IDEMPOTENT — safe to run multiple times.
-- It adds new columns to existing tables and creates new tables
-- only if they don't already exist.
--
-- Run this in the Supabase SQL Editor.
-- =============================================================


-- =============================================
-- 0. EXTENSIONS
-- =============================================

CREATE EXTENSION IF NOT EXISTS vector;


-- =============================================
-- 1. ALTER TABLE: projects
--    Add new columns that don't exist in the
--    original schema.
-- =============================================

-- repo_url: remote repository URL
DO $$ BEGIN
  ALTER TABLE projects ADD COLUMN repo_url TEXT;
EXCEPTION WHEN duplicate_column THEN NULL;
END $$;

-- local_path: local filesystem path
DO $$ BEGIN
  ALTER TABLE projects ADD COLUMN local_path TEXT;
EXCEPTION WHEN duplicate_column THEN NULL;
END $$;

-- team_id: for future team/org features
DO $$ BEGIN
  ALTER TABLE projects ADD COLUMN team_id UUID;
EXCEPTION WHEN duplicate_column THEN NULL;
END $$;

-- config_json: project-level configuration
DO $$ BEGIN
  ALTER TABLE projects ADD COLUMN config_json JSONB DEFAULT '{}';
EXCEPTION WHEN duplicate_column THEN NULL;
END $$;

-- updated_at: last update timestamp
DO $$ BEGIN
  ALTER TABLE projects ADD COLUMN updated_at TIMESTAMPTZ DEFAULT NOW();
EXCEPTION WHEN duplicate_column THEN NULL;
END $$;


-- =============================================
-- 2. ALTER TABLE: decisions
--    Add new columns for richer ADR tracking.
--    Existing columns (description → context mapping,
--    rationale → reasoning) are kept as-is to avoid
--    data loss. New columns are added alongside them.
-- =============================================

-- context: situational context for the decision
DO $$ BEGIN
  ALTER TABLE decisions ADD COLUMN context TEXT;
EXCEPTION WHEN duplicate_column THEN NULL;
END $$;

-- decision: what was actually decided
DO $$ BEGIN
  ALTER TABLE decisions ADD COLUMN decision TEXT;
EXCEPTION WHEN duplicate_column THEN NULL;
END $$;

-- reasoning: why this approach was chosen
DO $$ BEGIN
  ALTER TABLE decisions ADD COLUMN reasoning TEXT;
EXCEPTION WHEN duplicate_column THEN NULL;
END $$;

-- source_type: origin of the decision (pr_comment, commit_msg, manual, slack)
DO $$ BEGIN
  ALTER TABLE decisions ADD COLUMN source_type TEXT;
EXCEPTION WHEN duplicate_column THEN NULL;
END $$;

-- source_ref: reference link (PR URL, commit SHA, etc.)
DO $$ BEGIN
  ALTER TABLE decisions ADD COLUMN source_ref TEXT;
EXCEPTION WHEN duplicate_column THEN NULL;
END $$;

-- author_name: who made the decision
DO $$ BEGIN
  ALTER TABLE decisions ADD COLUMN author_name TEXT;
EXCEPTION WHEN duplicate_column THEN NULL;
END $$;

-- embedding: vector embedding for semantic search (1024-dim for NIM nvidia/nv-embedqa-e5-v5)
DO $$ BEGIN
  ALTER TABLE decisions ADD COLUMN embedding VECTOR(1024);
EXCEPTION WHEN duplicate_column THEN NULL;
END $$;


-- =============================================
-- 3. NEW TABLE: code_embeddings
--    Vector store with 1024-dim embeddings
--    (separate from the legacy 768-dim embeddings table)
-- =============================================

CREATE TABLE IF NOT EXISTS code_embeddings (
  id TEXT PRIMARY KEY,                           -- deterministic hash from embedding_service
  project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
  file_path TEXT NOT NULL,
  chunk_text TEXT NOT NULL,
  chunk_type TEXT,                               -- 'function', 'class', 'module', 'comment', 'docstring'
  language TEXT,
  start_line INT,
  end_line INT,
  embedding VECTOR(1024),                        -- matches NIM nvidia/nv-embedqa-e5-v5 dimension
  metadata_json JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT NOW()
);


-- =============================================
-- 4. NEW TABLE: impact_history
--    Stores blast-radius analysis results
-- =============================================

CREATE TABLE IF NOT EXISTS impact_history (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
  changed_file TEXT NOT NULL,
  blast_radius_json JSONB NOT NULL,
  risk_score FLOAT,
  analyzed_at TIMESTAMPTZ DEFAULT NOW()
);


-- =============================================
-- 5. NEW TABLE: expertise_map
--    Maps authors to files with contribution scores
-- =============================================

CREATE TABLE IF NOT EXISTS expertise_map (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
  author_name TEXT NOT NULL,
  file_path TEXT NOT NULL,
  score FLOAT DEFAULT 0,
  commit_count INT DEFAULT 0,
  last_contribution_at TIMESTAMPTZ,
  UNIQUE(project_id, author_name, file_path)
);


-- =============================================
-- 6. INDEXES
--    CREATE INDEX IF NOT EXISTS is safe to re-run.
-- =============================================

-- Vector similarity indexes (IVFFlat)
-- Note: IVFFlat indexes require the table to have some rows for optimal
-- performance. If the table is empty, the index will still be created
-- but may need to be rebuilt after initial data load with:
--   REINDEX INDEX <index_name>;

CREATE INDEX IF NOT EXISTS idx_code_embeddings_vector
  ON code_embeddings USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);

CREATE INDEX IF NOT EXISTS idx_decisions_vector
  ON decisions USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 50);

-- Lookup indexes
CREATE INDEX IF NOT EXISTS idx_code_embeddings_project
  ON code_embeddings (project_id);

CREATE INDEX IF NOT EXISTS idx_impact_history_project
  ON impact_history (project_id);

CREATE INDEX IF NOT EXISTS idx_expertise_map_project_file
  ON expertise_map (project_id, file_path);


-- =============================================
-- 7. ROW LEVEL SECURITY (RLS)
--    Enable RLS and create permissive policies.
--    DROP POLICY IF EXISTS prevents errors on re-run.
-- =============================================

ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE code_embeddings ENABLE ROW LEVEL SECURITY;
ALTER TABLE decisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE impact_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE expertise_map ENABLE ROW LEVEL SECURITY;

-- Permissive "allow all" policies (tighten when adding auth)
DROP POLICY IF EXISTS "allow_all" ON projects;
CREATE POLICY "allow_all" ON projects FOR ALL USING (true);

DROP POLICY IF EXISTS "allow_all" ON code_embeddings;
CREATE POLICY "allow_all" ON code_embeddings FOR ALL USING (true);

DROP POLICY IF EXISTS "allow_all" ON decisions;
CREATE POLICY "allow_all" ON decisions FOR ALL USING (true);

DROP POLICY IF EXISTS "allow_all" ON impact_history;
CREATE POLICY "allow_all" ON impact_history FOR ALL USING (true);

DROP POLICY IF EXISTS "allow_all" ON expertise_map;
CREATE POLICY "allow_all" ON expertise_map FOR ALL USING (true);


-- =============================================
-- 8. HELPER FUNCTION: match_code_embeddings
--    Updated to use the new code_embeddings table
--    with 1024-dim vectors.
-- =============================================

CREATE OR REPLACE FUNCTION match_code_embeddings(
  query_embedding VECTOR(1024),
  match_count INT DEFAULT 10,
  filter_project_id UUID DEFAULT NULL
)
RETURNS TABLE (
  id TEXT,
  file_path TEXT,
  chunk_text TEXT,
  chunk_type TEXT,
  language TEXT,
  start_line INT,
  end_line INT,
  metadata_json JSONB,
  similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    ce.id,
    ce.file_path,
    ce.chunk_text,
    ce.chunk_type,
    ce.language,
    ce.start_line,
    ce.end_line,
    ce.metadata_json,
    1 - (ce.embedding <=> query_embedding) AS similarity
  FROM code_embeddings ce
  WHERE (filter_project_id IS NULL OR ce.project_id = filter_project_id)
  ORDER BY ce.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;


-- =============================================
-- 9. HELPER FUNCTION: match_decisions
--    Semantic search over architectural decisions.
-- =============================================

CREATE OR REPLACE FUNCTION match_decisions(
  query_embedding VECTOR(1024),
  target_project_id UUID DEFAULT NULL,
  match_threshold FLOAT DEFAULT 0.7,
  match_count INT DEFAULT 5
)
RETURNS TABLE (
  id UUID,
  title TEXT,
  decision TEXT,
  reasoning TEXT,
  similarity FLOAT,
  status TEXT
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    d.id,
    d.title,
    d.decision,
    d.reasoning,
    1 - (d.embedding <=> query_embedding) AS similarity,
    d.status
  FROM decisions d
  WHERE
    (target_project_id IS NULL OR d.project_id = target_project_id)
    AND d.embedding IS NOT NULL
    AND 1 - (d.embedding <=> query_embedding) > match_threshold
  ORDER BY d.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;


-- =============================================================
-- MIGRATION COMPLETE
-- =============================================================
-- Summary of changes:
--   ✅ projects        → 5 new columns added (repo_url, local_path, team_id, config_json, updated_at)
--   ✅ decisions        → 7 new columns added (context, decision, reasoning, source_type, source_ref, author_name, embedding)
--   ✅ code_embeddings  → new table (1024-dim vectors for NIM embeddings)
--   ✅ impact_history   → new table (blast radius analysis logs)
--   ✅ expertise_map    → new table (author-to-file contribution scores)
--   ✅ RLS policies     → enabled on all new + existing tables
--   ✅ Helper functions  → match_code_embeddings, match_decisions
-- =============================================================
