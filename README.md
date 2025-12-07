# AI Accountability Agent

An AI-powered "adult nanny" that acts as external accountability to help manage workload, time, and commitments across multiple tools and clients.

## Overview

This agent integrates with your digital tools (Google Suite, Asana, Slack, etc.) to:
- Aggregate information from multiple sources
- Send proactive notifications (morning briefings, urgent alerts)
- Use AI to prioritize tasks and highlight what matters most
- Track workload across multiple clients

## Current Features

### Integrations

| Integration | Status | Capabilities |
|-------------|--------|--------------|
| Google Calendar | ✅ Ready | Fetch events from all calendars, support for multiple accounts |
| Gmail | ✅ Ready | Inbox summary, unread counts, important email detection |
| Twilio SMS | ✅ Ready | Send text notifications, morning briefings |
| Slack | ✅ Ready | Rich formatted messages, daily briefings with blocks |
| Asana | 🔜 Planned | Task sync, project tracking |
| Notion | 🔜 Planned | Database sync, task aggregation |

### Core Features

#### Morning Briefings
Automated daily briefings sent at your configured time including:
- Today's calendar events (aggregated from all connected accounts)
- Email inbox summary (unread count, important items)
- Urgent emails requiring attention
- AI-generated priorities for the day

#### AI Prioritization
Powered by Claude to analyze:
- Calendar events for meeting prep needs
- Emails for urgency scoring (1-10 scale)
- Tasks for priority scoring (0-100 scale)
- Combined context to suggest daily focus areas

#### Multi-Account Support
Connect multiple Google accounts (e.g., work + personal + client accounts) and see everything in one unified view.

#### Scheduled Jobs
- Morning briefings: Runs every 5 minutes to catch users in different timezones
- Urgent item checks: Runs every 15 minutes for time-sensitive alerts

## Project Structure

```
ai-accountability-agent/
├── config/
│   ├── __init__.py
│   └── settings.py           # Pydantic settings management
├── src/
│   ├── api/
│   │   ├── auth.py           # OAuth endpoints
│   │   ├── briefings.py      # Briefing generation API
│   │   ├── tasks.py          # Task management API
│   │   └── routes.py         # Route aggregation
│   ├── integrations/
│   │   ├── google_auth.py    # Google OAuth flow
│   │   ├── google_calendar.py # Calendar service
│   │   ├── google_gmail.py   # Gmail service
│   │   ├── twilio_sms.py     # SMS notifications
│   │   └── slack.py          # Slack messaging
│   ├── models/
│   │   ├── database.py       # SQLAlchemy async setup
│   │   ├── user.py           # User model
│   │   ├── integration.py    # OAuth token storage
│   │   └── task.py           # Task model with priority scoring
│   ├── services/
│   │   ├── briefing.py       # Briefing generation logic
│   │   ├── scheduler.py      # APScheduler background jobs
│   │   └── ai_prioritization.py # Claude AI integration
│   └── main.py               # FastAPI application entry
├── tests/
├── .env.example              # Environment template
├── .gitignore
└── pyproject.toml            # Project dependencies
```

## Setup

### Prerequisites
- Python 3.11+
- Google Cloud Console project with Calendar and Gmail APIs enabled
- Twilio account (for SMS)
- Slack workspace with bot configured (for Slack notifications)
- Anthropic API key (for AI features)

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/ai-accountability-agent.git
   cd ai-accountability-agent
   ```

2. Create and activate virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -e .
   ```

4. Configure environment:
   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   ```

5. Run the application:
   ```bash
   uvicorn src.main:app --reload
   ```

### Google Cloud Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project or select existing
3. Enable APIs:
   - Google Calendar API
   - Gmail API
4. Create OAuth 2.0 credentials:
   - Application type: Web application
   - Authorized redirect URI: `http://localhost:8000/auth/google/callback`
5. Copy Client ID and Client Secret to `.env`

### Twilio Setup

1. Sign up at [Twilio](https://www.twilio.com)
2. Get a phone number
3. Copy Account SID, Auth Token, and phone number to `.env`

### Slack Setup

1. Create a Slack App at [api.slack.com](https://api.slack.com/apps)
2. Add bot scopes: `chat:write`, `im:write`, `users:read`
3. Install to workspace
4. Copy Bot Token and your User ID to `.env`

## API Endpoints

### Authentication
- `GET /auth/google` - Start Google OAuth flow
- `GET /auth/google/callback` - OAuth callback handler
- `GET /auth/status` - View connected integrations

### Briefings
- `GET /briefings/{user_id}` - Generate briefing (without sending)
- `POST /briefings/{user_id}/send` - Generate and send briefing
- `GET /briefings/{user_id}/preview/sms` - Preview SMS format

### Tasks
- `GET /tasks/{user_id}` - Get all tasks
- `POST /tasks/{user_id}/prioritize` - AI prioritize tasks
- `GET /tasks/{user_id}/by-client` - Tasks grouped by client

### Health
- `GET /` - Service health check
- `GET /health` - Health endpoint

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `GOOGLE_CLIENT_ID` | Google OAuth client ID | Required |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret | Required |
| `TWILIO_ACCOUNT_SID` | Twilio account SID | Optional |
| `TWILIO_AUTH_TOKEN` | Twilio auth token | Optional |
| `TWILIO_FROM_NUMBER` | Twilio phone number | Optional |
| `USER_PHONE_NUMBER` | Your phone number for SMS | Optional |
| `SLACK_BOT_TOKEN` | Slack bot token | Optional |
| `SLACK_USER_ID` | Your Slack user ID | Optional |
| `ANTHROPIC_API_KEY` | Anthropic API key for Claude | Optional |
| `MORNING_BRIEFING_TIME` | Default briefing time | `07:00` |
| `TIMEZONE` | Default timezone | `Australia/Sydney` |

## Future Enhancements

### Near-term Roadmap

#### Asana Integration
- Sync tasks from Asana projects
- Map Asana projects to clients
- Two-way sync for task completion
- Due date and priority synchronization

#### Notion Integration
- Connect to Notion databases
- Sync tasks and projects
- Support for different database schemas

#### Enhanced Notifications
- Calendar event reminders (15 min, 1 hour before)
- Overdue task alerts
- Weekly summary reports
- End-of-day recap

### Medium-term Roadmap

#### Social Media Inbox
- LinkedIn message monitoring
- Twitter/X DM notifications
- Unified "inbox zero" tracking

#### Natural Language Interaction
- Slack bot for conversational updates
- "What's my day look like?" queries
- Task creation via chat
- Rescheduling assistance

#### Client Workload Dashboard
- Time allocation by client
- Task distribution visualization
- Capacity planning insights
- Overcommitment warnings

### Long-term Vision

#### Proactive Intelligence
- Pattern recognition (meeting overload, email debt)
- Burnout risk detection
- Optimal scheduling suggestions
- Focus time protection

#### Learning & Adaptation
- Learn your priorities over time
- Understand client importance from behavior
- Personalized urgency calibration
- Meeting preference learning

#### Multi-user Support
- Team accountability features
- Delegation tracking
- Shared client visibility
- Manager dashboards

## Development

### Running Tests
```bash
pytest
```

### Code Formatting
```bash
ruff check --fix .
ruff format .
```

### Type Checking
```bash
mypy src
```

## License

MIT License - see LICENSE file for details.

## Contributing

Contributions welcome! Please read CONTRIBUTING.md for guidelines.
