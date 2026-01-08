# Shadow-Tracker 🛡️

**Shadow-Tracker** is an automated behavioral reinforcement system designed to mitigate self-reporting bias in time tracking. Unlike passive logging tools, this application operates as an active auditing agent, utilizing a local Large Language Model (LLM) to validate user inputs against declared priorities.

The system enforces data integrity through hourly temporal sampling and heuristic analysis, detecting patterns of avoidance, priority neglect, and inconsistencies between logged activities and defined goals.

## Screenshot of Telegram Bot
<img src="demo/Screenshot_20260108_080358_Telegram.jpg" alt="Screenshot" width="500" height="1500"/>


## 🧠 Core Methodology: Cognitive Audit
The application addresses the "intention-behavior gap"; often rationalized by internal narratives (conceptually referred to here as "The Liar"). Shadow-Tracker implements a **Local Inference Engine** (via `llama.cpp`) to parse natural language entries, classifying them against a weighted priority matrix to provide objective, immediate feedback on resource allocation.

## ✨ System Capabilities
* **Active Temporal Sampling:** Initiates synchronous hourly prompts to capture activity data, defaulting to a "Sleep" state during defining dormant windows (23:00–08:00 ET) to maintain continuous time-series data.
* **LLM-Driven Classification:** Utilizes a quantized `Phi-3-mini-4k` model to semantically analyze user entries, classifying unstructured text into predefined categories based on context and sentiment.
* **Heuristic Anomaly Detection:**
    * **Priority Drift:** Monitors high-weight categories (Weight 4–5) for inactivity exceeding 72 hours.
    * **Avoidance Metrics:** Flags consecutive non-response events as potential behavioral avoidance.
    * **Contextual Mismatches:** Identifies "Leisure" classification events occurring within standard operational hours (09:00–17:00).
* **Weekly Aggregation & Reporting:** Generates a visual distribution analysis (Matplotlib) and a text-based heuristic summary of integrity violations every Sunday at 20:00 ET.

## 🛠️ Technical Architecture
* **Runtime Environment:** Python 3.11 (Slim-Bookworm) within a multi-stage Docker build.
* **Inference Engine:** `llama.cpp` server hosting `Phi-3-mini-4k-instruct` (GGUF format) for low-latency, offline text completion.
* **Persistence Layer:** SQLite relational database for transactional storage of logs and priority weights.
* **Visualization:** `Matplotlib` and `Pandas` for data aggregation and chart generation.
* **Orchestration:** Docker Compose for managing service dependencies between the bot and the AI inference server.

## 💻 Demo
* Please checkout the [DEMO](https://github.com/Raphaeal19/Shadow-Tracker/blob/main/demo/REPORT_DEMO.md).

## 🚀 Deployment

### 1. Prerequisites
* Docker Engine & Docker Compose.
* Valid Telegram Bot Token.
* GGUF model file (Default: `Phi-3-mini-4k-instruct-q4.gguf`) located in `./models`.

### 2. Configuration
Environment variables are required for service initialization. These may be defined in a `.env` file:
* `TELEGRAM_TOKEN`: API Token provided by BotFather.
* `AI_SERVER_URL`: Endpoint for the local inference service (Default: `http://ai-server:8080/completion`).

### 3. Execution
Initialize the containerized stack:
```bash
docker-compose up --build -d
