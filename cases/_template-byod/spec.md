# Spec: <your task>

The single source of truth for what a correct answer is. The optimiser reads this file and may rephrase it
in prompts but never change it.

## Input
What the model receives (one example from your file's `input` column, plus `context` if present).

## Output contract
Exactly what the model must return: a single label from a fixed list, a JSON object with these fields, ...

## Rules and edge cases
- Rule 1 ...
- How to treat missing values, casing, dates, numbers ...

## Scoring
How `score()` in case.py decides pass/fail (default: exact match for text, equality for JSON).
