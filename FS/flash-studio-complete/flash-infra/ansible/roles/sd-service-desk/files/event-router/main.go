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
// POST /api/tickets           <- agents (smart ticket creation pipeline)
// POST /api/voice-ticket      <- voice transcription → structured ticket
// GET  /api/tickets/{clientID} <- list ticket mappings
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
// POST /api/client-customers  <- admin (upsert client→Zammad customer mapping)
// GET  /api/client-customers/{clientID} <- admin (get mapping)
//
// POST   /api/admin/keys       <- admin (generate API key for a client agent)
// GET    /api/admin/keys       <- admin (list API keys, ?client_id= filter)
// DELETE /api/admin/keys/{hash} <- admin (revoke an API key)
//
//   -> PostgreSQL (events, announcements, gatus_endpoints, ticket_mappings, etc.)
//   -> Gatus config file rewrite + container restart
package main

import (
	"bytes"
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"math"
	"net"
	"net/http"
	"os"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
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

// TicketRequest is the incoming payload for smart ticket creation.
type TicketRequest struct {
	ClientID string            `json:"client_id"`
	Message  string            `json:"message"`
	Source   string            `json:"source"`   // voice, agent, openclaw, monitor, manual
	Language string            `json:"language"`  // fr, en — auto-detected if empty
	EventID  string            `json:"event_id"`  // idempotency key
	Metadata map[string]string `json:"metadata,omitempty"`
}

// ExtractedTicket is the structured output from LLM extraction.
type ExtractedTicket struct {
	Title    string  `json:"title"`
	Body     string  `json:"body"`
	Category string  `json:"category"` // billing, technical, account, security, general
	Priority string  `json:"priority"` // low, normal, high, urgent
	Urgency  float64 `json:"urgency"`  // 0.0 to 1.0
	Language string  `json:"language"`
	Summary  string  `json:"summary"`
}

// TicketResponse is the API response after ticket creation.
type TicketResponse struct {
	Status         string `json:"status"`                      // created, duplicate, throttled, error
	TicketID       int64  `json:"ticket_id,omitempty"`
	ZammadTicketID int64  `json:"zammad_ticket_id,omitempty"`
	CorrelationID  string `json:"correlation_id,omitempty"`
	DuplicateOf    int64  `json:"duplicate_of,omitempty"`
	Message        string `json:"message,omitempty"`
}

// ClientCustomer maps a client_id to a Zammad customer.
type ClientCustomer struct {
	ClientID         string `json:"client_id"`
	ZammadCustomerID int64  `json:"zammad_customer_id"`
	Email            string `json:"email"`
	Name             string `json:"name"`
}

// dedupResult holds the deduplication check outcome.
type dedupResult struct {
	isDuplicate      bool
	existingTicketID int64
	embeddingHash    string
	embedding        []float64
}

// ticketEnrichment holds context data attached to tickets.
type ticketEnrichment struct {
	HealthScore  int                      `json:"health_score"`
	RecentEvents []map[string]interface{} `json:"recent_events"`
}

// cachedEmbedding is stored in Redis for semantic deduplication.
type cachedEmbedding struct {
	TicketID  int64     `json:"t"`
	Embedding []float64 `json:"e"`
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

	validCategories = map[string]bool{
		"billing": true, "technical": true, "account": true,
		"security": true, "general": true,
	}
	validPriorities = map[string]bool{
		"low": true, "normal": true, "high": true, "urgent": true,
	}

	categoryToGroup = map[string]string{
		"billing":   "Billing",
		"technical": "Technical Support",
		"account":   "Account Management",
		"security":  "Security",
		"general":   "Users",
	}
	priorityToZammadID = map[string]int{
		"low": 1, "normal": 2, "high": 3, "urgent": 4,
	}

	// Circuit breaker for LiteLLM
	llmCircuitOpen    atomic.Bool
	llmCircuitResetAt atomic.Int64 // unix timestamp
	llmFailCount      atomic.Int32

	// Regex for sanitizing secrets from ticket body
	secretPattern = regexp.MustCompile(`(?i)(token|key|password|secret|bearer)\s*[:=]\s*\S+`)
)

const (
	maxTicketsPerHour   = 10
	categoryCooldownSec = 300 // 5 minutes
	duplicateThreshold  = 0.92
	idempotencyTTL      = 3600  // 1 hour
	dedupHashTTL        = 86400 // 24 hours
	recentEmbeddingsMax = 100
	embeddingCacheTTL   = 86400
	maxMessageLen       = 10000
	circuitBreakerMax   = 3  // failures before opening
	circuitBreakerReset = 60 // seconds
	dlqMaxRetries       = 5
	dlqRetryInterval    = 5 * time.Minute
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

	// Smart Ticket API
	mux.HandleFunc("POST /api/tickets", handleCreateTicket)
	mux.HandleFunc("POST /api/voice-ticket", handleVoiceTicket)
	mux.HandleFunc("GET /api/tickets/{clientID}", handleListTickets)

	// Client-Customer Mapping
	mux.HandleFunc("POST /api/client-customers", handleUpsertClientCustomer)
	mux.HandleFunc("GET /api/client-customers/{clientID}", handleGetClientCustomer)

	// API Key Management (admin only)
	mux.HandleFunc("POST /api/admin/keys", handleCreateAPIKey)
	mux.HandleFunc("GET /api/admin/keys", handleListAPIKeys)
	mux.HandleFunc("DELETE /api/admin/keys/{hash}", handleRevokeAPIKey)

	// Start DLQ retry goroutine
	go retryDLQ()

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

		CREATE TABLE IF NOT EXISTS ticket_mappings (
			id BIGSERIAL PRIMARY KEY,
			event_id TEXT NOT NULL DEFAULT '',
			client_id TEXT NOT NULL,
			zammad_ticket_id BIGINT NOT NULL DEFAULT 0,
			correlation_id TEXT NOT NULL,
			embedding_hash TEXT DEFAULT '',
			source TEXT DEFAULT '',
			category TEXT DEFAULT '',
			priority TEXT DEFAULT '',
			language TEXT DEFAULT '',
			raw_message TEXT DEFAULT '',
			created_at TIMESTAMPTZ DEFAULT NOW()
		);
		CREATE INDEX IF NOT EXISTS idx_ticket_mappings_event
			ON ticket_mappings(event_id) WHERE event_id != '';
		CREATE INDEX IF NOT EXISTS idx_ticket_mappings_client
			ON ticket_mappings(client_id, created_at DESC);
		CREATE INDEX IF NOT EXISTS idx_ticket_mappings_correlation
			ON ticket_mappings(correlation_id);

		CREATE TABLE IF NOT EXISTS client_customers (
			client_id TEXT PRIMARY KEY,
			zammad_customer_id BIGINT NOT NULL DEFAULT 0,
			email TEXT NOT NULL DEFAULT '',
			name TEXT NOT NULL DEFAULT '',
			updated_at TIMESTAMPTZ DEFAULT NOW()
		);

		CREATE TABLE IF NOT EXISTS api_keys (
			key_hash TEXT PRIMARY KEY,
			client_id TEXT NOT NULL,
			name TEXT DEFAULT '',
			created_at TIMESTAMPTZ DEFAULT NOW()
		);

		CREATE TABLE IF NOT EXISTS ticket_dlq (
			id BIGSERIAL PRIMARY KEY,
			client_id TEXT NOT NULL,
			payload JSONB NOT NULL,
			error TEXT DEFAULT '',
			retries INTEGER DEFAULT 0,
			next_retry_at TIMESTAMPTZ DEFAULT NOW(),
			created_at TIMESTAMPTZ DEFAULT NOW()
		);
		CREATE INDEX IF NOT EXISTS idx_ticket_dlq_retry
			ON ticket_dlq(next_retry_at) WHERE retries < 5;
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

	// Smart ticket creation if severity >= warning
	if event.Type == "warning" || event.Type == "critical" {
		req := TicketRequest{
			ClientID: event.ClientID,
			Message:  event.Title + "\n\n" + event.Message,
			Source:   "monitor",
			EventID:  fmt.Sprintf("event-%s-%d", event.ClientID, event.Timestamp.UnixNano()),
			Metadata: event.Metadata,
		}
		resp, _ := processTicketCreation(ctx, req)
		if resp.Status == "error" {
			createZammadTicket(event) // fallback to basic
		}
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

// ===========================================================================
// Smart Ticket Creation Pipeline
// ===========================================================================

// --- Utility helpers ---

func decodeJSON(r *http.Request, v interface{}) error {
	body, err := io.ReadAll(io.LimitReader(r.Body, int64(maxMessageLen+1024)))
	if err != nil {
		return err
	}
	return json.Unmarshal(body, v)
}

func writeJSON(w http.ResponseWriter, status int, v interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(v)
}

func writeError(w http.ResponseWriter, msg string, status int) {
	writeJSON(w, status, map[string]string{"error": msg})
}

func generateCorrelationID() string {
	b := make([]byte, 8)
	rand.Read(b)
	return fmt.Sprintf("tkt-%x", b)
}

func hashString(s string) string {
	h := sha256.Sum256([]byte(s))
	return fmt.Sprintf("%x", h[:16])
}

func sanitizeBody(s string) string {
	return secretPattern.ReplaceAllString(s, "[REDACTED]")
}

func cleanJSONResponse(s string) string {
	s = strings.TrimSpace(s)
	if strings.HasPrefix(s, "```json") {
		s = strings.TrimPrefix(s, "```json")
		s = strings.TrimSuffix(strings.TrimSpace(s), "```")
	} else if strings.HasPrefix(s, "```") {
		s = strings.TrimPrefix(s, "```")
		s = strings.TrimSuffix(strings.TrimSpace(s), "```")
	}
	return strings.TrimSpace(s)
}

func truncate(s string, max int) string {
	if len(s) <= max {
		return s
	}
	return s[:max-3] + "..."
}

// --- Auth middleware ---

func validateAPIKey(r *http.Request) (clientID string, ok bool) {
	adminKey := os.Getenv("ADMIN_API_KEY")
	auth := strings.TrimPrefix(r.Header.Get("Authorization"), "Bearer ")
	if auth == "" {
		// If no ADMIN_API_KEY configured, allow all (network isolation)
		if adminKey == "" {
			return "", true
		}
		return "", false
	}
	// Check admin key first
	if adminKey != "" && auth == adminKey {
		return "", true
	}
	// Check per-agent key in database
	keyHash := fmt.Sprintf("%x", sha256.Sum256([]byte(auth)))
	err := db.QueryRow(r.Context(),
		`SELECT client_id FROM api_keys WHERE key_hash = $1`, keyHash,
	).Scan(&clientID)
	return clientID, err == nil
}

// --- Redis: Idempotency ---

func checkIdempotency(ctx context.Context, eventID string) (bool, error) {
	if rdb == nil || eventID == "" {
		return false, nil
	}
	set, err := rdb.SetNX(ctx, "idempotent:"+eventID, "1",
		time.Duration(idempotencyTTL)*time.Second).Result()
	if err != nil {
		return false, err
	}
	return !set, nil // !set means key already existed
}

// --- Redis: Rate Limit (sliding window) ---

func checkRateLimit(ctx context.Context, clientID string) (bool, error) {
	if rdb == nil {
		return false, nil
	}
	key := "ratelimit:tickets:" + clientID
	now := time.Now()
	cutoff := fmt.Sprintf("%d", now.Add(-time.Hour).UnixMilli())

	pipe := rdb.Pipeline()
	pipe.ZRemRangeByScore(ctx, key, "0", cutoff)
	countCmd := pipe.ZCard(ctx, key)
	_, err := pipe.Exec(ctx)
	if err != nil {
		return false, err
	}

	if countCmd.Val() >= int64(maxTicketsPerHour) {
		return true, nil
	}
	rdb.ZAdd(ctx, key, redis.Z{Score: float64(now.UnixMilli()), Member: now.UnixNano()})
	rdb.Expire(ctx, key, 2*time.Hour)
	return false, nil
}

// --- Redis: Category Cooldown ---

func checkCategoryCooldown(ctx context.Context, clientID, category string) bool {
	if rdb == nil || category == "" {
		return false
	}
	key := fmt.Sprintf("cooldown:%s:%s", clientID, category)
	n, _ := rdb.Exists(ctx, key).Result()
	return n > 0
}

func setCategoryCooldown(ctx context.Context, clientID, category string) {
	if rdb == nil || category == "" {
		return
	}
	key := fmt.Sprintf("cooldown:%s:%s", clientID, category)
	rdb.Set(ctx, key, "1", time.Duration(categoryCooldownSec)*time.Second)
}

// --- Circuit Breaker for LiteLLM ---

func isCircuitOpen() bool {
	if !llmCircuitOpen.Load() {
		return false
	}
	if time.Now().Unix() >= llmCircuitResetAt.Load() {
		llmCircuitOpen.Store(false)
		llmFailCount.Store(0)
		log.Println("[circuit] LiteLLM circuit breaker reset")
		return false
	}
	return true
}

func recordLLMFailure() {
	count := llmFailCount.Add(1)
	if count >= int32(circuitBreakerMax) {
		llmCircuitOpen.Store(true)
		llmCircuitResetAt.Store(time.Now().Unix() + int64(circuitBreakerReset))
		log.Printf("[circuit] LiteLLM circuit breaker OPEN for %ds", circuitBreakerReset)
	}
}

func recordLLMSuccess() {
	llmFailCount.Store(0)
}

// --- LLM: Ticket Extraction ---

func extractTicket(ctx context.Context, message, lang, source string) (ExtractedTicket, error) {
	if isCircuitOpen() {
		return ExtractedTicket{}, fmt.Errorf("circuit breaker open")
	}

	litellmURL := os.Getenv("LITELLM_URL")
	litellmKey := os.Getenv("LITELLM_API_KEY")
	if litellmURL == "" {
		return ExtractedTicket{}, fmt.Errorf("LITELLM_URL not configured")
	}

	langHint := ""
	if lang != "" {
		langHint = fmt.Sprintf("The user communicates in %s. Use that language for title and body.", lang)
	}
	sourceHint := ""
	if source == "voice" {
		sourceHint = "This is from voice transcription. Fix transcription errors. Be forgiving of informal phrasing."
	}

	prompt := fmt.Sprintf(`Extract a structured support ticket from this message.
%s
%s

Message:
---
%s
---

Return ONLY valid JSON (no markdown, no explanation):
{"title":"short title","body":"clean description","category":"billing|technical|account|security|general","priority":"low|normal|high|urgent","urgency":0.5,"language":"fr|en","summary":"one line"}`, langHint, sourceHint, truncate(message, 8000))

	extracted, err := callLLMExtract(ctx, litellmURL, litellmKey, prompt)
	if err != nil {
		recordLLMFailure()
		return extracted, err
	}
	recordLLMSuccess()
	return extracted, nil
}

func callLLMExtract(ctx context.Context, baseURL, apiKey, prompt string) (ExtractedTicket, error) {
	model := os.Getenv("LLM_MODEL")
	if model == "" {
		model = "claude-sonnet-4-6"
	}

	reqBody, _ := json.Marshal(map[string]interface{}{
		"model":       model,
		"messages":    []map[string]string{{"role": "user", "content": prompt}},
		"temperature": 0.1,
		"max_tokens":  500,
	})

	httpReq, _ := http.NewRequestWithContext(ctx, "POST", baseURL+"/chat/completions",
		bytes.NewReader(reqBody))
	httpReq.Header.Set("Content-Type", "application/json")
	if apiKey != "" {
		httpReq.Header.Set("Authorization", "Bearer "+apiKey)
	}

	resp, err := (&http.Client{Timeout: 30 * time.Second}).Do(httpReq)
	if err != nil {
		return ExtractedTicket{}, err
	}
	defer resp.Body.Close()

	var llmResp struct {
		Choices []struct {
			Message struct {
				Content string `json:"content"`
			} `json:"message"`
		} `json:"choices"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&llmResp); err != nil {
		return ExtractedTicket{}, err
	}
	if len(llmResp.Choices) == 0 {
		return ExtractedTicket{}, fmt.Errorf("empty LLM response")
	}

	content := cleanJSONResponse(llmResp.Choices[0].Message.Content)
	var et ExtractedTicket
	if err := json.Unmarshal([]byte(content), &et); err != nil {
		return ExtractedTicket{}, fmt.Errorf("parse error: %w", err)
	}
	return et, nil
}

func fallbackExtraction(req TicketRequest) ExtractedTicket {
	return ExtractedTicket{
		Title:    truncate(req.Message, 80),
		Body:     req.Message,
		Category: "general",
		Priority: "normal",
		Urgency:  0.5,
		Language: req.Language,
		Summary:  truncate(req.Message, 80),
	}
}

// --- LLM: Embedding ---

func getEmbedding(ctx context.Context, text string) ([]float64, error) {
	if isCircuitOpen() {
		return nil, fmt.Errorf("circuit breaker open")
	}

	litellmURL := os.Getenv("LITELLM_URL")
	litellmKey := os.Getenv("LITELLM_API_KEY")
	if litellmURL == "" {
		return nil, fmt.Errorf("LITELLM_URL not configured")
	}

	reqBody, _ := json.Marshal(map[string]interface{}{
		"model": "text-embedding-3-small",
		"input": truncate(text, 8000),
	})

	httpReq, _ := http.NewRequestWithContext(ctx, "POST", litellmURL+"/embeddings",
		bytes.NewReader(reqBody))
	httpReq.Header.Set("Content-Type", "application/json")
	if litellmKey != "" {
		httpReq.Header.Set("Authorization", "Bearer "+litellmKey)
	}

	resp, err := (&http.Client{Timeout: 15 * time.Second}).Do(httpReq)
	if err != nil {
		recordLLMFailure()
		return nil, err
	}
	defer resp.Body.Close()

	var embResp struct {
		Data []struct {
			Embedding []float64 `json:"embedding"`
		} `json:"data"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&embResp); err != nil {
		recordLLMFailure()
		return nil, err
	}
	if len(embResp.Data) == 0 {
		return nil, fmt.Errorf("empty embedding response")
	}
	recordLLMSuccess()
	return embResp.Data[0].Embedding, nil
}

// --- Deduplication ---

func cosineSimilarity(a, b []float64) float64 {
	if len(a) != len(b) || len(a) == 0 {
		return 0
	}
	var dot, normA, normB float64
	for i := range a {
		dot += a[i] * b[i]
		normA += a[i] * a[i]
		normB += b[i] * b[i]
	}
	if normA == 0 || normB == 0 {
		return 0
	}
	return dot / (math.Sqrt(normA) * math.Sqrt(normB))
}

func checkDuplication(ctx context.Context, clientID, text string) dedupResult {
	result := dedupResult{}
	normalized := strings.ToLower(strings.TrimSpace(text))
	hash := hashString(normalized)
	result.embeddingHash = hash

	// Layer 1: Hash-based exact dedup
	if rdb != nil {
		key := fmt.Sprintf("dedup:hash:%s:%s", clientID, hash)
		if existing, err := rdb.Get(ctx, key).Result(); err == nil {
			ticketID, _ := strconv.ParseInt(existing, 10, 64)
			result.isDuplicate = true
			result.existingTicketID = ticketID
			return result
		}
	}

	// Layer 2: Semantic similarity via embeddings
	embedding, err := getEmbedding(ctx, text)
	if err != nil {
		log.Printf("[dedup] Embedding failed: %v", err)
		return result
	}
	result.embedding = embedding

	if rdb != nil {
		if similar, ticketID := findSimilarEmbedding(ctx, clientID, embedding); similar {
			result.isDuplicate = true
			result.existingTicketID = ticketID
		}
	}
	return result
}

func findSimilarEmbedding(ctx context.Context, clientID string, emb []float64) (bool, int64) {
	key := "dedup:emb:" + clientID
	entries, err := rdb.LRange(ctx, key, 0, int64(recentEmbeddingsMax-1)).Result()
	if err != nil {
		return false, 0
	}
	for _, entry := range entries {
		var cached cachedEmbedding
		if err := json.Unmarshal([]byte(entry), &cached); err != nil {
			continue
		}
		if cosineSimilarity(emb, cached.Embedding) >= duplicateThreshold {
			return true, cached.TicketID
		}
	}
	return false, 0
}

func cacheEmbedding(ctx context.Context, clientID string, ticketID int64, emb []float64) {
	if rdb == nil {
		return
	}
	key := "dedup:emb:" + clientID
	data, _ := json.Marshal(cachedEmbedding{TicketID: ticketID, Embedding: emb})
	rdb.LPush(ctx, key, string(data))
	rdb.LTrim(ctx, key, 0, int64(recentEmbeddingsMax-1))
	rdb.Expire(ctx, key, time.Duration(embeddingCacheTTL)*time.Second)
}

// --- Zammad Customer Resolution ---

func resolveZammadCustomer(ctx context.Context, clientID string) (int64, error) {
	// Check local cache
	var customerID int64
	if err := db.QueryRow(ctx,
		`SELECT zammad_customer_id FROM client_customers WHERE client_id = $1`,
		clientID).Scan(&customerID); err == nil && customerID > 0 {
		return customerID, nil
	}

	zammadURL := os.Getenv("ZAMMAD_URL")
	token := os.Getenv("ZAMMAD_API_TOKEN")
	if zammadURL == "" || token == "" {
		return 0, fmt.Errorf("Zammad not configured")
	}

	email := fmt.Sprintf("%s@clients.flash-studio.io", clientID)

	// Search in Zammad
	customerID = searchZammadCustomer(ctx, zammadURL, token, email)
	if customerID == 0 {
		customerID = createZammadCustomer(ctx, zammadURL, token, clientID, email)
	}
	if customerID == 0 {
		return 0, fmt.Errorf("failed to resolve customer")
	}

	// Cache locally
	db.Exec(ctx,
		`INSERT INTO client_customers (client_id, zammad_customer_id, email, name)
		 VALUES ($1, $2, $3, $4)
		 ON CONFLICT (client_id) DO UPDATE SET zammad_customer_id=$2, updated_at=NOW()`,
		clientID, customerID, email, clientID)

	return customerID, nil
}

func searchZammadCustomer(ctx context.Context, baseURL, token, email string) int64 {
	req, _ := http.NewRequestWithContext(ctx, "GET",
		fmt.Sprintf("%s/api/v1/users/search?query=%s&limit=1", baseURL, email), nil)
	req.Header.Set("Authorization", "Bearer "+token)
	resp, err := (&http.Client{Timeout: 10 * time.Second}).Do(req)
	if err != nil {
		return 0
	}
	defer resp.Body.Close()
	var users []struct {
		ID int64 `json:"id"`
	}
	json.NewDecoder(resp.Body).Decode(&users)
	if len(users) > 0 {
		return users[0].ID
	}
	return 0
}

func createZammadCustomer(ctx context.Context, baseURL, token, clientID, email string) int64 {
	body, _ := json.Marshal(map[string]interface{}{
		"email": email, "firstname": clientID, "lastname": "Client", "login": email,
	})
	req, _ := http.NewRequestWithContext(ctx, "POST", baseURL+"/api/v1/users",
		bytes.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+token)
	req.Header.Set("Content-Type", "application/json")
	resp, err := (&http.Client{Timeout: 10 * time.Second}).Do(req)
	if err != nil {
		return 0
	}
	defer resp.Body.Close()
	var customer struct {
		ID int64 `json:"id"`
	}
	json.NewDecoder(resp.Body).Decode(&customer)
	return customer.ID
}

// --- Enrichment ---

func enrichTicket(ctx context.Context, clientID string) ticketEnrichment {
	e := ticketEnrichment{HealthScore: 100}
	db.QueryRow(ctx,
		`SELECT score FROM health_scores WHERE client_id = $1`, clientID,
	).Scan(&e.HealthScore)

	rows, err := db.Query(ctx,
		`SELECT type, category, title, created_at FROM events
		 WHERE client_id = $1 ORDER BY created_at DESC LIMIT 5`, clientID)
	if err == nil {
		defer rows.Close()
		for rows.Next() {
			var typ, cat, title string
			var ts time.Time
			rows.Scan(&typ, &cat, &title, &ts)
			e.RecentEvents = append(e.RecentEvents, map[string]interface{}{
				"type": typ, "category": cat, "title": title,
				"created_at": ts.Format(time.RFC3339),
			})
		}
	}
	return e
}

// --- Enriched Zammad Ticket Creation ---

func createEnrichedZammadTicket(ctx context.Context, req TicketRequest,
	et ExtractedTicket, customerID int64, corrID string, enrich ticketEnrichment) (int64, error) {

	zammadURL := os.Getenv("ZAMMAD_URL")
	token := os.Getenv("ZAMMAD_API_TOKEN")
	if zammadURL == "" || token == "" {
		return 0, fmt.Errorf("ZAMMAD not configured")
	}

	group := categoryToGroup[et.Category]
	if group == "" {
		group = "Users"
	}
	priorityID := priorityToZammadID[et.Priority]
	if priorityID == 0 {
		priorityID = 2
	}

	bodyHTML := buildEnrichedBody(req, et, enrich, corrID)

	tags := strings.Join([]string{
		"source:" + req.Source, "lang:" + et.Language,
		"client:" + req.ClientID, "category:" + et.Category, "auto-created",
	}, ",")

	payload := map[string]interface{}{
		"title":       et.Title,
		"group":       group,
		"priority_id": priorityID,
		"article": map[string]interface{}{
			"body": bodyHTML, "type": "note",
			"content_type": "text/html", "internal": false,
		},
		"tags": tags,
		"note": fmt.Sprintf("correlation_id=%s health=%d", corrID, enrich.HealthScore),
	}
	if customerID > 0 {
		payload["customer_id"] = customerID
	}

	payloadJSON, _ := json.Marshal(payload)
	httpReq, _ := http.NewRequestWithContext(ctx, "POST", zammadURL+"/api/v1/tickets",
		bytes.NewReader(payloadJSON))
	httpReq.Header.Set("Authorization", "Bearer "+token)
	httpReq.Header.Set("Content-Type", "application/json")

	resp, err := (&http.Client{Timeout: 15 * time.Second}).Do(httpReq)
	if err != nil {
		return 0, err
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		respBody, _ := io.ReadAll(resp.Body)
		return 0, fmt.Errorf("Zammad %d: %s", resp.StatusCode, string(respBody))
	}

	var zResp struct {
		ID int64 `json:"id"`
	}
	json.NewDecoder(resp.Body).Decode(&zResp)
	return zResp.ID, nil
}

func buildEnrichedBody(req TicketRequest, et ExtractedTicket,
	enrich ticketEnrichment, corrID string) string {

	var b bytes.Buffer
	b.WriteString(fmt.Sprintf("<h3>%s</h3>", et.Title))
	b.WriteString(fmt.Sprintf("<p>%s</p><hr/>", sanitizeBody(et.Body)))
	b.WriteString("<details><summary>Metadata</summary><ul>")
	b.WriteString(fmt.Sprintf("<li><b>Source:</b> %s</li>", req.Source))
	b.WriteString(fmt.Sprintf("<li><b>Client:</b> %s</li>", req.ClientID))
	b.WriteString(fmt.Sprintf("<li><b>Language:</b> %s</li>", et.Language))
	b.WriteString(fmt.Sprintf("<li><b>Category:</b> %s</li>", et.Category))
	b.WriteString(fmt.Sprintf("<li><b>Urgency:</b> %.2f</li>", et.Urgency))
	b.WriteString(fmt.Sprintf("<li><b>Health:</b> %d/100</li>", enrich.HealthScore))
	b.WriteString(fmt.Sprintf("<li><b>Correlation:</b> %s</li>", corrID))
	b.WriteString("</ul>")

	if len(enrich.RecentEvents) > 0 {
		b.WriteString("<h4>Recent Events</h4><ul>")
		for _, evt := range enrich.RecentEvents {
			b.WriteString(fmt.Sprintf("<li>[%s] %s — %s (%s)</li>",
				evt["type"], evt["category"], evt["title"], evt["created_at"]))
		}
		b.WriteString("</ul>")
	}
	b.WriteString("</details>")
	return b.String()
}

// --- Dead-Letter Queue ---

func enqueueDLQ(ctx context.Context, req TicketRequest, errMsg string) {
	payload, _ := json.Marshal(req)
	db.Exec(ctx,
		`INSERT INTO ticket_dlq (client_id, payload, error, next_retry_at)
		 VALUES ($1, $2, $3, NOW() + INTERVAL '5 minutes')`,
		req.ClientID, payload, errMsg)
}

func retryDLQ() {
	for {
		time.Sleep(dlqRetryInterval)
		ctx := context.Background()
		rows, err := db.Query(ctx,
			`SELECT id, client_id, payload FROM ticket_dlq
			 WHERE retries < $1 AND next_retry_at <= NOW()
			 ORDER BY created_at ASC LIMIT 10`, dlqMaxRetries)
		if err != nil {
			continue
		}
		for rows.Next() {
			var id int64
			var clientID string
			var payload []byte
			rows.Scan(&id, &clientID, &payload)

			var req TicketRequest
			json.Unmarshal(payload, &req)

			resp, _ := processTicketCreation(ctx, req)
			if resp.Status == "created" {
				db.Exec(ctx, `DELETE FROM ticket_dlq WHERE id = $1`, id)
				log.Printf("[dlq] Retry succeeded for DLQ entry %d", id)
			} else {
				db.Exec(ctx,
					`UPDATE ticket_dlq SET retries = retries + 1,
					 error = $1, next_retry_at = NOW() + INTERVAL '5 minutes'
					 WHERE id = $2`, resp.Message, id)
			}
		}
		rows.Close()
	}
}

// --- Ticket Mapping Storage ---

func storeTicketMapping(ctx context.Context, req TicketRequest,
	et ExtractedTicket, zammadID int64, corrID, embHash string) int64 {

	rawMsg := truncate(req.Message, 5000)
	var id int64
	db.QueryRow(ctx,
		`INSERT INTO ticket_mappings
		 (event_id, client_id, zammad_ticket_id, correlation_id, embedding_hash,
		  source, category, priority, language, raw_message)
		 VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
		 RETURNING id`,
		req.EventID, req.ClientID, zammadID, corrID, embHash,
		req.Source, et.Category, et.Priority, et.Language, rawMsg,
	).Scan(&id)

	// Store hash for future dedup
	if rdb != nil && embHash != "" {
		key := fmt.Sprintf("dedup:hash:%s:%s", req.ClientID, embHash)
		rdb.Set(ctx, key, fmt.Sprintf("%d", zammadID),
			time.Duration(dedupHashTTL)*time.Second)
	}
	return id
}

// --- Core Pipeline ---

func processTicketCreation(ctx context.Context, req TicketRequest) (TicketResponse, int) {
	corrID := generateCorrelationID()

	// Step 1: Idempotency
	if req.EventID != "" {
		if dup, _ := checkIdempotency(ctx, req.EventID); dup {
			return TicketResponse{Status: "duplicate", Message: "Event already processed"}, http.StatusConflict
		}
	}

	// Step 2: Rate limit
	if throttled, _ := checkRateLimit(ctx, req.ClientID); throttled {
		return TicketResponse{Status: "throttled", Message: "Rate limit exceeded (max 10/h)"}, http.StatusTooManyRequests
	}

	// Step 3: LLM Extraction
	extracted, err := extractTicket(ctx, req.Message, req.Language, req.Source)
	if err != nil {
		log.Printf("[ticket] Extraction failed for %s: %v", req.ClientID, err)
		extracted = fallbackExtraction(req)
	}

	// Validate + sanitize extracted fields
	if !validCategories[extracted.Category] {
		extracted.Category = "general"
	}
	if !validPriorities[extracted.Priority] {
		extracted.Priority = "normal"
	}
	// Priority capping: only "monitor" source can set "urgent"
	if extracted.Priority == "urgent" && req.Source != "monitor" {
		extracted.Priority = "high"
	}

	// Step 4: Category cooldown
	if checkCategoryCooldown(ctx, req.ClientID, extracted.Category) {
		return TicketResponse{Status: "throttled",
			Message: fmt.Sprintf("Cooldown active for %s", extracted.Category)}, http.StatusTooManyRequests
	}

	// Step 5+6: Deduplication (hash + semantic)
	dedup := checkDuplication(ctx, req.ClientID, extracted.Title+" "+extracted.Body)
	if dedup.isDuplicate {
		return TicketResponse{Status: "duplicate", DuplicateOf: dedup.existingTicketID,
			Message: "Similar ticket exists"}, http.StatusConflict
	}

	// Step 7: Resolve Zammad customer
	customerID, err := resolveZammadCustomer(ctx, req.ClientID)
	if err != nil {
		log.Printf("[ticket] Customer resolve failed for %s: %v", req.ClientID, err)
	}

	// Step 8: Enrichment
	enrichment := enrichTicket(ctx, req.ClientID)

	// Step 9: Create Zammad ticket
	zammadID, err := createEnrichedZammadTicket(ctx, req, extracted, customerID, corrID, enrichment)
	if err != nil {
		log.Printf("[ticket] Zammad creation failed: %v", err)
		enqueueDLQ(ctx, req, err.Error())
		return TicketResponse{Status: "error", Message: "Ticket creation failed, queued for retry"}, http.StatusServiceUnavailable
	}

	// Step 10: Store mapping + caches
	mappingID := storeTicketMapping(ctx, req, extracted, zammadID, corrID, dedup.embeddingHash)
	setCategoryCooldown(ctx, req.ClientID, extracted.Category)
	if dedup.embedding != nil {
		cacheEmbedding(ctx, req.ClientID, zammadID, dedup.embedding)
	}

	log.Printf("[ticket] Created %d (zammad=%d) client=%s cat=%s corr=%s",
		mappingID, zammadID, req.ClientID, extracted.Category, corrID)

	return TicketResponse{
		Status: "created", TicketID: mappingID,
		ZammadTicketID: zammadID, CorrelationID: corrID,
	}, http.StatusCreated
}

// --- HTTP Handlers: Smart Tickets ---

func handleCreateTicket(w http.ResponseWriter, r *http.Request) {
	keyClient, ok := validateAPIKey(r)
	if !ok {
		writeError(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	var req TicketRequest
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, "Invalid request: "+err.Error(), http.StatusBadRequest)
		return
	}
	if req.ClientID == "" || req.Message == "" {
		writeError(w, "client_id and message required", http.StatusBadRequest)
		return
	}
	if len(req.Message) > maxMessageLen {
		writeError(w, fmt.Sprintf("Message too long (max %d chars)", maxMessageLen), http.StatusBadRequest)
		return
	}
	// Enforce client_id match if agent-scoped key
	if keyClient != "" && keyClient != req.ClientID {
		writeError(w, "client_id mismatch with API key", http.StatusForbidden)
		return
	}
	if req.Source == "" {
		req.Source = "agent"
	}

	resp, status := processTicketCreation(r.Context(), req)
	writeJSON(w, status, resp)
}

func handleVoiceTicket(w http.ResponseWriter, r *http.Request) {
	keyClient, ok := validateAPIKey(r)
	if !ok {
		writeError(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	var req TicketRequest
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, "Invalid request: "+err.Error(), http.StatusBadRequest)
		return
	}
	if req.ClientID == "" || req.Message == "" {
		writeError(w, "client_id and message required", http.StatusBadRequest)
		return
	}
	if len(req.Message) > maxMessageLen {
		writeError(w, fmt.Sprintf("Message too long (max %d chars)", maxMessageLen), http.StatusBadRequest)
		return
	}
	if keyClient != "" && keyClient != req.ClientID {
		writeError(w, "client_id mismatch with API key", http.StatusForbidden)
		return
	}
	req.Source = "voice"

	resp, status := processTicketCreation(r.Context(), req)
	writeJSON(w, status, resp)
}

func handleListTickets(w http.ResponseWriter, r *http.Request) {
	clientID := r.PathValue("clientID")
	rows, err := db.Query(r.Context(),
		`SELECT id, event_id, zammad_ticket_id, correlation_id, source,
		        category, priority, language, created_at
		 FROM ticket_mappings WHERE client_id = $1
		 ORDER BY created_at DESC LIMIT 50`, clientID)
	if err != nil {
		writeError(w, "Query error", http.StatusInternalServerError)
		return
	}
	defer rows.Close()

	results := make([]map[string]interface{}, 0)
	for rows.Next() {
		var id, zammadID int64
		var eventID, corrID, source, cat, prio, lang string
		var ts time.Time
		rows.Scan(&id, &eventID, &zammadID, &corrID, &source, &cat, &prio, &lang, &ts)
		results = append(results, map[string]interface{}{
			"id": id, "event_id": eventID, "zammad_ticket_id": zammadID,
			"correlation_id": corrID, "source": source, "category": cat,
			"priority": prio, "language": lang, "created_at": ts,
		})
	}
	writeJSON(w, http.StatusOK, results)
}

// --- HTTP Handlers: Client-Customer Mapping ---

func handleUpsertClientCustomer(w http.ResponseWriter, r *http.Request) {
	var req ClientCustomer
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, "Invalid request", http.StatusBadRequest)
		return
	}
	if req.ClientID == "" || req.Email == "" {
		writeError(w, "client_id and email required", http.StatusBadRequest)
		return
	}
	_, err := db.Exec(r.Context(),
		`INSERT INTO client_customers (client_id, zammad_customer_id, email, name)
		 VALUES ($1, $2, $3, $4)
		 ON CONFLICT (client_id) DO UPDATE SET
		     zammad_customer_id=$2, email=$3, name=$4, updated_at=NOW()`,
		req.ClientID, req.ZammadCustomerID, req.Email, req.Name)
	if err != nil {
		writeError(w, "Storage error", http.StatusInternalServerError)
		return
	}
	writeJSON(w, http.StatusCreated, req)
}

func handleGetClientCustomer(w http.ResponseWriter, r *http.Request) {
	clientID := r.PathValue("clientID")
	var cc ClientCustomer
	err := db.QueryRow(r.Context(),
		`SELECT client_id, zammad_customer_id, email, name
		 FROM client_customers WHERE client_id = $1`, clientID,
	).Scan(&cc.ClientID, &cc.ZammadCustomerID, &cc.Email, &cc.Name)
	if err != nil {
		writeError(w, "Not found", http.StatusNotFound)
		return
	}
	writeJSON(w, http.StatusOK, cc)
}

// --- HTTP Handlers: API Key Management (admin) ---

// APIKeyRequest is the incoming payload for key creation.
type APIKeyRequest struct {
	ClientID string `json:"client_id"`
	Name     string `json:"name"`
}

// APIKeyResponse is returned after key creation (only time raw key is visible).
type APIKeyResponse struct {
	Key      string `json:"key"`
	KeyHash  string `json:"key_hash"`
	ClientID string `json:"client_id"`
	Name     string `json:"name"`
}

// APIKeyListItem is a single key in the list (no raw key).
type APIKeyListItem struct {
	KeyHash   string    `json:"key_hash"`
	ClientID  string    `json:"client_id"`
	Name      string    `json:"name"`
	CreatedAt time.Time `json:"created_at"`
}

func handleCreateAPIKey(w http.ResponseWriter, r *http.Request) {
	// Admin auth required
	adminKey := os.Getenv("ADMIN_API_KEY")
	auth := strings.TrimPrefix(r.Header.Get("Authorization"), "Bearer ")
	if adminKey == "" || auth != adminKey {
		writeError(w, "Unauthorized — admin key required", http.StatusUnauthorized)
		return
	}

	var req APIKeyRequest
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, "Invalid request", http.StatusBadRequest)
		return
	}
	if req.ClientID == "" {
		writeError(w, "client_id required", http.StatusBadRequest)
		return
	}
	if req.Name == "" {
		req.Name = req.ClientID + "-agent"
	}

	// Generate 32 bytes of cryptographic randomness → 64 hex chars
	rawKey := make([]byte, 32)
	if _, err := rand.Read(rawKey); err != nil {
		writeError(w, "Key generation failed", http.StatusInternalServerError)
		return
	}
	keyStr := fmt.Sprintf("sk-%x", rawKey)
	keyHash := fmt.Sprintf("%x", sha256.Sum256([]byte(keyStr)))

	_, err := db.Exec(r.Context(),
		`INSERT INTO api_keys (key_hash, client_id, name) VALUES ($1, $2, $3)`,
		keyHash, req.ClientID, req.Name)
	if err != nil {
		writeError(w, "Key already exists or storage error", http.StatusConflict)
		return
	}

	log.Printf("[keys] Created API key for %s (name=%s, hash=%s…)",
		req.ClientID, req.Name, keyHash[:12])

	writeJSON(w, http.StatusCreated, APIKeyResponse{
		Key: keyStr, KeyHash: keyHash, ClientID: req.ClientID, Name: req.Name,
	})
}

func handleListAPIKeys(w http.ResponseWriter, r *http.Request) {
	adminKey := os.Getenv("ADMIN_API_KEY")
	auth := strings.TrimPrefix(r.Header.Get("Authorization"), "Bearer ")
	if adminKey == "" || auth != adminKey {
		writeError(w, "Unauthorized — admin key required", http.StatusUnauthorized)
		return
	}

	clientFilter := r.URL.Query().Get("client_id")
	query := `SELECT key_hash, client_id, name, created_at FROM api_keys`
	args := []interface{}{}
	if clientFilter != "" {
		query += ` WHERE client_id = $1`
		args = append(args, clientFilter)
	}
	query += ` ORDER BY created_at DESC`

	rows, err := db.Query(r.Context(), query, args...)
	if err != nil {
		writeError(w, "Query error", http.StatusInternalServerError)
		return
	}
	defer rows.Close()

	results := make([]APIKeyListItem, 0)
	for rows.Next() {
		var item APIKeyListItem
		rows.Scan(&item.KeyHash, &item.ClientID, &item.Name, &item.CreatedAt)
		results = append(results, item)
	}
	writeJSON(w, http.StatusOK, results)
}

func handleRevokeAPIKey(w http.ResponseWriter, r *http.Request) {
	adminKey := os.Getenv("ADMIN_API_KEY")
	auth := strings.TrimPrefix(r.Header.Get("Authorization"), "Bearer ")
	if adminKey == "" || auth != adminKey {
		writeError(w, "Unauthorized — admin key required", http.StatusUnauthorized)
		return
	}

	keyHash := r.PathValue("hash")
	if keyHash == "" {
		writeError(w, "Key hash required", http.StatusBadRequest)
		return
	}

	tag, err := db.Exec(r.Context(), `DELETE FROM api_keys WHERE key_hash = $1`, keyHash)
	if err != nil || tag.RowsAffected() == 0 {
		writeError(w, "Key not found", http.StatusNotFound)
		return
	}

	log.Printf("[keys] Revoked API key %s…", keyHash[:12])
	writeJSON(w, http.StatusOK, map[string]string{"status": "revoked"})
}
