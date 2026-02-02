# Browser module (Web mode)

Voice-controlled web: search (table only), open URL, store page for RAG. Self-contained addon; config merged by discovery.

## Voice commands for browse (web) mode

| Command | Example |
|---------|---------|
| **Browse mode** | "browse on", "browse off" |
| **Search** | "search" + your query |
| **Save page** | "save page" |
| **Navigation** | "back" |
| **Open link** | "open" + target (position or text) |
| **Scroll** | "scroll up", "scroll down" |
| **Close tab** | "close", "close tab" (on main tab: quit confirmation) |
| **Help** | Press **H** or **h** to show this help |
| **Close help** | Press **Esc** |

## Config

- **browser.enabled**: Turn browser module on or off.
- **browser.chrome_app_name**: App name for opening Chrome (e.g. "Google Chrome").
- **browser.fetch_timeout_sec**, **browser.fetch_max_retries**: Search fetch settings.
- **browser.search_engine_url**: URL template for search (e.g. `https://duckduckgo.com/?q={query}`).
- **browser.cooldown_sec**: Cooldown between commands.

Override in root `config.yaml` or `config.user.yaml`.

## Deployment (container)

When this module runs as a compose service, rebuild the image to pick up code changes: `podman compose build browser` then `podman compose up -d --force-recreate browser`. Local (in-process): restart the web UI to pick up changes.
