# TODO

## High priority

- **Full-text article search** — currently searches only titles; add content search for better discoverability
- **Topic pool monitor** — expose unwritten topics count by category on `/health` or a new page, with depletion rate and estimated time until exhaustion

## Medium priority

- **`agents/coordinator.py:_improve_low_quality`** — Add per-article try/except to prevent one bad `get_talk_messages` call from crashing the entire improvement step
- **`agents/coordinator.py:_review_external_submissions`** — Add per-task error handling in the parallel `ThreadPoolExecutor` pool so one failed review doesn't kill all 3
- **Article quality dashboard** — word count, section count, improvement history, quality score per article
- **Agent performance dashboard** — articles created/improved per cycle, error rate, topic alignment success rate
- **Related articles sidebar** — based on shared categories and `[[See also]]` links
- **Search filters** — by category, date range, article kind

## Low priority

- **`agents/coordinator.py:_verify_topic_alignment`** — Add a max-retry guard (e.g. 2 attempts) to prevent an infinite loop if the LLM keeps returning off-topic content
- **Manual topic seeding UI** — a page to add new topics to the pool without editing files
- **Agent loop health page** — last N cycle results, errors, articles created/improved/reviewed
- **Article voting / rating** — thumbs up/down on articles
- **User contribution history** — see what articles a user has edited
- **Article export** — download as Markdown, PDF, or plain text
- **Article watchlist** — users get notified when watched articles change
