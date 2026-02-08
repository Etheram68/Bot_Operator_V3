# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Environment Setup

```bash
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
```

### Running

```bash
python main.py --list                              # List available missions
python main.py --mission 12345                     # Deploy specific mission
python main.py --auto --max-missions 3             # Auto deploy (max 3)
python main.py --continuous                        # Continuous mode
python main.py --status                            # Show bot status
python main.py --list --no-headless --debug         # Debug mode (with browser UI)

# Mission analysis
python main.py --analyze-conditions                # Analyze conditions of available missions
python main.py --analyze-conditions --max-analyze 10
python main.py --analyze-mission 12345             # Analyze specific mission
python main.py --test-mission 12345                # Test complete mission scraping

# Pattern analysis
python bot_operateur/utils/analyze_patterns.py     # Analyze unrecognized vehicle patterns
```

### Docker

```bash
docker-compose up --build -d                       # Build and run
docker-compose logs -f bot-operateur               # View logs
docker-compose down                                # Stop
```

## Architecture Overview

Python automation bot for "Opérateur 112" (emergency management game).
Built with Playwright, Pydantic, Loguru, AsyncIO.

### Project Structure

```
bot_operateur/
├── core/
│   ├── bot.py                  # Main OperateurBot class (async context manager)
│   ├── browser_manager.py      # Playwright browser lifecycle & navigation
│   └── mission_manager.py      # Mission detection, analysis & deployment (3000+ lines - needs refactoring)
├── models/
│   ├── mission.py              # Mission data model
│   ├── vehicle.py              # Vehicle data model
│   ├── patient.py              # Patient data model
│   ├── requirement_parser.py   # Singleton - parses mission text into vehicle requirements
│   ├── contextual_parser.py    # Context-aware regex matching
│   ├── probability_detector.py # Detects probability vs concrete requirements
│   └── text_cleaner.py         # Mission text normalization
├── scrapers/
│   ├── mission_scraper.py      # Extracts missions from game interface
│   ├── vehicle_scraper.py      # Vehicle info & deployment (1500+ lines - needs refactoring)
│   ├── patient_scraper.py      # Patient data extraction
│   └── conditions_analyzer.py  # Mission conditions analysis
├── services/
│   ├── missing_needs_parser.py     # Parses missing vehicle/personnel alerts
│   ├── patient_transport_handler.py # Hospital selection for patients
│   └── prisoner_transport_handler.py # Prison selection for prisoners
├── strategies/
│   ├── base_strategy.py            # Abstract base for deployment strategies
│   ├── smart_strategy.py           # Smart vehicle selection with game data
│   └── smart_strategy_optimized.py # Optimized variant with vehicle optimizer
├── config/
│   ├── settings.py             # Pydantic Settings from .env (configurable values)
│   └── constants.py            # Technical constants (DOM selectors, timeouts, URLs)
├── utils/
│   ├── dom_base.py             # Base DOM operations (safe_click, etc.)
│   ├── dom_utils.py            # Higher-level DOM utilities
│   ├── exceptions.py           # Custom exception hierarchy
│   ├── retry.py                # Retry with exponential backoff
│   ├── simple_cache.py         # Simple TTL cache decorator
│   ├── smart_navigation.py     # Intelligent page navigation
│   ├── vehicle_selection_optimizer.py # Vehicle selection optimization
│   ├── analyze_patterns.py     # Pattern analysis tool
│   ├── text_utils.py           # Text utilities
│   └── logger.py               # Logging setup
└── data/
    ├── needs_labels_v2.json    # Regex patterns: mission text → vehicle types
    ├── vehicles_v2.json        # Vehicle alternatives & crew specs
    └── missing_needs_config.json # Missing needs parsing rules
```

### Key Patterns

- **Singleton**: `RequirementParser` — single instance, lazy-compiled regex patterns
- **Strategy Pattern**: `BaseStrategy` → `SmartStrategy` / `SmartStrategyOptimized`
- **Async Context Manager**: `OperateurBot` uses `async with` for resource cleanup
- **Settings from Environment**: All config via `.env` file with Pydantic validation

### Data Flow

1. Browser connects and authenticates via `browser_manager`
2. `mission_scraper` detects available missions
3. `requirement_parser` analyzes mission text → vehicle requirements
4. Strategy selects optimal vehicles from available pool
5. `vehicle_scraper` deploys selected vehicles
6. `services/` handle special cases (patient transport, prisoner transport, missing needs)

### Configuration

Settings loaded from `.env`:
- `USERNAME`/`PASSWORD`: Game credentials (required)
- `DEFAULT_STRATEGY`: `smart` or `smart_optimized` (default)
- `HEADLESS`: Browser display mode
- `LOG_LEVEL`: Logging verbosity
- `MAX_CONCURRENT_MISSIONS`: Safety limit (default 5)
- `MIN_CREDITS_THRESHOLD`: Minimum mission credits (default 1000)

### Data Files

- `needs_labels_v2.json`: Regex patterns matching mission text to vehicle types (77 types)
- `vehicles_v2.json`: Vehicle alternatives and crew specifications
- Both files are critical for the smart strategy
