import os

# Set stub env vars before any swarm_core module is imported.
# swarm_core.config raises EnvironmentError at module load time if these are absent.
# All Supabase clients are mocked in tests, so the values here are never used.
os.environ.setdefault("SUPABASE_URL", "http://localhost:54321")
os.environ.setdefault("SUPABASE_KEY", "test-key-stub")
