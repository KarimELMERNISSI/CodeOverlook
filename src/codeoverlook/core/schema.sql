-- CodeOverlook Fact Store Schema (SQLite 3.35+)
-- Aligned with FactStore (src/codeoverlook/core/store.py)

CREATE TABLE IF NOT EXISTS files (
    path TEXT PRIMARY KEY,
    sha256 TEXT NOT NULL,
    block_id TEXT NOT NULL DEFAULT 'unassigned',
    loc INTEGER NOT NULL DEFAULT 0,
    is_test INTEGER NOT NULL DEFAULT 0,
    indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS symbols (
    id TEXT PRIMARY KEY,
    file_path TEXT NOT NULL REFERENCES files(path) ON DELETE CASCADE,
    kind TEXT NOT NULL,           -- 'module' | 'class' | 'function' | 'method'
    name TEXT NOT NULL,
    qualname TEXT NOT NULL,
    signature TEXT NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    docstring TEXT
);

CREATE TABLE IF NOT EXISTS edges (
    src_id TEXT NOT NULL,
    dst_id TEXT NOT NULL,
    kind TEXT NOT NULL,           -- 'IMPORTS' | 'CALLS' | 'INHERITS' | 'RUNTIME_CALL'
    target_scope TEXT NOT NULL DEFAULT 'INTERNAL', -- 'INTERNAL' | 'STDLIB' | 'EXTERNAL'
    weight INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (src_id, dst_id, kind)
);

CREATE TABLE IF NOT EXISTS traces (
    usecase_id TEXT PRIMARY KEY,
    entry_symbol_id TEXT,
    sequence_json TEXT NOT NULL,
    coverage_ratio REAL DEFAULT 0.0,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL REFERENCES files(path) ON DELETE CASCADE,
    symbol_id TEXT,
    tool TEXT NOT NULL,           -- 'codeoverlook-ast' | 'bandit' | 'semgrep' | 'pip-audit'
    rule_id TEXT NOT NULL,
    severity TEXT NOT NULL,       -- 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'INFO'
    category TEXT NOT NULL,       -- 'SINK' | 'SAST' | 'CVE' | 'ARCH'
    line INTEGER NOT NULL,
    message TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_files_block ON files(block_id);
CREATE INDEX IF NOT EXISTS idx_files_test ON files(is_test, block_id);
CREATE INDEX IF NOT EXISTS idx_symbols_file ON symbols(file_path);
CREATE INDEX IF NOT EXISTS idx_edges_src ON edges(src_id, kind);
CREATE INDEX IF NOT EXISTS idx_edges_dst ON edges(dst_id, kind);
CREATE INDEX IF NOT EXISTS idx_edges_kind_scope ON edges(kind, target_scope);
CREATE INDEX IF NOT EXISTS idx_findings_file ON findings(file_path, severity);
CREATE INDEX IF NOT EXISTS idx_findings_symbol ON findings(symbol_id);

-- Analytical views for module dependency and production block risk inspection
CREATE VIEW IF NOT EXISTS v_internal_module_edges AS
SELECT DISTINCT
    CASE WHEN instr(src_id, '::') > 0 THEN substr(src_id, 1, instr(src_id, '::') - 1) ELSE src_id END AS src_file,
    CASE WHEN instr(dst_id, '::') > 0 THEN substr(dst_id, 1, instr(dst_id, '::') - 1) ELSE dst_id END AS dst_file,
    kind,
    weight
FROM edges
WHERE target_scope = 'INTERNAL';

CREATE VIEW IF NOT EXISTS v_block_risk_summary AS
WITH file_findings AS (
    SELECT
        file_path,
        COUNT(*) AS total_findings,
        SUM(CASE WHEN severity IN ('CRITICAL', 'HIGH') THEN 1 ELSE 0 END) AS high_risk_findings,
        SUM(CASE WHEN category = 'SINK' THEN 1 ELSE 0 END) AS sensitive_sinks
    FROM findings
    GROUP BY file_path
)
SELECT
    f.block_id,
    COUNT(f.path) AS file_count,
    COALESCE(SUM(f.loc), 0) AS total_loc,
    COALESCE(SUM(ff.total_findings), 0) AS total_findings,
    COALESCE(SUM(ff.high_risk_findings), 0) AS high_risk_findings,
    COALESCE(SUM(ff.sensitive_sinks), 0) AS sensitive_sinks
FROM files f
LEFT JOIN file_findings ff ON ff.file_path = f.path
WHERE f.is_test = 0
GROUP BY f.block_id;
