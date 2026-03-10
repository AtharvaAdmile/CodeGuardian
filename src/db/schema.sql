-- ============================================
-- CodeGuardian Database Schema for Supabase
-- ============================================
-- This file is for reference only.
-- Schema is applied via Supabase migrations.

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================
-- 1. PROJECT & FILES
-- ============================================

CREATE TABLE projects (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name TEXT NOT NULL,
  root_path TEXT NOT NULL,
  total_files INT DEFAULT 0,
  total_lines INT DEFAULT 0,
  indexed_at TIMESTAMP,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE code_files (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
  path TEXT NOT NULL,
  language TEXT NOT NULL,
  content TEXT,
  line_count INT,
  last_modified TIMESTAMP,
  git_commit_hash TEXT,
  created_at TIMESTAMP DEFAULT NOW(),
  UNIQUE(project_id, path)
);

CREATE INDEX idx_files_project ON code_files(project_id);
CREATE INDEX idx_files_language ON code_files(language);

-- ============================================
-- 2. CODE ENTITIES & EMBEDDINGS
-- ============================================

CREATE TABLE code_entities (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  file_id UUID REFERENCES code_files(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  type TEXT NOT NULL,
  signature TEXT,
  start_line INT,
  end_line INT,
  docstring TEXT,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_entities_file ON code_entities(file_id);
CREATE INDEX idx_entities_name ON code_entities(name);

CREATE TABLE embeddings (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  file_id UUID REFERENCES code_files(id) ON DELETE CASCADE,
  entity_id UUID REFERENCES code_entities(id) ON DELETE SET NULL,
  chunk_text TEXT NOT NULL,
  embedding VECTOR(768),
  start_line INT,
  end_line INT,
  metadata JSONB,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX embeddings_vector_idx ON embeddings 
USING ivfflat (embedding vector_cosine_ops) 
WITH (lists = 100);

-- ============================================
-- 3. DEPENDENCIES
-- ============================================

CREATE TABLE dependencies (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
  from_file_id UUID REFERENCES code_files(id) ON DELETE CASCADE,
  to_file_id UUID REFERENCES code_files(id) ON DELETE CASCADE,
  type TEXT NOT NULL,
  line_number INT,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_deps_from ON dependencies(from_file_id);
CREATE INDEX idx_deps_to ON dependencies(to_file_id);

-- ============================================
-- 4. ARCHITECTURAL DECISIONS
-- ============================================

CREATE TABLE decisions (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  description TEXT NOT NULL,
  rationale TEXT,
  alternatives JSONB,
  status TEXT DEFAULT 'active',
  tags TEXT[],
  made_by TEXT,
  made_at TIMESTAMP DEFAULT NOW(),
  git_commit_hash TEXT,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_decisions_project ON decisions(project_id);
CREATE INDEX idx_decisions_tags ON decisions USING GIN(tags);

CREATE TABLE decision_anchors (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  decision_id UUID REFERENCES decisions(id) ON DELETE CASCADE,
  file_id UUID REFERENCES code_files(id) ON DELETE CASCADE,
  line_number INT,
  code_snippet TEXT,
  created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================
-- 5. AGENT TASKS
-- ============================================

CREATE TABLE agent_tasks (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
  type TEXT NOT NULL,
  description TEXT NOT NULL,
  status TEXT DEFAULT 'pending',
  context JSONB,
  result JSONB,
  error_message TEXT,
  blast_radius_score INT,
  requires_approval BOOLEAN DEFAULT false,
  approved_at TIMESTAMP,
  started_at TIMESTAMP,
  completed_at TIMESTAMP,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_tasks_project ON agent_tasks(project_id);
CREATE INDEX idx_tasks_status ON agent_tasks(status);

CREATE TABLE agent_actions (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  task_id UUID REFERENCES agent_tasks(id) ON DELETE CASCADE,
  step_number INT,
  action_type TEXT,
  input JSONB,
  output JSONB,
  success BOOLEAN,
  error TEXT,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE code_changes (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  task_id UUID REFERENCES agent_tasks(id) ON DELETE CASCADE,
  file_id UUID REFERENCES code_files(id) ON DELETE SET NULL,
  change_type TEXT,
  old_content TEXT,
  new_content TEXT,
  diff TEXT,
  git_commit_hash TEXT,
  created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================
-- 6. HELPER FUNCTIONS
-- ============================================

CREATE OR REPLACE FUNCTION match_embeddings(
  query_embedding VECTOR(768),
  match_threshold FLOAT DEFAULT 0.7,
  match_count INT DEFAULT 5
)
RETURNS TABLE (
  file_id UUID,
  chunk_text TEXT,
  similarity FLOAT,
  file_path TEXT,
  start_line INT,
  end_line INT
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    e.file_id,
    e.chunk_text,
    1 - (e.embedding <=> query_embedding) AS similarity,
    cf.path AS file_path,
    e.start_line,
    e.end_line
  FROM embeddings e
  JOIN code_files cf ON e.file_id = cf.id
  WHERE 1 - (e.embedding <=> query_embedding) > match_threshold
  ORDER BY e.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

CREATE OR REPLACE FUNCTION calculate_blast_radius(target_file_id UUID)
RETURNS INT
LANGUAGE sql
AS $$
  WITH RECURSIVE dep_tree AS (
    SELECT to_file_id, 1 AS depth
    FROM dependencies
    WHERE from_file_id = target_file_id
    
    UNION
    
    SELECT d.to_file_id, dt.depth + 1
    FROM dependencies d
    INNER JOIN dep_tree dt ON d.from_file_id = dt.to_file_id
    WHERE dt.depth < 5
  )
  SELECT COUNT(DISTINCT to_file_id)::INT FROM dep_tree;
$$;

-- ============================================
-- 7. FILE METRICS (Tech Debt & Expertise)
-- ============================================

CREATE TABLE file_metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    file_path TEXT NOT NULL,
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    complexity_score INTEGER DEFAULT 0,
    churn_score INTEGER DEFAULT 0,
    health_score INTEGER DEFAULT 100,
    top_expert TEXT,
    backup_expert TEXT,
    last_analyzed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(project_id, file_path)
);

CREATE INDEX idx_file_metrics_project ON file_metrics(project_id);
CREATE INDEX idx_file_metrics_health ON file_metrics(health_score);

-- ============================================
-- 8. GIT CONTEXT CACHE
-- ============================================

CREATE TABLE git_context_cache (
    commit_hash TEXT PRIMARY KEY,
    message TEXT,
    author TEXT,
    pr_description TEXT,
    timestamp TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_git_context_author ON git_context_cache(author);

