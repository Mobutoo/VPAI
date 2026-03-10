// Event Router — Receives flash-agent events, routes to notification channels.
//
// POST /api/events            <- flash-agent (all clients, via NetBird)
//   -> PostgreSQL (history, read/unread)
//   -> SSE endpoint (real-time notifications)
//   -> Zammad API (if severity >= warning)
//   -> Brevo API (if client enabled email)
//   -> Telegram API (if client configured bot)
//   -> Client Health Score update
//
// POST /api/announcements     <- portail admin (create announcement)
// GET  /api/announcements     <- portail (list active announcements)
// PUT  /api/announcements/{id}/archive <- portail admin (archive)
//
// POST   /api/gatus/endpoints <- portail admin (add monitored service)
// GET    /api/gatus/endpoints <- portail (list dynamic endpoints)
// PUT    /api/gatus/endpoints/{id} <- portail admin (update endpoint)
// DELETE /api/gatus/endpoints/{id} <- portail admin (remove endpoint)
//
//   -> PostgreSQL (announcements + gatus_endpoints tables)
//   -> Gatus config file rewrite + container restart
package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/redis/go-redis/v9"
)

type Event struct {
	ClientID  string            `json:"client_id"`
	Type      string            `json:"type"` // info, warning, critical
	Category  string            `json:"category"`
	Title     string            `json:"title"`
	Message   string            `json:"message"`
	Metadata  map[string]string `json:"metadata,omitempty"`
	Timestamp time.Time         `json:"timestamp"`
}

type Announcement struct {
	ID        int64     `json:"id"`
	Type      string    `json:"type"`    // information, warning, outage, operational
	Message   string    `json:"message"`
	Archived  bool      `json:"archived"`
	CreatedAt time.Time `json:"created_at"`
}

// GatusEndpoint represents a dynamically managed Gatus monitoring endpoint.
type GatusEndpoint struct {
	ID         int64    `json:"id"`
	Name       string   `json:"name"`
	Group      string   `json:"group"`
	URL        string   `json:"url"`
	Interval   string   `json:"interval"`   // e.g. "60s", "30s"
	Conditions []string `json:"conditions"` // e.g. ["[STATUS] == 200"]
	Enabled    bool     `json:"enabled"`
	CreatedAt  time.Time `json:"created_at"`
}

type SSEClient struct {
	ClientID string
	Channel  chan []byte
}

// gatusAnnouncement is used internally to pass data to the config rewriter.
type gatusAnnouncement struct {
	Type      string
	Message   string
	CreatedAt time.Time
}

// gatusEndpointRow is used internally to pass endpoint data to the config rewriter.
type gatusEndpointRow struct {
	Name, Group, URL, Interval string
	Conditions                 []string
}

var (
	db         *pgxpool.Pool
	rdb        *redis.Client
	sseClients = make(map[string][]*SSEClient)
	sseMu      sync.RWMutex

	validAnnouncementTypes = map[string]bool{
		"information": true, "warning": true,
		"outage": true, "operational": true,
	}
)

func main() {
	ctx := context.Background()

	// Database
	dbURL := os.Getenv("DATABASE_URL")
	if dbURL == "" {
		log.Fatal("DATABASE_URL required")
	}

	var err error
	db, err = pgxpool.New(ctx, dbURL)
	if err != nil {
		log.Fatalf("Failed to connect to database: %v", err)
	}
	defer db.Close()

	// Run migrations
	if err := migrate(ctx); err != nil {
		log.Fatalf("Migration failed: %v", err)
	}

	// Redis
	redisURL := os.Getenv("REDIS_URL")
	if redisURL != "" {
		opt, _ := redis.ParseURL(redisURL)
		rdb = redis.NewClient(opt)
	}

	// HTTP server
	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", handleHealth)
	mux.HandleFunc("POST /api/events", handleEvent)
	mux.HandleFunc("GET /api/events/stream/{clientID}", handleSSE)
	mux.HandleFunc("GET /api/events/{clientID}", handleGetEvents)
	mux.HandleFunc("PUT /api/events/{id}/read", handleMarkRead)
	mux.HandleFunc("GET /api/health-score/{clientID}", handleHealthScore)

	// Announcements API
	mux.HandleFunc("POST /api/announcements", handleCreateAnnouncement)
	mux.HandleFunc("GET /api/announcements", handleListAnnouncements)
	mux.HandleFunc("PUT /api/announcements/{id}/archive", handleArchiveAnnouncement)

	// Gatus Endpoints API
	mux.HandleFunc("POST /api/gatus/endpoints", handleCreateGatusEndpoint)
	mux.HandleFunc("GET /api/gatus/endpoints", handleListGatusEndpoints)
	mux.HandleFunc("PUT /api/gatus/endpoints/{id}", handleUpdateGatusEndpoint)
	mux.HandleFunc("DELETE /api/gatus/endpoints/{id}", handleDeleteGatusEndpoint)

	port := os.Getenv("PORT")
	if port == "" {
		port = "8092"
	}

	log.Printf("Event Router listening on :%s", port)
	log.Fatal(http.ListenAndServe(":"+port, mux))
}

func migrate(ctx context.Context) error {
	_, err := db.Exec(ctx, `
		CREATE TABLE IF NOT EXISTS events (
			id BIGSERIAL PRIMARY KEY,
			client_id TEXT NOT NULL,
			type TEXT NOT NULL,
			category TEXT NOT NULL DEFAULT '',
			title TEXT NOT NULL,
			message TEXT NOT NULL DEFAULT '',
			metadata JSONB DEFAULT '{}',
			read BOOLEAN DEFAULT FALSE,
			created_at TIMESTAMPTZ DEFAULT NOW()
		);
		CREATE INDEX IF NOT EXISTS idx_events_client ON events(client_id, created_at DESC);
		CREATE INDEX IF NOT EXISTS idx_events_unread ON events(client_id, read) WHERE NOT read;

		CREATE TABLE IF NOT EXISTS notification_prefs (
			client_id TEXT PRIMARY KEY,
			email_enabled BOOLEAN DEFAULT FALSE,
			email_address TEXT DEFAULT '',
			email_levels TEXT[] DEFAULT '{"critical","warning"}',
			telegram_enabled BOOLEAN DEFAULT FALSE,
			telegram_bot_token TEXT DEFAULT '',
			telegram_chat_id TEXT DEFAULT '',
			telegram_levels TEXT[] DEFAULT '{"critical"}',
			updated_at TIMESTAMPTZ DEFAULT NOW()
		);

		CREATE TABLE IF NOT EXISTS health_scores (
			client_id TEXT PRIMARY KEY,
			score INTEGER DEFAULT 100,
			ticket_count_30d INTEGER DEFAULT 0,
			uptime_pct REAL DEFAULT 100.0,
			avg_resolution_hours REAL DEFAULT 0,
			sentiment_score REAL DEFAULT 1.0,
			updated_at TIMESTAMPTZ DEFAULT NOW()
		);

		CREATE TABLE IF NOT EXISTS announcements (
			id BIGSERIAL PRIMARY KEY,
			type TEXT NOT NULL DEFAULT 'information',
			message TEXT NOT NULL,
			archived BOOLEAN DEFAULT FALSE,
			created_at TIMESTAMPTZ DEFAULT NOW()
		);
		CREATE INDEX IF NOT EXISTS idx_announcements_active
			ON announcements(archived, created_at DESC) WHERE NOT archived;

		CREATE TABLE IF NOT EXISTS gatus_endpoints (
			id BIGSERIAL PRIMARY KEY,
			name TEXT NOT NULL,
			grp TEXT NOT NULL DEFAULT 'Custom',
			url TEXT NOT NULL,
			interval TEXT NOT NULL DEFAULT '60s',
			conditions JSONB NOT NULL DEFAULT '["[STATUS] == 200"]',
			enabled BOOLEAN DEFAULT TRUE,
			created_at TIMESTAMPTZ DEFAULT NOW()
		);
		CREATE INDEX IF NOT EXISTS idx_gatus_endpoints_enabled
			ON gatus_endpoints(enabled) WHERE enabled;
	`)
	return err
}

func handleHealth(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	w.Write([]byte(`{"status":"ok"}`))
}

func handleEvent(w http.ResponseWriter, r *http.Request) {
	var event Event
	body, err := io.ReadAll(r.Body)
	if err != nil {
		http.Error(w, "Bad request", http.StatusBadRequest)
		return
	}

	if err := json.Unmarshal(body, &event); err != nil {
		http.Error(w, "Invalid JSON", http.StatusBadRequest)
		return
	}

	if event.ClientID == "" || event.Type == "" || event.Title == "" {
		http.Error(w, "client_id, type, and title required", http.StatusBadRequest)
		return
	}

	if event.Timestamp.IsZero() {
		event.Timestamp = time.Now()
	}

	ctx := r.Context()

	// 1. Store in database
	metadataJSON, _ := json.Marshal(event.Metadata)
	var eventID int64
	err = db.QueryRow(ctx,
		`INSERT INTO events (client_id, type, category, title, message, metadata, created_at)
		 VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id`,
		event.ClientID, event.Type, event.Category, event.Title, event.Message,
		metadataJSON, event.Timestamp,
	).Scan(&eventID)
	if err != nil {
		log.Printf("Failed to store event: %v", err)
		http.Error(w, "Storage error", http.StatusInternalServerError)
		return
	}

	// 2. SSE broadcast to client
	eventJSON, _ := json.Marshal(map[string]interface{}{
		"id": eventID, "type": event.Type, "category": event.Category,
		"title": event.Title, "message": event.Message, "timestamp": event.Timestamp,
	})
	broadcastSSE(event.ClientID, eventJSON)

	// 3. Route to channels (async)
	go routeEvent(event)

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"status": "accepted", "event_id": eventID,
	})
}

func routeEvent(event Event) {
	ctx := context.Background()

	// Zammad ticket if severity >= warning
	if event.Type == "warning" || event.Type == "critical" {
		createZammadTicket(event)
	}

	// Check notification preferences
	var prefs struct {
		EmailEnabled    bool
		EmailAddress    string
		EmailLevels     []string
		TelegramEnabled bool
		TelegramToken   string
		TelegramChatID  string
		TelegramLevels  []string
	}

	err := db.QueryRow(ctx,
		`SELECT email_enabled, email_address, email_levels,
		        telegram_enabled, telegram_bot_token, telegram_chat_id, telegram_levels
		 FROM notification_prefs WHERE client_id = $1`, event.ClientID,
	).Scan(&prefs.EmailEnabled, &prefs.EmailAddress, &prefs.EmailLevels,
		&prefs.TelegramEnabled, &prefs.TelegramToken, &prefs.TelegramChatID, &prefs.TelegramLevels)

	if err != nil {
		if event.Type == "critical" {
			sendTelegramOps(event)
		}
		return
	}

	// Email via Brevo
	if prefs.EmailEnabled && contains(prefs.EmailLevels, event.Type) {
		sendBrevoEmail(prefs.EmailAddress, event)
	}

	// Client Telegram
	if prefs.TelegramEnabled && contains(prefs.TelegramLevels, event.Type) {
		sendTelegram(prefs.TelegramToken, prefs.TelegramChatID, event)
	}

	// Ops Telegram for critical
	if event.Type == "critical" {
		sendTelegramOps(event)
	}

	// Update health score
	updateHealthScore(ctx, event.ClientID, event.Type)
}

func broadcastSSE(clientID string, data []byte) {
	sseMu.RLock()
	defer sseMu.RUnlock()
	for _, c := range sseClients[clientID] {
		select {
		case c.Channel <- data:
		default:
		}
	}
}

func handleSSE(w http.ResponseWriter, r *http.Request) {
	clientID := r.PathValue("clientID")
	if clientID == "" {
		http.Error(w, "clientID required", http.StatusBadRequest)
		return
	}

	flusher, ok := w.(http.Flusher)
	if !ok {
		http.Error(w, "Streaming not supported", http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")
	w.Header().Set("Access-Control-Allow-Origin", "*")

	client := &SSEClient{ClientID: clientID, Channel: make(chan []byte, 64)}

	sseMu.Lock()
	sseClients[clientID] = append(sseClients[clientID], client)
	sseMu.Unlock()

	defer func() {
		sseMu.Lock()
		clients := sseClients[clientID]
		for i, c := range clients {
			if c == client {
				sseClients[clientID] = append(clients[:i], clients[i+1:]...)
				break
			}
		}
		sseMu.Unlock()
	}()

	for {
		select {
		case data := <-client.Channel:
			fmt.Fprintf(w, "data: %s\n\n", data)
			flusher.Flush()
		case <-r.Context().Done():
			return
		}
	}
}

func handleGetEvents(w http.ResponseWriter, r *http.Request) {
	clientID := r.PathValue("clientID")
	ctx := r.Context()

	rows, err := db.Query(ctx,
		`SELECT id, type, category, title, message, read, created_at
		 FROM events WHERE client_id = $1 ORDER BY created_at DESC LIMIT 100`,
		clientID)
	if err != nil {
		http.Error(w, "Query error", http.StatusInternalServerError)
		return
	}
	defer rows.Close()

	var events []map[string]interface{}
	for rows.Next() {
		var id int64
		var typ, category, title, message string
		var read bool
		var createdAt time.Time
		rows.Scan(&id, &typ, &category, &title, &message, &read, &createdAt)
		events = append(events, map[string]interface{}{
			"id": id, "type": typ, "category": category,
			"title": title, "message": message, "read": read, "created_at": createdAt,
		})
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(events)
}

func handleMarkRead(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	_, err := db.Exec(r.Context(), `UPDATE events SET read = TRUE WHERE id = $1`, id)
	if err != nil {
		http.Error(w, "Update error", http.StatusInternalServerError)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	w.Write([]byte(`{"status":"ok"}`))
}

func handleHealthScore(w http.ResponseWriter, r *http.Request) {
	clientID := r.PathValue("clientID")
	var score int
	err := db.QueryRow(r.Context(),
		`SELECT score FROM health_scores WHERE client_id = $1`, clientID,
	).Scan(&score)
	if err != nil {
		score = 100
	}
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{"client_id": clientID, "score": score})
}

func updateHealthScore(ctx context.Context, clientID string, eventType string) {
	delta := 0
	switch eventType {
	case "critical":
		delta = -10
	case "warning":
		delta = -3
	case "info":
		delta = 1
	}

	db.Exec(ctx, `
		INSERT INTO health_scores (client_id, score) VALUES ($1, $2)
		ON CONFLICT (client_id) DO UPDATE SET
			score = GREATEST(0, LEAST(100, health_scores.score + $3)),
			updated_at = NOW()`,
		clientID, 100+delta, delta)
}

func createZammadTicket(event Event) {
	url := os.Getenv("ZAMMAD_URL")
	token := os.Getenv("ZAMMAD_API_TOKEN")
	if url == "" || token == "" {
		return
	}

	priority := "2 normal"
	if event.Type == "critical" {
		priority = "3 high"
	}

	body, _ := json.Marshal(map[string]interface{}{
		"title":    fmt.Sprintf("[%s] %s — %s", strings.ToUpper(event.Type), event.ClientID, event.Title),
		"group":    "Users",
		"priority": map[string]string{"name": priority},
		"article": map[string]string{
			"body":         event.Message,
			"type":         "note",
			"content_type": "text/plain",
		},
	})

	req, _ := http.NewRequest("POST", url+"/api/v1/tickets", strings.NewReader(string(body)))
	req.Header.Set("Authorization", "Bearer "+token)
	req.Header.Set("Content-Type", "application/json")
	http.DefaultClient.Do(req)
}

func sendTelegramOps(event Event) {
	token := os.Getenv("TELEGRAM_BOT_TOKEN")
	chatID := os.Getenv("TELEGRAM_CHAT_ID")
	if token == "" || chatID == "" {
		return
	}
	sendTelegram(token, chatID, event)
}

func sendTelegram(token, chatID string, event Event) {
	emoji := map[string]string{"critical": "\xf0\x9f\x94\xb4", "warning": "\xf0\x9f\x9f\xa1", "info": "\xf0\x9f\x9f\xa2"}
	text := fmt.Sprintf("%s *[%s]* %s\n_%s_\n%s",
		emoji[event.Type], event.ClientID, event.Title, event.Category, event.Message)

	body, _ := json.Marshal(map[string]interface{}{
		"chat_id": chatID, "text": text, "parse_mode": "Markdown",
	})
	http.Post(
		fmt.Sprintf("https://api.telegram.org/bot%s/sendMessage", token),
		"application/json", strings.NewReader(string(body)),
	)
}

func sendBrevoEmail(to string, event Event) {
	apiKey := os.Getenv("BREVO_API_KEY")
	if apiKey == "" || apiKey == "placeholder-configure-brevo" {
		return
	}

	body, _ := json.Marshal(map[string]interface{}{
		"sender":  map[string]string{"name": "Flash Studio", "email": "support@flash-studio.io"},
		"to":      []map[string]string{{"email": to}},
		"subject": fmt.Sprintf("[%s] %s", strings.ToUpper(event.Type), event.Title),
		"htmlContent": fmt.Sprintf("<h3>%s</h3><p>%s</p><p><em>Client: %s</em></p>",
			event.Title, event.Message, event.ClientID),
	})

	req, _ := http.NewRequest("POST", "https://api.brevo.com/v3/smtp/email",
		strings.NewReader(string(body)))
	req.Header.Set("api-key", apiKey)
	req.Header.Set("Content-Type", "application/json")
	http.DefaultClient.Do(req)
}

func contains(slice []string, item string) bool {
	for _, s := range slice {
		if s == item {
			return true
		}
	}
	return false
}

// ---------------------------------------------------------------------------
// Announcements API
// ---------------------------------------------------------------------------

func handleCreateAnnouncement(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Type    string `json:"type"`
		Message string `json:"message"`
	}

	body, err := io.ReadAll(r.Body)
	if err != nil {
		http.Error(w, "Bad request", http.StatusBadRequest)
		return
	}
	if err := json.Unmarshal(body, &req); err != nil {
		http.Error(w, "Invalid JSON", http.StatusBadRequest)
		return
	}

	if req.Message == "" {
		http.Error(w, "message is required", http.StatusBadRequest)
		return
	}
	if req.Type == "" {
		req.Type = "information"
	}
	if !validAnnouncementTypes[req.Type] {
		http.Error(w, "type must be one of: information, warning, outage, operational", http.StatusBadRequest)
		return
	}

	ctx := r.Context()
	var ann Announcement
	err = db.QueryRow(ctx,
		`INSERT INTO announcements (type, message) VALUES ($1, $2)
		 RETURNING id, type, message, archived, created_at`,
		req.Type, req.Message,
	).Scan(&ann.ID, &ann.Type, &ann.Message, &ann.Archived, &ann.CreatedAt)
	if err != nil {
		log.Printf("Failed to create announcement: %v", err)
		http.Error(w, "Storage error", http.StatusInternalServerError)
		return
	}

	// Sync to Gatus config file (best effort)
	go syncGatusConfig()

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusCreated)
	json.NewEncoder(w).Encode(ann)
}

func handleListAnnouncements(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()

	// Default: active only. ?all=true to include archived.
	includeArchived := r.URL.Query().Get("all") == "true"

	var query string
	if includeArchived {
		query = `SELECT id, type, message, archived, created_at
		         FROM announcements ORDER BY created_at DESC LIMIT 100`
	} else {
		query = `SELECT id, type, message, archived, created_at
		         FROM announcements WHERE NOT archived ORDER BY created_at DESC LIMIT 100`
	}

	rows, err := db.Query(ctx, query)
	if err != nil {
		http.Error(w, "Query error", http.StatusInternalServerError)
		return
	}
	defer rows.Close()

	announcements := make([]Announcement, 0)
	for rows.Next() {
		var ann Announcement
		if err := rows.Scan(&ann.ID, &ann.Type, &ann.Message, &ann.Archived, &ann.CreatedAt); err != nil {
			continue
		}
		announcements = append(announcements, ann)
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(announcements)
}

func handleArchiveAnnouncement(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	if id == "" {
		http.Error(w, "id required", http.StatusBadRequest)
		return
	}

	ctx := r.Context()
	tag, err := db.Exec(ctx,
		`UPDATE announcements SET archived = TRUE WHERE id = $1 AND NOT archived`, id)
	if err != nil {
		http.Error(w, "Update error", http.StatusInternalServerError)
		return
	}
	if tag.RowsAffected() == 0 {
		http.Error(w, "Announcement not found or already archived", http.StatusNotFound)
		return
	}

	// Sync to Gatus config file (best effort)
	go syncGatusConfig()

	w.Header().Set("Content-Type", "application/json")
	w.Write([]byte(`{"status":"archived"}`))
}

// ---------------------------------------------------------------------------
// Gatus Endpoints API
// ---------------------------------------------------------------------------

func handleCreateGatusEndpoint(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Name       string   `json:"name"`
		Group      string   `json:"group"`
		URL        string   `json:"url"`
		Interval   string   `json:"interval"`
		Conditions []string `json:"conditions"`
	}

	body, err := io.ReadAll(r.Body)
	if err != nil {
		http.Error(w, "Bad request", http.StatusBadRequest)
		return
	}
	if err := json.Unmarshal(body, &req); err != nil {
		http.Error(w, "Invalid JSON", http.StatusBadRequest)
		return
	}

	if req.Name == "" || req.URL == "" {
		http.Error(w, "name and url are required", http.StatusBadRequest)
		return
	}
	if req.Group == "" {
		req.Group = "Custom"
	}
	if req.Interval == "" {
		req.Interval = "60s"
	}
	if len(req.Conditions) == 0 {
		req.Conditions = []string{"[STATUS] == 200"}
	}

	condJSON, _ := json.Marshal(req.Conditions)

	ctx := r.Context()
	var ep GatusEndpoint
	err = db.QueryRow(ctx,
		`INSERT INTO gatus_endpoints (name, grp, url, interval, conditions)
		 VALUES ($1, $2, $3, $4, $5)
		 RETURNING id, name, grp, url, interval, conditions, enabled, created_at`,
		req.Name, req.Group, req.URL, req.Interval, condJSON,
	).Scan(&ep.ID, &ep.Name, &ep.Group, &ep.URL, &ep.Interval, &condJSON, &ep.Enabled, &ep.CreatedAt)
	if err != nil {
		log.Printf("Failed to create gatus endpoint: %v", err)
		http.Error(w, "Storage error", http.StatusInternalServerError)
		return
	}
	json.Unmarshal(condJSON, &ep.Conditions)

	go syncGatusConfig()

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusCreated)
	json.NewEncoder(w).Encode(ep)
}

func handleListGatusEndpoints(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	rows, err := db.Query(ctx,
		`SELECT id, name, grp, url, interval, conditions, enabled, created_at
		 FROM gatus_endpoints ORDER BY created_at ASC`)
	if err != nil {
		http.Error(w, "Query error", http.StatusInternalServerError)
		return
	}
	defer rows.Close()

	endpoints := make([]GatusEndpoint, 0)
	for rows.Next() {
		var ep GatusEndpoint
		var condJSON []byte
		if err := rows.Scan(&ep.ID, &ep.Name, &ep.Group, &ep.URL, &ep.Interval, &condJSON, &ep.Enabled, &ep.CreatedAt); err != nil {
			continue
		}
		json.Unmarshal(condJSON, &ep.Conditions)
		endpoints = append(endpoints, ep)
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(endpoints)
}

func handleUpdateGatusEndpoint(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	if id == "" {
		http.Error(w, "id required", http.StatusBadRequest)
		return
	}

	var req struct {
		Name       *string  `json:"name"`
		Group      *string  `json:"group"`
		URL        *string  `json:"url"`
		Interval   *string  `json:"interval"`
		Conditions []string `json:"conditions"`
		Enabled    *bool    `json:"enabled"`
	}

	body, err := io.ReadAll(r.Body)
	if err != nil {
		http.Error(w, "Bad request", http.StatusBadRequest)
		return
	}
	if err := json.Unmarshal(body, &req); err != nil {
		http.Error(w, "Invalid JSON", http.StatusBadRequest)
		return
	}

	ctx := r.Context()

	// Read current state
	var ep GatusEndpoint
	var condJSON []byte
	err = db.QueryRow(ctx,
		`SELECT id, name, grp, url, interval, conditions, enabled, created_at
		 FROM gatus_endpoints WHERE id = $1`, id,
	).Scan(&ep.ID, &ep.Name, &ep.Group, &ep.URL, &ep.Interval, &condJSON, &ep.Enabled, &ep.CreatedAt)
	if err != nil {
		http.Error(w, "Endpoint not found", http.StatusNotFound)
		return
	}
	json.Unmarshal(condJSON, &ep.Conditions)

	// Apply partial update
	if req.Name != nil {
		ep.Name = *req.Name
	}
	if req.Group != nil {
		ep.Group = *req.Group
	}
	if req.URL != nil {
		ep.URL = *req.URL
	}
	if req.Interval != nil {
		ep.Interval = *req.Interval
	}
	if req.Conditions != nil {
		ep.Conditions = req.Conditions
	}
	if req.Enabled != nil {
		ep.Enabled = *req.Enabled
	}

	condJSON, _ = json.Marshal(ep.Conditions)
	_, err = db.Exec(ctx,
		`UPDATE gatus_endpoints
		 SET name=$1, grp=$2, url=$3, interval=$4, conditions=$5, enabled=$6
		 WHERE id=$7`,
		ep.Name, ep.Group, ep.URL, ep.Interval, condJSON, ep.Enabled, ep.ID)
	if err != nil {
		http.Error(w, "Update error", http.StatusInternalServerError)
		return
	}

	go syncGatusConfig()

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(ep)
}

func handleDeleteGatusEndpoint(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	if id == "" {
		http.Error(w, "id required", http.StatusBadRequest)
		return
	}

	ctx := r.Context()
	tag, err := db.Exec(ctx, `DELETE FROM gatus_endpoints WHERE id = $1`, id)
	if err != nil {
		http.Error(w, "Delete error", http.StatusInternalServerError)
		return
	}
	if tag.RowsAffected() == 0 {
		http.Error(w, "Endpoint not found", http.StatusNotFound)
		return
	}

	go syncGatusConfig()

	w.Header().Set("Content-Type", "application/json")
	w.Write([]byte(`{"status":"deleted"}`))
}

// ---------------------------------------------------------------------------
// Gatus config sync — rewrites announcements + dynamic endpoints + restarts
// ---------------------------------------------------------------------------

// syncGatusConfig rewrites the Gatus YAML config with:
//   - announcements from DB (replaces existing announcements section)
//   - dynamic endpoints from DB (appended after the marker comment)
//
// Then restarts the Gatus container.
func syncGatusConfig() {
	configPath := os.Getenv("GATUS_CONFIG_PATH")
	if configPath == "" {
		log.Println("[gatus-sync] GATUS_CONFIG_PATH not set, skipping sync")
		return
	}

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	// --- Fetch announcements ---
	annRows, err := db.Query(ctx,
		`SELECT type, message, created_at FROM announcements
		 WHERE NOT archived ORDER BY created_at DESC`)
	if err != nil {
		log.Printf("[gatus-sync] Failed to query announcements: %v", err)
		return
	}
	var announcements []gatusAnnouncement
	for annRows.Next() {
		var a gatusAnnouncement
		if err := annRows.Scan(&a.Type, &a.Message, &a.CreatedAt); err != nil {
			continue
		}
		announcements = append(announcements, a)
	}
	annRows.Close()

	// --- Fetch dynamic endpoints ---
	epRows, err := db.Query(ctx,
		`SELECT name, grp, url, interval, conditions FROM gatus_endpoints
		 WHERE enabled ORDER BY created_at ASC`)
	if err != nil {
		log.Printf("[gatus-sync] Failed to query endpoints: %v", err)
		return
	}
	var endpoints []gatusEndpointRow
	for epRows.Next() {
		var e gatusEndpointRow
		var condJSON []byte
		if err := epRows.Scan(&e.Name, &e.Group, &e.URL, &e.Interval, &condJSON); err != nil {
			continue
		}
		json.Unmarshal(condJSON, &e.Conditions)
		endpoints = append(endpoints, e)
	}
	epRows.Close()

	// --- Read existing config ---
	data, err := os.ReadFile(configPath)
	if err != nil {
		log.Printf("[gatus-sync] Cannot read %s: %v", configPath, err)
		return
	}

	// --- Rewrite ---
	newConfig := rewriteGatusConfig(string(data), announcements, endpoints)

	if err := os.WriteFile(configPath, []byte(newConfig), 0644); err != nil {
		log.Printf("[gatus-sync] Cannot write %s: %v", configPath, err)
		return
	}

	log.Printf("[gatus-sync] Synced: %d announcement(s), %d dynamic endpoint(s)",
		len(announcements), len(endpoints))

	restartGatusContainer()
}

// dynamicMarker is the comment line in the Gatus config that separates
// static (Ansible-managed) endpoints from dynamic (API-managed) ones.
const dynamicMarker = "# --- Dynamic (API-managed) ---"

// rewriteGatusConfig rewrites the Gatus YAML config by:
// 1. Replacing the announcements: top-level section
// 2. Removing everything after the dynamic marker and appending fresh dynamic endpoints
func rewriteGatusConfig(config string, announcements []gatusAnnouncement, endpoints []gatusEndpointRow) string {
	lines := strings.Split(config, "\n")

	// --- Pass 1: strip existing announcements section ---
	var stripped []string
	inAnnouncements := false
	for _, line := range lines {
		trimmed := strings.TrimSpace(line)
		if trimmed == "announcements:" {
			inAnnouncements = true
			continue
		}
		if inAnnouncements {
			if trimmed == "" || (len(line) > 0 && (line[0] == ' ' || line[0] == '\t')) {
				continue
			}
			inAnnouncements = false
		}
		stripped = append(stripped, line)
	}

	// --- Pass 2: strip everything from the dynamic marker to next top-level key or EOF ---
	var base []string
	foundMarker := false
	afterMarker := false
	for _, line := range stripped {
		trimmed := strings.TrimSpace(line)
		if trimmed == dynamicMarker {
			foundMarker = true
			afterMarker = true
			continue
		}
		if afterMarker {
			// skip indented/list lines and empty lines belonging to dynamic section
			if trimmed == "" || (len(line) > 0 && (line[0] == ' ' || line[0] == '\t')) {
				continue
			}
			// new top-level key → stop stripping
			afterMarker = false
		}
		base = append(base, line)
	}

	// --- Build announcements YAML ---
	var annBuf bytes.Buffer
	if len(announcements) > 0 {
		annBuf.WriteString("announcements:\n")
		for _, a := range announcements {
			ts := a.CreatedAt.UTC().Format(time.RFC3339)
			safeMsg := strings.ReplaceAll(a.Message, `"`, `\"`)
			annBuf.WriteString(fmt.Sprintf("  - timestamp: %s\n", ts))
			annBuf.WriteString(fmt.Sprintf("    type: %s\n", a.Type))
			annBuf.WriteString(fmt.Sprintf("    message: \"%s\"\n", safeMsg))
		}
	}

	// --- Build dynamic endpoints YAML ---
	var epBuf bytes.Buffer
	if len(endpoints) > 0 {
		epBuf.WriteString("\n  " + dynamicMarker + "\n")
		for _, e := range endpoints {
			safeN := strings.ReplaceAll(e.Name, `"`, `\"`)
			epBuf.WriteString(fmt.Sprintf("  - name: \"%s\"\n", safeN))
			epBuf.WriteString(fmt.Sprintf("    group: \"%s\"\n", e.Group))
			epBuf.WriteString(fmt.Sprintf("    url: \"%s\"\n", e.URL))
			epBuf.WriteString(fmt.Sprintf("    interval: %s\n", e.Interval))
			epBuf.WriteString("    conditions:\n")
			for _, c := range e.Conditions {
				epBuf.WriteString(fmt.Sprintf("      - \"%s\"\n", c))
			}
		}
	}

	// --- Assemble final config ---
	output := strings.Join(base, "\n")

	// Insert announcements before "ui:"
	if annBuf.Len() > 0 {
		annBlock := annBuf.String()
		if idx := strings.Index(output, "\nui:"); idx >= 0 {
			output = output[:idx] + "\n" + annBlock + output[idx:]
		} else if idx := strings.Index(output, "\nendpoints:"); idx >= 0 {
			output = output[:idx] + "\n" + annBlock + output[idx:]
		} else {
			output += "\n" + annBlock
		}
	}

	// Append dynamic endpoints at the end (inside the endpoints section)
	if epBuf.Len() > 0 {
		// If marker was previously present, we already removed it — just append
		output = strings.TrimRight(output, "\n") + "\n" + epBuf.String()
	} else if foundMarker {
		// Marker existed but no endpoints left → already stripped, nothing to add
	}

	return output
}

// restartGatusContainer sends a POST to the Docker Engine API via Unix socket
// to restart the sd_gatus container. Requires /var/run/docker.sock mounted.
func restartGatusContainer() {
	socketPath := os.Getenv("DOCKER_SOCKET")
	if socketPath == "" {
		socketPath = "/var/run/docker.sock"
	}

	containerName := os.Getenv("GATUS_CONTAINER_NAME")
	if containerName == "" {
		containerName = "sd_gatus"
	}

	client := &http.Client{
		Transport: &http.Transport{
			DialContext: func(_ context.Context, _, _ string) (net.Conn, error) {
				return net.Dial("unix", socketPath)
			},
		},
		Timeout: 30 * time.Second,
	}

	url := fmt.Sprintf("http://localhost/containers/%s/restart?t=5", containerName)
	req, err := http.NewRequest("POST", url, nil)
	if err != nil {
		log.Printf("[gatus-sync] Failed to create restart request: %v", err)
		return
	}

	resp, err := client.Do(req)
	if err != nil {
		log.Printf("[gatus-sync] Failed to restart Gatus container: %v", err)
		return
	}
	defer resp.Body.Close()

	if resp.StatusCode == 204 || resp.StatusCode == 200 {
		log.Println("[gatus-sync] Gatus container restarted successfully")
	} else {
		body, _ := io.ReadAll(resp.Body)
		log.Printf("[gatus-sync] Gatus restart returned %d: %s", resp.StatusCode, string(body))
	}
}
