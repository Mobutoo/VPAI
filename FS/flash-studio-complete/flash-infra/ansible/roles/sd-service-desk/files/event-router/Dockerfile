FROM golang:1.24-alpine AS builder

WORKDIR /app
COPY go.mod ./
RUN go mod download

COPY . .
RUN rm -f go.sum && go mod tidy && CGO_ENABLED=0 go build -o event-router .

FROM alpine:3.21

RUN apk add --no-cache ca-certificates tzdata
WORKDIR /app
COPY --from=builder /app/event-router .

EXPOSE 8092

CMD ["./event-router"]
