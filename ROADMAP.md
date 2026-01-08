# Shadow-Tracker Development Roadmap

This document outlines the strategic progression from the current foundational system (Phase 1) to a context-aware, identity-level behavioral modification agent.

## Phase 1: Foundation & Deterministic Rules (Current Status)
**Objective:** Establish value-based accountability and heuristic pattern detection without heavy reliance on inference for basic auditing.

* **Priority Matrix:** Implementation of `priorities` table to weight user activities (1–5).
* **Deterministic Pattern Recognition:**
    * *Avoidance:* Algorithmic detection of unlogged time/auto-sleep events.
    * *Neglect:* Time-series analysis to flag high-priority categories (Weight 4–5) absent for >72 hours.
    * *Imbalance:* Detection of "Leisure" classification during defined operational hours.
* **Weekly Heuristics:** Pre-pending rule-based insights (e.g., burnout warnings based on sleep/work delta) to visual summaries.

---

## Phase 2: Contextual Memory Architecture (Scoped RAG)
**Objective:** Transition from an episodic feedback system to a longitudinal behavioral memory system. The agent must recall past failures and principles to prevent cyclical feedback loops.

### 4. Definition of Behavioral Memory
Distinct from conversational history, *Behavioral Memory* persists specific structured units:
* **Weekly Insights:** Summarized text of previous weekly reports.
* **Detected Patterns:** Structured records of recurring avoidance or neglect.
* **User Principles:** Explicit value statements extracted from journal entries.
* **Recidivism Records:** Patterns repeated >3 times.

### 5. RAG Architecture (Lightweight/Local)
* **Embedding Model:** `all-MiniLM-L6-v2` (384-dimensional) for low-latency local inference.
* **Storage Backend:** SQLite `memory` table utilizing vector storage (BLOB) for cosine similarity.
    ```sql
    CREATE TABLE memory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type TEXT, -- e.g., 'summary', 'pattern', 'principle'
        content TEXT,
        embedding BLOB,
        timestamp DATETIME
    );
    ```
* **Retrieval Logic:**
    * **Trigger:** Only on free-text journal entries (not button clicks).
    * **Scope:** Fetch top-k (k=2) semantically similar entries + last weekly summary.
    * **Injection:** Retrieved context is injected into the LLM system prompt as immutable context constraints.

### 7. Prompt Engineering Update
The system prompt will be updated to enforce historical consistency:
> "Context constraints: [Retrieved Memory]. Do not contradict prior feedback unless new evidence is presented. Do not reassure the user unless the retrieved behavioral data supports it."

---

## Phase 3: Identity-Level Feedback (Long-Term Analysis)
**Objective:** Move beyond daily/weekly tactical advice to monthly strategic identity auditing.

### 8. Monthly Identity Report
* **Aggregation:** Synthesis of 4 weeks of behavioral data and AI feedback.
* **Narrative Generation:** The LLM generates a "Narrative Identity" profile based on observed actions rather than stated intent.
* **Example Output:**
    > "The data profile indicates an agent disciplined during structured morning hours but consistently avoidant during evening transitions. Self-reported priorities regarding 'Sleep' are contradicted by a 4-week trend of late-night leisure logging."

---

## Phase 4: Tonal Calibration ("Wholesome Rigor")
**Objective:** refine the agent's persona to balance stoic accountability with constructive reinforcement.

### Feedback Logic Rules
1.  **Conditional Compassion:** Empathy is algorithmically gated; it is offered only when effort metrics (e.g., improved log consistency) are detected.
2.  **Consequence-Oriented Phrasing:** Feedback must highlight the downstream effects of current actions.
3.  **Tone Guidelines:**
    * *Avoid:* "It’s okay, tomorrow is a new day." (Passive reassurance)
    * *Enforce:* "You failed to meet your standard today. This does not define you, but repetition will." (Active accountability)
