# RoomTask – Technical Decisions

This document records important technical decisions and the reasoning behind them.

## Decision log

### TD-001 – FastAPI as backend framework

- **Decision:** Use FastAPI.
- **Reason:** Provides a modern Python API framework with request validation, automatic API documentation and asynchronous support.
- **Status:** Accepted.

### TD-002 – MySQL as database

- **Decision:** Use MySQL 8.4.
- **Reason:** Provides relational data storage, transactions, constraints and row locking for concurrent ticket handling.
- **Status:** Accepted.

### TD-003 – React as frontend framework

- **Decision:** Use React.
- **Reason:** Supports a component-based interface and separation between frontend and backend.
- **Status:** Accepted.

### TD-004 – Docker Compose for deployment

- **Decision:** Use Docker Compose.
- **Reason:** Allows the application services to be configured and started together in a reproducible environment.
- **Status:** Accepted.

### TD-005 – Discord integration as an optional service

- **Decision:** Keep the Discord bot optional.
- **Reason:** The core application should work independently of Discord.
- **Status:** Accepted.

## Future decisions

Record new architectural and technical decisions here.

Template:

### TD-XXX – Decision title

- **Decision:**
- **Reason:**
- **Alternatives considered:**
- **Consequences:**
- **Status:** Proposed / Accepted / Rejected / Superseded
