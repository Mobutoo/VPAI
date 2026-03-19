# Kitsu/CGWire Documentation — Full Scrape for Qdrant Embedding

> Scraped: 2026-03-19
> Sources: kitsu.cg-wire.com, zou.cg-wire.com, gazu.cg-wire.com, api-docs.kitsu.cloud, dev.kitsu.cloud

---

# PART 1: KITSU USER DOCUMENTATION (kitsu.cg-wire.com)

## 1.1 Getting Started With Kitsu
**URL**: https://kitsu.cg-wire.com/configure-kitsu/

Kitsu enables users to track various production projects spanning 2D and 3D production, VFX, video games, and related work. Projects can range from simple advertisements to extensive feature films.

### Understanding Studio Workflows
A workflow represents the structured coordination of tasks constituting the operational processes within a production. In CGI production, tasks like modeling, rigging, and shading are undertaken to finalize assets.

Key terminology:
- **Task Type**: Processes such as modeling and shading
- **Entities**: Individual objects like assets and shots
- **Task**: A specific action needing completion, attributed to entities and categorized by task type

### Global Library vs Production Library
Two library types exist:
- **Global Library**: Studio-level access restricted to Studio managers, containing departments, task types, statuses, asset types, and automation
- **Production Library**: Where specific elements from the global library populate individual productions, keeping each production separated with distinct workflows

### Departments
Departments help supervisors and artists focus on assigned tasks. Once linked to departments, users gain filtered task views for their task type. Departments also determine which metadata columns appear for specific users. Setup involves accessing the main menu, selecting the Department page under Admin, and creating departments with names and colors.

### Task Types
Task types can associate with multiple entities including assets, shots, sequences, episodes, or edits. Creation requires:
- Task type name
- Time logging requirement
- Entity applicability
- Department linkage
- Background color

Newly created task types will appear at the bottom of the list. Users can drag items to reorder them.

### Asset Types
Asset types organize assets by category, similar to folder structures. Different asset types can have distinct workflows. Characters typically require rigging while Environments may not. Creation requires supplying the name and specifying which task types apply to that particular asset type.

### Task Statuses
Statuses represent stages tasks pass through during review and approval. Examples include:
- **Ready**: Artists have everything needed; work shouldn't begin before reaching this status
- **WIP** (Work in Progress): Artists actively working; indicates no reassignment needed
- **WFA** (Waiting-For-Approval): Work completed and awaiting supervisor review
- **Done**: Work completed and approved; next process step can commence
- **Retake**: Comments posted requiring continued work until validation achieved

Status creation requires defining: Full name and short name, Default status designation (only one per system), Whether the status validates tasks, Retake value usage, Artist and client permissions, Feedback request functionality, Background color selection.

### Status Automation
Status Automation defines rules triggering automatic task status changes based on conditions. For assets, automations work between tasks. When a concept task reaches "done," downstream modeling automatically becomes "ready." Automations can also update asset status based on task statuses. The system can copy latest previews with automations.

### 3D Backgrounds
The 3D Backgrounds feature enhances .GLB file reviews by incorporating .HDR backgrounds with lighting information. Users create a global HDR library accessible across productions.

### Asset Library
The Asset Library functions as a centralized repository for assets usable across productions. Users can import character models, props, environments, and similar elements from other projects.

Import permissions depend on user role:
- Studio Managers: Import any assets from any production
- Production Managers: Import only from assigned team productions
- Supervisors and Artists: Cannot import assets

Three import methods exist: import all assets from a production, import by type, or select individual assets.

### Settings
Global studio settings include: Custom studio logo, Studio name configuration, Daily working hours specification, Original filename download options, HD image quality defaults, Timesheet modification restrictions, Chat integration configurations.

---

## 1.2 Preparing Your Team
**URL**: https://kitsu.cg-wire.com/team/

### Creating Users and Linking to Departments
The platform maintains two distinct user libraries:
- **People Page (Global Library)**: Manages permissions, contracts, and departmental assignments
- **Team Page (Production Library)**: Defines project participation and production access

Users require mandatory fields: first name and email address (which must be unique). Optional fields include last name, phone number, department assignment(s), role designation, and activation status. Each user requires an individual account to log in to Kitsu.

### CSV Import
Teams can import employee data via .csv files. The import tool provides preview capabilities and allows column mapping customization. The Role field remains optional during import.

### Permission Roles
Six distinct roles govern system access:

**Artist**: Limited to assigned production access; can comment, upload media, and modify statuses only on assigned tasks. Cannot view client comments or access non-assigned projects.

**Supervisor**: Inherits artist permissions; manages department team member assignments and views departmental assets, shots, and statistics.

**Production Manager**: Manages production-level content including asset/shot creation, batch imports, and playlist management; cannot access studio-wide settings.

**Studio Manager/Administrator**: Full system access across all productions, can customize studio aspects, define task types, and manage user roles.

**Vendor**: Similar to artists but with restricted visibility. Only sees assigned tasks.

**Client**: Limited to assigned production viewing; can access global asset/shot pages and stats pages with restricted status commenting capabilities.

### Two-Factor Authentication
Three authentication methods are available:
- **TOTP**: App-based authentication with QR code scanning
- **OTP Via Email**: Code delivery through email
- **FIDO Device**: Hardware security key support

### Team Assignment
Adding users to production teams requires navigating to the production's TEAM page via dropdown menu and adding users to enable task assignment capabilities. Studio Managers don't require team addition for read access but need addition for task assignment.

---

## 1.3 Create a TV Show Production
**URL**: https://kitsu.cg-wire.com/tvshow/

### Production Setup
Users create a new production by selecting TV Show as the type, specifying technical details like FPS and resolution, and defining the production workflow by selecting asset task types, shot task types, task statuses, and asset types from the global library.

### Asset Management
Assets are created individually through pop-up dialogs or via CSV import. Key features include: Specifying asset types and episodes, Adding descriptions, Creating tasks simultaneously with assets, Updating through manual editing or batch CSV.

### Shot Creation and Management
Multiple methods: Manual creation through sequences and episodes, EDL file import for automated sequence/shot generation with frame data, CSV spreadsheet import and copy-paste functionality, Frame range input (In/Out frames, automatic frame count calculation).

### Concepts
Concept creation and asset linking. Upload multiple concept images simultaneously. Link concepts to assets through comment panel.

### Sequences
Sequences allow macro-level task tracking for production phases like storyboarding, color grading. Dedicated task types with sequence attributes must be created in the global library first.

### Edits
Edits track specific versions of content (complete film, trailers, first edit, fine cut) through validation steps. Edit-specific task types must be created in the global library.

### Breakdown
The breakdown feature assembles shot requirements by displaying available assets alongside selected shots. Users can select individual or multiple shots, assign multiple asset instances, create new assets within the breakdown interface, copy asset selections between shots.

### Custom Metadata Columns
Users create custom columns supporting: Free text entries, Numeric values, Checkboxes, Predefined value lists, Tag systems, Checklists. Columns can be linked to specific departments. Batch modifications work with multiple entity selection.

### Data Import Methods
CSV File Import and Copy-Paste Import both include an "update existing data" toggle, highlighting changes in blue before confirmation.

---

## 1.4 Create a Feature Film Production
**URL**: https://kitsu.cg-wire.com/feature/

Users create a feature film production by clicking "Create a new production," entering the production name, selecting "Feature Film" as the type, and choosing between 2D or 3D styles. Technical specifications include FPS, aspect ratio, and resolution settings which determine video preview re-encoding parameters.

Content mirrors TV Show production with the same asset management, shot creation (via sequences without episodes), EDL imports, concepts, breakdown, custom metadata, and data import capabilities. The Episode column is not present for feature films.

Shot padding conventions (naming shots as SH0010, SH0020, SH0030) are supported.

---

## 1.5 Create a Short Production
**URL**: https://kitsu.cg-wire.com/short/

Short film production setup follows the same patterns as other production types. Technical details (FPS, aspect ratio, resolution) are configured during creation. The production workflow requires selecting asset task types, shot task types, task statuses, and asset categories.

Frame information: If you enter the Frame In and Frame Out, Kitsu automatically calculates the Number of Frame.

All standard features available: Assets, Shots, Sequences, Concepts, Breakdown, Custom Metadata, Edits.

---

## 1.6 Create a SHOTS Only Production
**URL**: https://kitsu.cg-wire.com/short-shot/

A shots-only production focuses exclusively on shot management without asset tracking. Users select "only shots" as the production type. Includes Shots, Sequences, Edits, Concepts, Playlists pages. Same shot creation methods (manual, EDL, CSV). Custom metadata columns, frame information tracking, and all review features.

---

## 1.7 Create an ASSET Only Production
**URL**: https://kitsu.cg-wire.com/short-asset/

Asset-focused production without shots. Users select "only Asset" as the type. Full asset management including creation, CSV import, concepts, edits, breakdown lists, asset library casting. Supports same metadata columns and import/export capabilities.

---

## 1.8 Create a Video Game Production
**URL**: https://kitsu.cg-wire.com/videogame/

Video game productions use Maps and Levels instead of Shots and Sequences. Maps link to levels. Creation involves naming levels and maps with optional padding specifications. Supports EDL file imports for automated map creation. All other features (assets, concepts, breakdown, metadata) remain available.

---

## 1.9 Create a NFT Collection
**URL**: https://kitsu.cg-wire.com/nft/

NFT Collection productions organize sequences and individual items. The interface permits creating sequences and populating them with named collections using customizable padding schemes. Supports asset management, concepts, breakdown, metadata columns, and asset library integration.

---

## 1.10 Meta Columns
**URL**: https://kitsu.cg-wire.com/meta-column/

Metadata columns allow tracking additional information. Six data types: Text, Number, Checkbox, List of values, List of tags, Checklist. For List types, you must specify available values at creation time. Columns can be linked to departments for filtered visibility. Batch updates available. Columns can be stuck for constant visibility while scrolling.

---

## 1.11 Filters
**URL**: https://kitsu.cg-wire.com/filter/

Filters are configured through the search bar. The search bar applies filters instantaneously as characters are typed, except for Feature Film which requires pressing Enter.

Examples: "layout=wip" finds tasks with particular statuses. "[wfa] [retake] -alicia 020" combines multiple criteria.

Filter Builder supports: Task Status filtering, Metadata filtering, Assignment filtering, Thumbnail presence, Priority levels, Ready For status.

Saved filters appear as clickable buttons. Can be renamed, organized into colored groups, or deleted.

---

## 1.12 Production Specific Workflow Settings
**URL**: https://kitsu.cg-wire.com/configure-prod/

Settings accessed through Navigation Menu dropdown. Parameters tab contains FPS and resolution. Warning: If you change the FPS or Resolution after uploading previews, the changes won't be applied; you must reupload.

Tabs available: Task Statuses, Task Types, Asset Types, Status Automation, Preview Backgrounds, Artist Board (controls which statuses appear for artists).

---

## 1.13 Task Assignments
**URL**: https://kitsu.cg-wire.com/assignation/

A task represents a fundamental planning element. Assigning tasks provides clear responsibility, enables workload monitoring, supports time tracking, and facilitates productivity forecasting.

Users must be added to production team before assignment. Assignment via: Global page (click status cell), Bulk assignment (Ctrl/Cmd + click or Shift), Detailed task type page.

Task assignments control user visibility based on role. Vendors require task assignment to view content.

---

## 1.14 Estimates & Team Quotas
**URL**: https://kitsu.cg-wire.com/estimation/

Task estimation enables: Seeing estimated days, Comparing projected vs actual, Adjusting schedules, Keeping artists organized, Enhancing forecasting.

Estimates input in days. Bulk operations with Ctrl/Cmd or Shift. Start dates via calendar picker, due dates calculated automatically.

Quota calculation methods: Timesheet-based (tasks complete on first feedback request) and Status-based (frames distributed across business days).

Priority levels: Normal (default), High, Very High, Emergency.

---

## 1.15 Schedules
**URL**: https://kitsu.cg-wire.com/schedules/

Schedule types:
- **Production Schedule**: Global Gantt chart for milestones linked to contracts
- **Task Type Schedule**: Detailed per-task tracking with color coding (blue=WIP, red=retakes, purple=WFA, green=done)
- **Asset/Shot Schedule**: Individual task timelines on detail pages
- **Studio Schedule**: All productions consolidated (Studio Manager only)
- **Team Schedule**: All personnel with task assignments, adjustable date ranges

Milestones mark significant project points. "Late in Red" highlights overdue tasks.

---

## 1.16 Statuses & Feedback
**URL**: https://kitsu.cg-wire.com/status/

### Comment Panel
Click task status to open right-side panel with POST COMMENT and PUBLISH REVISION tabs. Supports Markdown formatting.

### Tagging
Type "@" + name to notify team members. Type "@" + department to alert entire departments.

### Checklists
Add checklist items within comments. Press Enter to add more entries.

### File Attachments
Upload files or paste screenshots. Validate with "Add file as attachment."

### Bulk Status Updates
Select multiple tasks, use "Change status" from action menu. Comment applied to all selected.

### Artist Board
Board view where statuses become columns and tasks are draggable cards. Configurable per permission role in production settings.

---

## 1.17 Publishes
**URL**: https://kitsu.cg-wire.com/publish/

### Publishing Concepts
Upload concepts via Concepts page. Previews generate automatically.

### Linking Concepts to Assets
Link through Comment Panel's Link button. Multiple concepts can associate with single assets.

### Publishing Previews as Versions
Access PUBLISH REVISION tab in comment panel. Kitsu switches to this tab automatically with WFA status.

Supported formats: Pictures (.png, .jpg, .jpeg, .gif), Videos (.mp4, .mov, .wmv), 3D (.glb). Other formats (.pdf, .zip, .rar, .ma, .mb) require download.

Copy-paste screenshots from clipboard or drag-and-drop files. Multiple images upload simultaneously with navigation between them.

---

## 1.18 Thumbnails
**URL**: https://kitsu.cg-wire.com/thumbnails/

Three methods:
1. **Manual**: Select preview revision, click Preview button, choose frame
2. **Automatic**: Enable in production settings Parameters tab
3. **Batch Upload**: Import multiple via Add Thumbnails button. Files must follow naming convention: sequence_shot (e.g., SEQ_001_SH_001)

---

## 1.19 Reviews
**URL**: https://kitsu.cg-wire.com/review/

### Task Review
Artists request reviews by changing status to WFA. Supports 3D file reviews (.glb wireframes) and HDR lighting checks.

### Drawing & Annotation
Pencil tool for drawing on frames. Text annotations. Tag specific frames with "@" for timestamped references.

### Comparing Versions
Fullscreen side-by-side comparison of task types or versions.

### Concept Reviews
Navigate to concept page, view uploaded items, click status to open comments. Select "Approved" or "Rejected."

### Playlists
Curated version/preview compilations. "Daily pending" adds all WFA tasks from that day. Playback controls: play/pause, speed (x2, x1, x0.50, x0.25), looping, audio waveforms, timecode, frame-by-frame, comparison, annotations. Downloads as Zip, CSV, or MP4.

### Review Room
Collaborative space for synchronized dailies review sessions with real-time feedback.

---

## 1.20 Daily & Weekly Review
**URL**: https://kitsu.cg-wire.com/review-weekly/

Playlists page with list and display sections. Default name is date and hour. Settings for studio/client sharing, shot/asset type, task type tags.

Content selection: Add entire movies, Daily pending (WFA tasks), Whole sequences, Advanced filters (e.g., "animation=wfa").

Kitsu automatically loads the latest uploaded version.

Full review controls: Play/pause, speed adjustment, sound wave, frame-by-frame (arrow keys), looping, comparison, drawing/text annotations, comment panel with history, download options, quality switching, fullscreen.

---

## 1.21 Client Playlists
**URL**: https://kitsu.cg-wire.com/playlist-client/

Select "The Client" under "To Be Shared With" during creation. Clients see: All task versions, Only their own comments, Revision dates (not publishers), Only statuses tagged "Is client Allowed."

Client comments visible only to supervisors and production managers. Supervisors can copy, modify, and publish client feedback.

---

## 1.22 Managing Your Department (Supervisor)
**URL**: https://kitsu.cg-wire.com/supervisor-team/

Supervisors view tasks filtered by department. Assignment limited to department members. Estimation page shows tasks by artist with frame/second counts.

Daily supervision: Contact sheets, filters (exclude completed, "Due This Week").

Team Schedule: View department schedules, adjust dates, reassign work.

Quotas: Amount of work expected per timeframe. Tracked daily, weekly, or monthly.

Timesheets: Monitor team hours, identify unusual patterns.

---

## 1.23 Task Supervision
**URL**: https://kitsu.cg-wire.com/supervisor-tasks/

"My Tasks" for supervisor's own work. Priority sorting default. Board view for drag-and-drop status updates.

"My Checks" for WFA tasks across departments. Review via playlists, task type page contact sheets, or due date filtering.

Concepts page for reviewing concept submissions.

---

## 1.24 Building Production Reports
**URL**: https://kitsu.cg-wire.com/production-report/

News feed for real-time status updates. Statistics as pie charts (sequence, asset type). Count view with percentages per status. CSV export.

Task timing: Due date filtering, Gantt diagram with color coding (grey=on-time, red=late).

Duration vs Estimation analysis comparing projected person-days against actual.

Quota tracking: Timesheet-weighted and status-change-based methods.

Timesheets: Daily hours by task, viewable by day/week/month/year with export.

---

## 1.25 Building Studio Reports
**URL**: https://kitsu.cg-wire.com/studio-report/

"All Tasks" page with production/status/type/person filtering. News Feed with Filters Builder.

Productions dashboard via Load Stats button. Sequence Stats and Asset Types Stats pages.

Studio Occupancy Rate via Team Schedule. Main Schedule consolidating all productions.

---

## 1.26 Custom Actions
**URL**: https://kitsu.cg-wire.com/custom-actions/

Custom actions send HTTP requests to external endpoints. Only studio managers can configure them. Requires: Name, URL, Entity Type, AJAX Option.

JSON payload includes: personid, personemail, projectid, currentpath, currentserver, selection (task IDs), entitytype.

---

## 1.27 Bots
**URL**: https://kitsu.cg-wire.com/bots/

Bots are automated users that perform scripted tasks via API. Don't consume active user licenses. Creation requires: name, optional expiration date, department, role, active status.

System generates JWT token for API authentication. Token regeneration available for security.

---

## 1.28 Kitsu Publisher
**URL**: https://kitsu.cg-wire.com/publisher/

Desktop application connecting DCC tools with Kitsu. Supported DCCs: Blender, Toon Boom Harmony, Unreal Engine. In development: Photoshop, Nuke.

Available for Linux (DEB, RPM, Snap, TAR.GZ, AppImage), Windows (NSIS, MSI, portable), macOS (DMG, PKG, ZIP).

Enables direct timesheet adjustment, screenshot/animation capture, and comment posting.

---

## 1.29 Chat Integration
**URL**: https://kitsu.cg-wire.com/chat-integration/

### Discord
Create bot via developer portal. Enable Public Bot and Server Members Intent. Copy token to Kitsu settings. Invite with "bot" scope and "Send Messages" permission. Users enter Discord username (username#number).

### Slack
Create Slack app, add chat:write:bot permission. Install to workspace, copy token to Kitsu. Users enter Slack Member ID.

### Mattermost
Enable incoming webhooks in System Console. Create webhook with title "Kitsu". Paste URL in Kitsu settings. Users enter Mattermost username.

---

## 1.30 Open Source Setup
**URL**: https://kitsu.cg-wire.com/installation/

Docker quick-start: `docker run -d -p 80:80 --name cgwire cgwire/cgwire`

Default credentials: admin@example.com / mysecretpassword

Development: Node.js 20.18+, Zou on port 5000, optional Events on port 5001. `npm run dev` at http://localhost:8080.

Architecture: Vue.js with Vuex and vue-router.

---

# PART 2: ZOU API DOCUMENTATION (zou.cg-wire.com)

## 2.1 API Overview
**URL**: https://zou.cg-wire.com/api/

REST-based architecture. Authentication via JWT token. POST to /auth/login with email and password. Response includes access_token. All requests require "Authorization: Bearer [token]" header.

Full OpenAPI specs at https://api-docs.kitsu.cloud

---

## 2.2 Backup
**URL**: https://zou.cg-wire.com/backup/

### Database Backup
```
cd /opt/zou/backups
. /etc/zou/zou.env
/opt/zou/zouenv/bin/zou dump-database
```
Output: 2021-03-21-zou-db-backup.sql.gz

### Restoration Options
1. New Database: Create fresh Postgres, decompress and restore (source and target API versions must match)
2. Default Database: Restore to zoudb, terminate existing connections first
3. Rename Approach: Create target database, restore, rename with ALTER DATABASE
4. Environment Variable: Modify /etc/zou/zou.env to point DB_DATABASE to restored database

### File Backup
Object storage: verify replication with provider. Direct storage: backup /opt/zou/previews folder.

---

## 2.3 Configuration
**URL**: https://zou.cg-wire.com/configuration/

### Database
DB_HOST (localhost), DB_PORT (5432), DB_USERNAME (postgres), DB_PASSWORD, DB_DATABASE (zoudb), DB_POOL_SIZE (30), DB_MAX_OVERFLOW (60)

### Key-Value Store
KV_HOST (localhost), KV_PORT (6379)

### Indexer
INDEXER_KEY (masterkey), INDEXER_HOST (localhost), INDEXER_PORT (7700)

### Authentication
AUTH_STRATEGY (auth_local_classic or auth_remote_ldap), SECRET_KEY for token encryption

### Previews
PREVIEW_FOLDER, REMOVE_FILES

### Users
USER_LIMIT (100), MIN_PASSWORD_LENGTH (8), DEFAULT_TIMEZONE, DEFAULT_LOCALE

### Email
MAIL_SERVER, MAIL_PORT (25), MAIL_USERNAME, MAIL_PASSWORD, MAIL_USE_TLS, MAIL_DEFAULT_SENDER, DOMAIN_NAME, DOMAIN_PROTOCOL

### Storage
FS_BACKEND (s3 or swift), FS_BUCKET_PREFIX, S3/Swift credentials

### Job Queue
ENABLE_JOB_QUEUE (True/False), JOB_QUEUE_TIMEOUT

---

## 2.4 Development
**URL**: https://zou.cg-wire.com/development/

Requires Python 3, PostgreSQL, Redis, Meilisearch, FFmpeg.

Database: Docker PostgreSQL with user postgres/mysecretpassword.
Redis: Docker on port 6379.
Meilisearch: v1.8.3 with development env and master key.

Install: Clone repo, virtualenvwrapper, Python 3 venv "zou", pip install -r requirements.txt.

Database init: zou clear-db, zou init-db, zou init-data. Admin creation with email/password.

Server: PREVIEW_FOLDER=$PWD/previews DEBUG=1 FLASK_DEBUG=1 FLASK_APP=zou.app python zou/debug.py

Event server: Gevent-based WebSocket worker on port 5001.

Testing: Separate zoutest database, pytest with DB_DATABASE env var.

---

## 2.5 Events
**URL**: https://zou.cg-wire.com/events/

Create event handlers directory, set EVENT_HANDLERS_FOLDER env var. Handlers implement handle_event(data) function.

Registration via event_map dictionary in __init__.py. Maps event names ("task:start", "task:to-review") to handler modules.

WebSocket listening available through Python client events.

---

## 2.6 File Trees
**URL**: https://zou.cg-wire.com/file_trees/

JSON-based configuration with "working" and "output" contexts. Each context contains: mounting point, root folder, folder path template, file path template.

Templates use angle-bracket tags: <Project>, <Sequence>, <Shot>, <TaskType>. Style options like "lowercase".

---

## 2.7 Indexer
**URL**: https://zou.cg-wire.com/indexer/

Optional Meilisearch for full-text search. Create system user, install package, configure master key (16+ alphanumeric chars).

Systemd service management. Connection via INDEXER_KEY, INDEXER_HOST, INDEXER_PORT env vars.

Verify at /api/status: "indexer-up": "true".

Reset: zou reset-search-index.

---

## 2.8 Jobs
**URL**: https://zou.cg-wire.com/jobs/

Job queue for playlists build and event handlers. Enable with ENABLE_JOB_QUEUE=True.

S3 storage requires: FS_BACKEND=s3, FS_BUCKET_PREFIX, FS_S3_REGION, FS_S3_ENDPOINT, FS_S3_ACCESS_KEY, FS_S3_SECRET_KEY. Install boto3.

RQ worker systemd service at /etc/systemd/system/zou-jobs.service.

---

## 2.9 LDAP
**URL**: https://zou.cg-wire.com/ldap/

Enable with AUTH_STRATEGY=auth_remote_ldap.

Variables: LDAP_HOST, LDAP_PORT (389), LDAP_BASE_DN, LDAP_DOMAIN, LDAP_FALLBACK, LDAP_IS_AD.

Sync: zou sync-with-ldap-server. Requires LDAP_USER, LDAP_PASSWORD, LDAP_EMAIL_DOMAIN, LDAP_EXCLUDED_ACCOUNTS.

When LDAP active, email/name/avatar cannot be modified in Kitsu interface.

---

## 2.10 Log Rotation
**URL**: https://zou.cg-wire.com/log_rotation/

Add RuntimeDirectory=zou and -p /run/zou/zou.pid to systemd unit files.

Logrotate config for 4 log files: daily rotation, 14 files retained, 100M limit, postrotate USR1 signals.

Test: logrotate /etc/logrotate.d/zou --debug

---

## 2.11 Plugins
**URL**: https://zou.cg-wire.com/plugins/

Plugins add routes and database tables. Each requires manifest.toml.

Structure: __init__.py (routes), resources.py (API endpoints), models.py (database), manifest.toml (metadata), migrations/.

CLI commands: install-plugin, uninstall-plugin, create-plugin-skeleton, create-plugin-package, list-plugins, migrate-plugin-db.

UI integration: frontend_studio_enabled or frontend_project_enabled flags.

---

## 2.12 Sync
**URL**: https://zou.cg-wire.com/sync/

Two approaches: Raw database dump/restore, or Zou CLI sync.

CLI: Clear database, reset migrations, upgrade. Then sync base data, project data, or individual projects. Incremental sync supported. File transfer via sync-full-files.

---

## 2.13 Troubleshooting
**URL**: https://zou.cg-wire.com/troubleshooting/

Database: zou upgrade-db. Error logs: /opt/zou/gunicorn_error.log. Status: /api/status endpoint.

Password reset via CLI. Ubuntu requires libjpeg-dev. systemctl enable for boot. Job queue errors in zou-jobs.service logs.

DB connections: DB_POOL_SIZE (30), DB_MAX_OVERFLOW (60).

Playlist issues: Resolution inconsistencies, disk space. Version upgrades: stepwise recommended.

---

# PART 3: GAZU PYTHON CLIENT (gazu.cg-wire.com)

## 3.1 Getting Started
**URL**: https://gazu.cg-wire.com/intro/

Install: pip install gazu. Development: pip install git+https://github.com/cgwire/cgwire-api-client.git

Configuration:
```python
import gazu
gazu.client.set_host("https://zou-server-url/api")
gazu.log_in("user@mail.com", "userpassword")
```

Bot authentication: gazu.set_token("verylongtoken")

---

## 3.2 Available Data
**URL**: https://gazu.cg-wire.com/data/

All model instances return as Python dictionaries. Universal fields: id, created_at, updated_at, type.

30+ data models: Assets, Shots, Sequences, Episodes, Projects, Asset instances/types, Entity types, Output types, Tasks, Task status/types, Time spents, Working/Output/Preview files, File status, Persons, Comments, Notifications, Subscriptions, Playlists, Software, Search filters, Metadata, Events.

Many models include free JSON data fields for custom metadata and Shotgun integration identifiers.

---

## 3.3 Examples
**URL**: https://gazu.cg-wire.com/examples/

User Operations: gazu.user.all_tasks_to_do()
Task Management: gazu.task.add_comment(), gazu.task.add_preview(), gazu.task.publish_preview()
Personnel: Retrieve by full name or desktop login
Projects: gazu.project.new_project(), filtering for open projects
Assets: Creation, updates, deletion, retrieval by project/type
Shots/Sequences: Hierarchical temporal entity management
Files: Working files, output files, software definitions, file tree templates
Time Tracking: Date-based tracking methods

---

## 3.4 Raw Functions
**URL**: https://gazu.cg-wire.com/raw/

Low-level API requests: is_host_up(), get_host(), set_host().

Authentication: login, logout, get current user, check API version.

HTTP methods: GET, POST, PUT, DELETE to API paths.

Multi-client support for simultaneous server connections.

File operations: Upload and download.

Model functions: Fetch all (with pagination), fetch one, fetch first, create.

---

## 3.5 Caching
**URL**: https://gazu.cg-wire.com/cache/

Enable: gazu.cache.enable(). Disable: gazu.cache.disable().

Clear: gazu.cache.clear_all() or per-function clear_cache().

Per-function: disable_cache(), set_expire(120) in seconds.

Monitor: get_cache_infos().

---

## 3.6 Events
**URL**: https://gazu.cg-wire.com/events/

Listen via callback function in separate thread. Setup: set_host(), set_event_host(), log_in(), events.init(), events.add_listener(), events.run_client().

Generic events: model:new, model:update, model:delete for each data type.

Special events: asset-instance operations, thumbnail settings, preview-file actions, shot casting updates, task management (assign, unassign, status-changed).

Recent events via gazu.client.get() with page_size, before, after, only_files filters.

---

## 3.7 Specifications
**URL**: https://gazu.cg-wire.com/specs/

Modules: asset, task, shot/scene, person, project, files, cache, client, events.

Consistent patterns for CRUD operations. File management with path generation. Real-time events via WebSocket. CSV import/export. Playlist management. Time tracking. Casting and asset instances. Task commenting with attachments.

---

## 3.8 DCC Utils
**URL**: https://gazu.cg-wire.com/dccutils/

Abstracts DCC features for Blender, Maya, Houdini. Install: pip install dccutils.

SoftwareContext class methods: get_available_renderers(), get_cameras(), get_current_color_space(), get_current_project_path(), get_dcc_name(), get_dcc_version(), get_extensions(), push_state()/pop_state(), set_camera(), set_current_color_space(), take_render_animation(), take_render_screenshot(), take_viewport_animation(), take_viewport_screenshot().

---

# PART 4: KITSU REST API REFERENCE (api-docs.kitsu.cloud)

## 4.1 API Overview
**URL**: https://api-docs.kitsu.cloud/

Kitsu API v1.0.21. REST endpoints requiring JWT authentication. License: AGPL 3.0.

### Authentication
JWT Authorization via "Authorization: Bearer {token}" header. Token format: xxxxx.yyyyy.zzzzz

### 22 Authentication Endpoints
Login/Logout, User registration, Password management, Token refresh, TOTP, Email OTP, FIDO devices, Recovery codes, SAML SSO.

### 30 API Endpoint Categories

| Category | Description |
|----------|-------------|
| Authentication | Login, Register, TOTP, FIDO, SAML SSO |
| Assets | Create, retrieve, cast, link assets |
| Breakdown | Casting, entity links, asset instances |
| Chat | Messages, details, deletion |
| Comments | Task comments, attachments, replies |
| Concepts | Create, retrieve, preview files |
| CRUD | Persons, Projects, Tasks, Departments |
| Departments | Software licenses, hardware items |
| Edits | Create, manage, task types |
| Entities | News, previews, time tracking |
| Events | Activity logs, login records |
| Export | CSV export for assets, shots, tasks |
| Files | Working files, output files, paths |
| Import | Shotgun, CSV, OTIO, Kitsu formats |
| Index | API status, configuration, usage stats |
| News | Project announcements |
| Persons | User management, time tracking |
| Playlists | Builds, downloads, entity management |
| Previews | Thumbnails, media files, annotations |
| Projects | Team, budgets, schedules, milestones |
| Search | Entity search capabilities |
| Shots | Episodes, sequences, scenes, casting |
| Tasks | Assignment, time spent, comments |
| User | Context, filters, notifications, subscriptions |

OpenAPI specs downloadable in JSON and YAML formats.

---

# PART 5: NEW DEVELOPER DOCUMENTATION (dev.kitsu.cloud)

## 5.1 Why Kitsu
**URL**: https://dev.kitsu.cloud/start-here/why-kitsu

Open-source production tracking for animation, VFX, and game studios. Single source of truth for all production entities. Production-specific task states. Review and approval features. Scalable from small teams to large studios. Community-driven development by CGWire.

---

## 5.2 Docker Setup
**URL**: https://dev.kitsu.cloud/start-here/docker

NOT recommended for production. Basic: docker run --init -ti --rm -p 80:80 -p 1080:1080 --name cgwire cgwire/cgwire

Persistence: Mount zou-storage volumes for /var/lib/postgresql and /opt/zou/previews.

Docker Compose available. Default: admin@example.com / mysecretpassword. Kitsu at :80, webmail at :1080.

Upgrade: docker exec -ti cgwire sh -c "/opt/zou/env/bin/zou upgrade-db"

---

## 5.3 Authentication Guide
**URL**: https://dev.kitsu.cloud/guides/authentication

All endpoints require JWT. User auth: gazu.log_in(email, password). Bot auth: gazu.set_token(token).

User data retrieval: Open projects, asset types, assets, sequences, shots, scenes, tasks.

Session logout deletes tokens from server.

Security: Never hardcode secrets, never store JWTs, use environment variables. Regenerate compromised bot tokens.

---

## 5.4 Permissions and Roles
**URL**: https://dev.kitsu.cloud/guides/permissions-roles

Six roles with fixed database codes:
- admin: Studio Manager (full system access)
- manager: Production Manager (production-level control)
- supervisor: Department Lead (department-level access)
- user: Artist (assigned tasks only)
- client: External Reviewer (limited read, client playlists)
- vendor: External Studio (assigned tasks only)

Roles assigned during user creation or updated via API.

---

## 5.5 Production Setup
**URL**: https://dev.kitsu.cloud/guides/production-setup

Create project with name, type, style. Add team members by email. Shot structure: episodes > sequences > shots. Asset types and individual assets. Task types (modeling, rigging, animation) and statuses (to do, WIP, review, approved). Custom metadata descriptors via data attribute.

---

## 5.6 Task Tracking
**URL**: https://dev.kitsu.cloud/guides/task-tracking

Creating task types and statuses. Generating tasks for entities. User workload: gazu.user.all_tasks_to_do(). Time tracking: gazu.task.set_time_spent(), gazu.task.add_time_spent(). Schedule management: start/due dates, estimates in seconds, priorities.

Task fields: priority, duration, estimation, completion_rate, retake_count, start_date, due_date, real_start_date, end_date, last_comment_date.

---

## 5.7 Review Engine (Publishing)
**URL**: https://dev.kitsu.cloud/guides/publishing

Three elements: Comments, Preview versions, Playlists.

Comments: gazu.task.add_comment() with task, status, text, person, checklist, attachments.

Previews: File uploads linked to comments. Publish shortcut combines posting and preview linking.

Status changes via comments. Retrieve history per project or per task.

Download previews and thumbnails. Create playlists with project, name, client visibility, entity type.

---

## 5.8 Asset Management
**URL**: https://dev.kitsu.cloud/guides/asset-management

Three file types: Working files (artist's editable source), Output files (exports/renders), Preview files (for reviews in Kitsu).

File tree configuration per project. Software management. Working files: list, retrieve, revisions, create, generate paths, upload. Output files: types, retrieval, listing, revisions, creation, paths.

---

## 5.9 Bot Automation
**URL**: https://dev.kitsu.cloud/guides/bot-automation

Bots don't count as active users. Created in Admin > Bots. Required fields: name, optional expiration, department, role, active status. System displays API token upon creation.

Example: Retrieve project with gazu using bot token.

---

## 5.10 Event Listeners
**URL**: https://dev.kitsu.cloud/guides/event-listeners

Naming pattern: entity:action. CRUD events: new, update, delete. Callback data includes entity ID and project ID.

Event categories cover: Assets, Shots, Sequences, Episodes, Tasks, Comments, Preview files, Working files, Personnel, Projects, Edits, Concepts, Playlists, Notifications, Chat, News, Budgets, Schedules, Time tracking, Entity links, Build jobs.

---

## 5.11 Search
**URL**: https://dev.kitsu.cloud/guides/search

Raw retrieval: fetch_all(), fetch_one(), fetch_first(), create().

Search by API path: gazu.client.get("data/projects").

Pagination: page_size, before, after, only_files.

Full-text search: gazu.search.search_entities() across persons, assets, shots.

---

## 5.12 Custom Actions
**URL**: https://dev.kitsu.cloud/guides/custom-actions

HTTP requests to external endpoints. Studio Managers only. Configuration: Name, URL, Entity Type, Use AJAX.

Payload: personid, personemail, projectid, currentpath, currentserver, selection (task IDs), entitytype.

---

## 5.13 Session Management
**URL**: https://dev.kitsu.cloud/guides/session-management

Context manager: gazu.create_session(host, email, password) with automatic cleanup. Multiple instances via nested context managers. TOTP support via totp parameter.

---

## 5.14 Async Client
**URL**: https://dev.kitsu.cloud/guides/async

Install: pip install gazu[async]. Built on aiohttp. Use asyncio.gather() for concurrent operations.

Key differences: No global default client, uses aiohttp.ClientSession, requires await syntax, async with for context management.

---

## 5.15 Logging
**URL**: https://dev.kitsu.cloud/guides/logging

Set GAZU_DEBUG=true for HTTP request logging. Code-based configuration via logging module. File logging with basicConfig(). Sensitive data (passwords, tokens) automatically excluded. Async module uses separate "gazu.aio" logger.

---

## 5.16 Caching Guide
**URL**: https://dev.kitsu.cloud/guides/caching

Enable: gazu.cache.enable(). Disable: gazu.cache.disable(). Clear: gazu.cache.clear_all(). Per-function: clear_cache(), disable_cache(), set_expire(seconds), get_cache_infos().

All read-only operations cached when enabled.

---

## 5.17 Self-Hosting Architecture
**URL**: https://dev.kitsu.cloud/self-hosting/architecture

Frontend: Vue.js with Vuex and vue-router. Backend: Python Flask with Flask Restful API, Flask events service (WebSocket), PostgreSQL, Redis, FFmpeg, Meilisearch. Nginx reverse proxy.

---

## 5.18 Hardware Requirements
**URL**: https://dev.kitsu.cloud/self-hosting/hardware-requirements

| Users | Cores | RAM |
|-------|-------|-----|
| 1-10 | 2 | 4 GB |
| 11-30 | 2 | 8 GB |
| 31-80 | 4 | 15 GB |
| 81-200 | 8 | 30 GB |

Disk space: Factor of x2.5-x3 of all files sent. Separate database VM and PREVIEW_FOLDER volume recommended.

---

## 5.19 Self-Hosting Setup
**URL**: https://dev.kitsu.cloud/self-hosting/setup

Requires Ubuntu 22.04+, Python 3.10+, PostgreSQL 9.2+, Redis 2.0+, Nginx, FFmpeg.

Zou backend: Install dependencies, configure PostgreSQL, set env vars (including random SECRET_KEY), zou init-db, configure Gunicorn (main + events), Nginx reverse proxy.

Kitsu frontend: Download built release from GitHub, configure Nginx to serve static files and route API requests.

Updates: Upgrade Zou package, zou upgrade-db, restart services. Create admin user, optionally seed data.

---

## 5.20 Environment Variables
**URL**: https://dev.kitsu.cloud/self-hosting/environment-variables

Complete reference: Database (DB_*), Redis (KV_*), Meilisearch (INDEXER_*), Authentication (AUTH_STRATEGY, SECRET_KEY), Previews (PREVIEW_FOLDER), Users (USER_LIMIT, MIN_PASSWORD_LENGTH), Email (MAIL_*), Storage (FS_* for S3/Swift), LDAP (LDAP_*), Job Queue (ENABLE_JOB_QUEUE), Misc (TMP_DIR, DEBUG).

---

## 5.21 Full-Text Search
**URL**: https://dev.kitsu.cloud/self-hosting/full-text-search

Optional Meilisearch. Install via APT, create /opt/meilisearch directory, configure master key. Systemd service. Configure INDEXER_KEY, INDEXER_HOST, INDEXER_PORT in zou.env.

Verify: /api/status shows "indexer-up": "true". Reset: zou reset-search-index.

---

## 5.22 Preview Storage (S3)
**URL**: https://dev.kitsu.cloud/self-hosting/preview-storage

FS_BACKEND=s3, FS_BUCKET_PREFIX, FS_S3_REGION, FS_S3_ENDPOINT, FS_S3_ACCESS_KEY, FS_S3_SECRET_KEY. Install boto3.

---

## 5.23 Job Queue
**URL**: https://dev.kitsu.cloud/self-hosting/job-queue

Handles playlist builds and event handlers. ENABLE_JOB_QUEUE=True. RQ worker systemd service.

---

## 5.24 LDAP
**URL**: https://dev.kitsu.cloud/self-hosting/lightweight-directory-access-protocol

AUTH_STRATEGY=auth_remote_ldap. LDAP_HOST, LDAP_PORT, LDAP_BASE_DN, LDAP_DOMAIN, LDAP_FALLBACK, LDAP_IS_AD. Sync with zou sync-with-ldap-server.

---

## 5.25 Logging (Self-Hosting)
**URL**: https://dev.kitsu.cloud/self-hosting/logging

Add RuntimeDirectory and PID files to systemd units. Logrotate: daily, 14 files, 100M limit, USR1 postrotate. Test: logrotate --debug.

---

## 5.26 Backup
**URL**: https://dev.kitsu.cloud/self-hosting/backup

Database: zou dump-database. Restore: API versions must match. Preview files: backup /opt/zou/previews.

---

## 5.27 Data Migration
**URL**: https://dev.kitsu.cloud/self-hosting/data-migration

Raw: Dump and restore database + move preview files.

CLI: zou clear-db, zou reset-migrations, zou upgrade-db. Then sync base data, project data, files. Incremental sync supported. Deletions not handled.

---

## 5.28 Troubleshooting
**URL**: https://dev.kitsu.cloud/self-hosting/troubleshooting

Database: zou upgrade-db. Logs: /opt/zou/gunicorn_error.log. Status: /api/status. Password: zou change-password. Ubuntu: libjpeg-dev. Boot: systemctl enable. Job logs: journalctl -u zou-jobs.service. DB connections: DB_POOL_SIZE, DB_MAX_OVERFLOW. Playlists: Resolution mismatches, disk space. Upgrades: Incremental required.

---

## 5.29 CLI Reference
**URL**: https://dev.kitsu.cloud/references/cli

Commands: version, init-db, is-db-ready, migrate-db, downgrade-db, upgrade-db, stamp-db, clear-db, reset-migrations, create-admin, change-password, set-person-as-active, disable-two-factor-authentication, clean-auth-tokens, clear-all-auth-tokens, sync-with-ldap-server, create-bot, init-data, remove-old-data, clean-tasks-data, reset-search-index, search-asset, sync-full, sync-full-files, sync-changes, sync-file-changes, dump-database, clear-memory-cache, install-plugin, uninstall-plugin, create-plugin-skeleton, create-plugin-package, list-plugins, migrate-plugin-db.

---

## 5.30 Data Models Reference
**URL**: https://dev.kitsu.cloud/references/data-models

All entities include id, created_at, updated_at.

**Project**: name, code, FPS (25 default), resolution (1920x1080), production_type (short/featurefilm/tvshow), style (2d/3d/2d3d/ar/vfx).

**Entity**: Assets, shots, sequences, episodes, scenes with status (standby/running/complete/canceled), frame counts, casting info.

**Task**: priority, difficulty, duration, estimation, dates, assignees.

**Comment**: text, replies, checklists, pinned, mentions, departments, attachments.

**PreviewFile**: revision, validation (validated/rejected/neutral), dimensions, duration, processing status.

**Person**: auth settings (TOTP, OTP, FIDO), roles (user/admin/supervisor/manager/client/vendor), position, seniority.

Additional: TaskType, TaskStatus, EntityType, EntityLink, AssetInstance, WorkingFile, OutputFile, Playlist, BuildJob, Notification, Chat, MetadataDescriptor, ScheduleItem, Milestone, Budget, Software, CustomAction, SearchFilter, ApiEvent, Plugin.

---

## 5.31 Gazu SDK Reference
**URL**: https://dev.kitsu.cloud/references/gazu

Modules: Authentication (log_in, set_host, log_out), Asset (new_asset, all_assets), Files (build_working_file_path, new_working_file), Project (new_project, get_team), Task (add_comment, publish_preview), Shot/Sequence, Casting (update_shot_casting), Person (new_person, all_persons), Playlist (new_playlist).

Features: Caching with decorators, Pagination, Progress callbacks, Metadata support, MFA support.

---

## 5.32 Plugin Development
**URL**: https://dev.kitsu.cloud/recipes/make-your-plugin

Plugin structure: manifest.toml, __init__.py (routes/hooks), models.py (SQLAlchemy), resources.py (Flask-RESTful), services.py, frontend/ (Vue 3 or Nuxt), migrations/, tests/.

Models: Inherit db.Model + BaseMixin + SerializerMixin. Table names prefixed plugin_<id>_. Never modify core models. Implement present() method.

Routes: @jwt_required() on all endpoints. Admin checks for sensitive operations. ArgsMixin for UUID validation.

Frontend: Vue 3 + Vite recommended. createWebHashHistory, base: './'. Context via URL query params (production_id, episode_id).

Testing: DB_DATABASE=zoudb-test. Extend ApiDBTestCase.

Deployment: pip install -e (dev), npm run build, create-plugin-package, install-plugin.

---

## 5.33 Import Studio Team Recipe
**URL**: https://dev.kitsu.cloud/recipes/import-studio-team

CSV import of team data. Steps: Load CSV, authenticate (use automation account with env vars), create artists checking for existing users (idempotent), execute workflow.

---

## 5.34 File Management Recipe
**URL**: https://dev.kitsu.cloud/recipes/file-management

JSON file tree config with "working" and "output" contexts. Templates with <Project>, <Sequence>, <Shot> etc. tags.

Functions: update_project_file_tree(), build_working_file_path(), build_entity_output_file_path(), new_working_file() (auto-incrementing revisions), new_entity_output_file().

---

## 5.35 Progress Callbacks
**URL**: https://dev.kitsu.cloud/recipes/progress-callbacks

Callback(bytes_read, total). Upload total from file size, download from Content-Length.

Supported: Working file upload/download, avatar upload, project thumbnails, preview files, comment attachments, all preview variants.

---

## 5.36 AI Agent Quickstart
**URL**: https://dev.kitsu.cloud/start-here/agent-quickstart

Authenticate with bot tokens. Use Python SDK or REST API.

Core values: Artist empowerment, production visibility, distributed collaboration, efficiency, communication, ease of use.

Guidelines: Read first, write second. Never create/update/delete without explicit user intent. Confirm destructive actions. Respect permissions. Preserve human decisions. Minimize disruptions.

Conventions: UUID identification, consistent naming, caching to reduce API load, events over polling, secure secrets.

---

## 5.37 Migrate to Kitsu
**URL**: https://dev.kitsu.cloud/start-here/migrate-to-kitsu

Data architecture understanding required first. Pre-migration: Audit data, map entities, normalize naming, decide on historical data, export as JSON/CSV.

Migration order: Structural data first (departments, task types, statuses), then production content.

Scripts commonly in Python: Export, transform to Kitsu schema, create/update via API, batch loading.

Validate with dashboard or automated tests. Multiple dry runs. Go-live: Freeze legacy, final migration, transition, archive. CGWire offers professional migration services.

---

## 5.38 Integrations

### Blender (dev.kitsu.cloud/integrations/dcc/blender)
Kitsu Publisher desktop app. Available for Blender, Toon Boom Harmony, Unreal Engine. Maya and Photoshop in development. Multi-platform installers. DCC connectors via ZIP. Node.js >=16.11 for development.

### Toon Boom Harmony (dev.kitsu.cloud/integrations/dcc/toon-boom-harmony)
Same Kitsu Publisher. Windows connector via install.ps1 PowerShell script. macOS coming soon.

### Slack (dev.kitsu.cloud/integrations/messaging/slack)
Create Slack app, add chat:write:bot permission, install to workspace, copy token to Kitsu settings. Users provide Slack Member ID.

### Discord (dev.kitsu.cloud/integrations/messaging/discord)
Create bot via developer portal, enable Public Bot and Server Members Intent, copy token to Kitsu. Invite with bot scope + Send Messages. Users enter username#number.

### Mattermost (dev.kitsu.cloud/integrations/messaging/mattermost)
Enable webhooks in System Console. Create incoming webhook. Paste URL in Kitsu settings. Users enter Mattermost username.

---

## 5.39 Contributing
**URL**: https://dev.kitsu.cloud/open-source/contributing

Bug reports: GitHub issues. Feature requests: Canny page. Translations: POEditor. Code contributions follow C4 contract. Front-end requires style guide compliance and CGWire designer validation.

---

## 5.40 Development Environment
**URL**: https://dev.kitsu.cloud/open-source/development-environment-quickstart

Prerequisites: Node.js 20.18+, Zou on :5000, optional Events on :5001.

Frontend: Clone kitsu repo, npm install, npm run dev at :8080.

Backend: Clone zou, virtualenvwrapper, Python 3 venv, pip install -r requirements. PostgreSQL zoudb, Redis, optional Meilisearch.

Init: zou clear-db, zou init-db, zou init-data, create admin.

Run: PREVIEW_FOLDER=$PWD/previews DEBUG=1 FLASK_APP=zou.app python zou/debug.py

Events: Gunicorn with GeventWebSocket on :5001.

Testing: Separate zoutest database. DB_DATABASE=zoutest py.test.

---

## 5.41 Self-Hosting vs Cloud
**URL**: https://dev.kitsu.cloud/self-hosting/vs-cloud-hosting

Cloud: Fast setup, managed infrastructure, automatic upgrades, daily backups, priority support. Minimal DevOps needed.

Self-hosting: Full control, customization, no vendor lock-in. Requires DevOps expertise.

Comparison across: Setup, Deployment, Infrastructure, Operations, DevOps Requirements, Scalability, Performance, Maintenance, Customization, Security, Compliance, Reliability, Cost, Portability, Support.
