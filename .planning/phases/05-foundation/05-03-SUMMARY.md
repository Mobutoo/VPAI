---
plan: "05-03"
phase: "05-foundation"
status: complete
started: 2026-03-17
completed: 2026-03-17
---

# Plan 05-03: Kitsu Provisioning — Summary

## What was built

1. **kitsu-provision Ansible role** (`roles/kitsu-provision/`)
   - Zou CLI initialization (upgrade-db, init-data, create-admin)
   - REST API provisioning script for project structure
   - Idempotent with sentinel file guard

2. **Kitsu project structure** (provisioned via API):
   - Production: "Paul Taff — Lancement" (tvshow type)
   - Episode: "Drop 1"
   - 4 Sequences: Pre-production, Ecriture, Production, Post-production
   - 14 Task types: Brief, Recherche, Script, Storyboard CF, Voice-over, Music, Image Gen, Video Gen, Montage, Sous-titres, Color Grade, Review, Export, Publication
   - Custom status: "Generating" (for AI pipeline steps)

3. **Bot account "Mobotoo"** — dedicated admin bot for API automation
   - Email: javisi.bot@gmail.com
   - Credentials stored in Ansible vault

4. **Vault variables added:**
   - `vault_kitsu_secret_key`, `vault_kitsu_admin_email`, `vault_kitsu_admin_password`
   - `vault_kitsu_bot_email`, `vault_kitsu_bot_password`, `vault_kitsu_bot_id`

## Deviations

- **Admin user**: Kitsu was pre-initialized with `seko.mobutoo@gmail.com` (not `admin@ewutelo.cloud`). Provision script's `create-admin` step would create a separate admin — bot account "Mobotoo" created instead for API automation.
- **Task types**: Names updated from PRD originals (Moodboard→Voice-over, Sound Design→Music, Assets→Image Gen, Rough Cut→Video Gen, Fine Cut→Montage) to match actual Content Factory pipeline.
- **Default Zou data**: `zou init-data` creates default VFX task types (Modeling, Animation, etc.) alongside our custom ones. Not harmful — they can be archived later.

## Commits

- `e80f3d4` feat(05-03): create kitsu-provision role with Zou CLI init and project structure
- `0dc3cc8` fix(05-03): align kitsu-provision defaults with actual API provisioning

## Kitsu IDs (for downstream phases)

| Entity | ID |
|--------|-----|
| Production | `19b9faf4-f7c4-4829-9739-cbf7c3181941` |
| Episode "Drop 1" | `e5deb971-7b45-4cde-9f79-b1de84303a72` |
| Seq Pre-production | `afd7480d-5571-4b31-96e3-2248cc3a165a` |
| Seq Ecriture | `933f8e43-d5d3-4652-9645-ee4585093411` |
| Seq Production | `17d5a100-d6ac-4ca7-a476-7381b75966d6` |
| Seq Post-production | `682662ad-fd17-46c5-b8b6-5240b3b061b5` |
| Bot Mobotoo | `7a7e6854-7b12-4650-906a-e6c3f9da82e2` |
