# Multiple Files Break Fixture

## Description
5 files modified, file3.py contains breaking change.

## Expected Result
Binary search should find file3.py in ~3 iterations instead of 5 linear.

## Commits
- Parent (good): d9b3d02d58221d3596894c64d0e55f0ccf2e5311
- Bad commit: 058501778f0ce186eee0ad471b4f0a9a4c231eca

## Test Command
```bash
bash test.sh
```

## Breaking Change
File: `file3.py`
Line: `return "BROKEN"`
Expected: `return "file3"`
