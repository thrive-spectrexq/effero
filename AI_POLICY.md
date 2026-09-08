# AI-Generated Contribution Policy

Effero is a framework for agentic AI — which means it's a natural target
for AI-generated contributions. We welcome them, with ground rules:

## Requirements

1. **Disclose AI involvement.** If any part of your PR (code, tests,
   docs, commit messages, review comments) was generated or substantially
   assisted by an AI tool, say so in the PR description. A simple
   "Co-authored with [tool name]" is sufficient.

2. **Human review is mandatory.** Every PR must have a human author who
   has read, understood, and takes responsibility for the entire diff.
   Fully autonomous agent PRs with no human reviewer will be closed.

3. **You are responsible for correctness.** "The AI wrote it" is not an
   acceptable response to a review comment. If you can't explain why a
   line of code is correct, it shouldn't be in your PR.

## Why this policy

Effero controls physical hardware. A subtle bug in a safety policy, an
adapter, or a skill can have real-world consequences. The bar for
understanding what code does — not just that it passes CI — is higher
here than in most projects.

## AI-generated issues and reviews

The same disclosure requirement applies to issues and review comments.
AI-generated review comments that don't demonstrate understanding of
the code being reviewed will be dismissed.
