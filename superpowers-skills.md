# Superpowers Skills

> Source: https://github.com/obra/superpowers

## Testing

### test-driven-development
Guides implementation of features and bugfixes following the red-green-refactor cycle. Core mandate: write the test first, watch it fail, write minimal code to pass. Applies to new features, bugfixes, refactoring, and behavior changes.

### verification-before-completion
Enforces a mandatory verification gate before claiming work is complete. Never claim success without running fresh verification commands and reading the actual output. "Evidence before assertions always."

---

## Debugging

### systematic-debugging
Structured four-phase root cause analysis: (1) root cause investigation, (2) pattern analysis, (3) hypothesis and testing, (4) implementation. Core rule: NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST.

---

## Collaboration

### brainstorming
Transforms ideas into fully formed designs through collaborative dialogue. Mandatory first step before any creative or implementation work. Guides through a nine-step process ending in an approved spec document before any code is written.

### writing-plans
Creates comprehensive implementation plans for multi-step development tasks. Saves plans to `docs/superpowers/plans/YYYY-MM-DD-<feature-name>.md`. Every step must contain complete, executable content with actual code examples.

### executing-plans
Orchestrates implementation of written plans across separate sessions with built-in review checkpoints. Requires git worktrees for isolated workspaces. Stop immediately on blockers — never guess.

### subagent-driven-development
Coordinates execution of plans by dispatching fresh independent subagents per task with a two-stage review (spec compliance + code quality). "Fresh subagent per task + two-stage review = high quality, fast iteration."

### dispatching-parallel-agents
Enables concurrent subagent workflows for 2+ independent tasks with no shared state or sequential dependencies. Each agent gets specific scope, clear goal, self-contained context, and output specification.

### requesting-code-review
Dispatches a code-reviewer subagent to validate work before merging. Review after each task, major feature, and before merging. Issues classified as Critical / Important / Minor.

### receiving-code-review
Guides technical evaluation of code review feedback. Prioritizes verification over performative agreement. Requires pushback when feedback is technically incorrect or lacks context.

### using-git-worktrees
Creates isolated git worktrees with smart directory selection and safety verification. Verifies `.gitignore`, auto-detects project type, runs dependency installation, and validates baseline tests.

### ~~finishing-a-development-branch~~ *(desactivada)*
~~Guides completion of development work by presenting integration options: merge locally, push + PR, keep branch, or discard. Verifies tests pass before offering any option. Never force-pushes without explicit request.~~

> **Desactivada** — esta skill gestiona commits y merges automáticos al finalizar una rama.

---

## Meta

### writing-skills
Use when creating new skills, editing existing skills, or verifying skills work before deployment. Applies TDD to documentation: document agent failures without the skill (RED), write minimal docs to fix them (GREEN), iterate until bulletproof (REFACTOR).

### using-superpowers
Establishes how to find and use other skills. Core rule: invoke relevant skills BEFORE any response or action. Even a 1% chance a skill applies mandates checking it first.
