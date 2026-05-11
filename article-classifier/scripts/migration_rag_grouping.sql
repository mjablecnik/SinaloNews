-- Migration: RAG-based grouping
-- Adds needs_regeneration flag to article_groups and creates full_article_indexed tracking table.

ALTER TABLE article_groups
    ADD COLUMN IF NOT EXISTS needs_regeneration BOOLEAN NOT NULL DEFAULT false;

CREATE TABLE IF NOT EXISTS full_article_indexed (
    article_id INTEGER PRIMARY KEY REFERENCES articles(id) ON DELETE CASCADE,
    indexed_at TIMESTAMP NOT NULL DEFAULT NOW()
);
