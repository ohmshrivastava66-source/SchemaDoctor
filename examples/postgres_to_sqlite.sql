CREATE TABLE users (
    id BIGSERIAL PRIMARY KEY,
    profile JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);
