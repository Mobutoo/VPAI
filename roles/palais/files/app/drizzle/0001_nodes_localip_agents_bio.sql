-- Migration 0001: Add localIp + description to nodes, bio to agents
-- Phase 17 — Nodes real IPs/descriptions, Agent bio snippets

ALTER TABLE "nodes" ADD COLUMN IF NOT EXISTS "local_ip" varchar(50);
ALTER TABLE "nodes" ADD COLUMN IF NOT EXISTS "description" text;

ALTER TABLE "agents" ADD COLUMN IF NOT EXISTS "bio" text;

-- Extend node_status enum for full status visibility on Health page
ALTER TYPE "public"."node_status" ADD VALUE IF NOT EXISTS 'busy';
ALTER TYPE "public"."node_status" ADD VALUE IF NOT EXISTS 'degraded';
