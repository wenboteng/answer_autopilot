# OTA Forum Auto-Reply System (MVP)

This project is an automated system to monitor public forums (starting with Reddit), detect OTA vendor-related questions, and auto-reply with helpful answers and links to our tool ([https://gygsearch.io](https://gygsearch.io)).

## Architecture

The system is built as four loosely-coupled microservices:

1. **Listener** (`listener.py`) - Monitors Reddit streams for OTA-related posts
2. **Classifier** (`classify.py`) - FastAPI service that classifies posts as vendor questions
3. **Reply Generator** (`reply.py`) - Generates responses using OpenAI
4. **Poster** (`poster.py`) - Posts replies with rate limiting and safety measures

## Features

- **Async Reddit Monitoring**: Uses `asyncpraw` for efficient streaming
- **Smart Classification**: Sentence transformers for vendor detection
- **AI-Powered Responses**: OpenAI GPT-4o-mini for natural replies
- **Rate Limiting**: Respects Reddit's API limits (3 comments/hour until 500 karma)
- **Content Moderation**: OpenAI moderation API for safety
- **Redis Queue Management**: Reliable message passing between services
- **Docker Deployment**: Easy deployment with Docker Compose

## Setup

### 1. Clone the repository
```bash
git clone <repo-url>
cd <repo-directory>
```

### 2. Configure environment variables
```bash
cp env.example .env
# Edit .env with your credentials:
# - Reddit API credentials (client_id, client_secret, refresh_token)
# - OpenAI API key
```

### 3. Deploy with Docker Compose
```bash
docker-compose up -d
```

### 4. Monitor logs
```bash
docker-compose logs -f
```

## Configuration

Edit `config.yaml` to customize:
- Target subreddits
- OTA keywords
- Rate limits
- Safety settings
- Tool URL and UTM parameters

## Services

### Listener Service
- Streams posts from target subreddits
- Filters by OTA keywords
- Queues relevant posts for classification

### Classifier Service
- FastAPI endpoint at `http://localhost:8000`
- Uses sentence transformers for semantic analysis
- Returns vendor classification and pain point detection

### Reply Generator
- Processes classified vendor posts
- Generates responses using OpenAI
- Applies content moderation
- Adds UTM tracking parameters

### Poster Service
- Posts replies with rate limiting
- Tracks account karma for limits
- Logs all activity to Redis

## Safety Features

- **Dry Run Mode**: Set `dry_run: true` in config.yaml for testing
- **Content Moderation**: OpenAI moderation API
- **Rate Limiting**: Respects Reddit's API limits
- **Duplicate Prevention**: Redis TTL for processed posts
- **Error Handling**: Exponential backoff and graceful failures

## Monitoring

- All activity logged to Redis
- Daily post counts tracked
- Error logging with timestamps
- Health check endpoints

## Testing Checklist

1. **Dry Run**: Test with `dry_run: true`
2. **Manual Approval**: Implement Slack webhook for manual review
3. **Soak Test**: Run 48h test to verify rate limits
4. **CTR Measurement**: Target ≥5% click-through rate

## Deployment

### Local Development
```bash
docker-compose up
```

### Production (DigitalOcean)
```bash
# Deploy to $5 droplet
docker-compose -f docker-compose.yml up -d
```

### Scaling
Use Docker Swarm for horizontal scaling:
```bash
docker stack deploy -c docker-compose.yml ota-bot
```

## API Endpoints

### Classifier Service
- `POST /score` - Classify a post
- `GET /health` - Health check
- `GET /pain_points` - Available pain point categories

## Environment Variables

See `env.example` for all required variables:
- `REDDIT_CLIENT_ID`
- `REDDIT_CLIENT_SECRET` 
- `REDDIT_REFRESH_TOKEN`
- `OPENAI_API_KEY`

## License

MIT 