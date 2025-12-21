# Single Hunk Break Fixture

## Description
Single file with 4 functions modified. The multiply() function has a bug.

## Expected Result
Hunk-level bifurcation should identify the specific hunk (multiply function).

## Commits
- Parent (good): 09fad38aebab7f33356047d63d169c393efde518
- Bad commit: face63f4b88b3fbdc0e5964f4ccd97f72374685b

## Test Command
```bash
python3 test.py
```

## Breaking Change
Function: `multiply(a, b)`
Line: `result = a + b  # Oops, should be a * b`
Expected: `result = a * b`
