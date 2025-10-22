# `git-bifurcate`

* Imagine if `git-bisect` could fimd the file or line that broke your test (not just the commit)
* Account for coupled changes (e.g. change in file A needs file B's change to compile)
* Find the smallest set of changes, R, in a commit, C, s.t. C minus R passes & R fails

## Goals

* Treat submodule hash changes as big sets of file changes
* Handle Rename & Retype of files w/ grace (Symlinks and Moves should still work)

## Better Bisection

* Get past islands of incompatibility
  * Typical bisections struggle with regions of failing builds and won't refine the location of the specific problem
  * Ideally detect non-monotonic success -> failure transitions & adaptively swap to bifurcation
    * Restrict the scope of search by finding the newest good & oldest bad commits that can be verified

## Test Invariants to Validate

* Consistency: if a test passses on commit A it will always pass on commit A
* Isolation: if a test fails on commit B it won't prevent a valid commit from passing
