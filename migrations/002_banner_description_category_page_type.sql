-- Migration 002: banners.description + categories.page_type

ALTER TABLE banners
  ADD COLUMN IF NOT EXISTS description VARCHAR(255);

ALTER TABLE categories
  ADD COLUMN IF NOT EXISTS page_type VARCHAR(20) NOT NULL DEFAULT 'product';
