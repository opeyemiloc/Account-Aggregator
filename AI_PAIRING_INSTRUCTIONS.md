AI Pairing Instructions

These instructions govern the collaboration between the developer and the AI assistant for the `RE-cal-resolution-pipeline` project, specifically focusing on the `user_driven_ingestion` plan.

## 1. Focused Execution

- The AI must only work on the specific parts of the codebase that are currently in focus.
- Avoid modifying unrelated files or components.

## 2. Outline and Approval Workflow

- **Before** writing any code or modifying any files, the AI must explicitly outline:
  - What it plans to do.
  - Which files will be changed.
- The AI must wait for an explicit "go-ahead" from the developer before executing any file modifications.

## 3. Version Control and Branching

- The developer is responsible for creating and checking out all Git branches.
- The AI is strictly prohibited from running any `git add`, `git commit`, or `git push` commands autonomously.

## 4. Final Deliverables

- Once a fix or feature implementation is complete and the developer is ready to commit, the AI will provide:
  - A short, descriptive commit message.
  - A concise, bulleted PR (Pull Request) summary.
