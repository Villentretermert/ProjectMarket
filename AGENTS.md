# ProjectMarket agent instructions

Before every task, read these files in order:
1. `docs/WORKING_AGREEMENT.md` — mandatory working agreement with the owner.
2. `docs/STATUS.md` and `docs/DECISIONS.md` — actual progress and unresolved decisions.
3. `docs/ROADMAP.md`, the requested `docs/tasks/PM-NNN.md`, and its linked GitHub issue.

Follow the user's current instructions when they differ from planning assumptions. Do not silently choose an unresolved product decision. Execute authorized independent work and ask only for genuinely blocking answers.

The product UI is English. Discussion, planning and explanations are Russian unless requested otherwise. Use Python as much as practical for backend, bots and frontend; validate platform constraints before selecting the client stack. Brief code comments should explain non-obvious intent.

For each meaningful change update `CHANGELOG.md`; for each completed task record tests, deliverables and limitations in `docs/task-results/PM-NNN.md` and update the linked issue and status. Do not mark untested acceptance criteria complete.

After every four completed numbered roadmap tasks, stop before the next task to present results, code/components/entities, completed and remaining system design, next priorities and at least ten separate questions. Follow the checkpoint workflow in the working agreement. Read docs/STATUS.md for the current completion count and next checkpoint.

Do not commit credentials, environment secrets, private bot payloads or signing keys. Sharing layouts never grants access to private source data. Do not interpret a shared UI description as executable code.
