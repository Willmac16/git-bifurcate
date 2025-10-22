# `git-bifurcate`

* Imagine if `git-bisect` could find the file or line that broke your test (not just the commit)
* Account for coupled changes (e.g. change in file A needs file B's change to compile)
* Find the smallest set of changes, R, in a commit, C, s.t. C minus R passes & R fails

## Goals

* Treat submodule hash changes as big sets of file changes
* Handle Rename & Retype of files w/ grace (Symlinks and Moves should still work)
* Handle or warn upon multi-parent merge commits

## Better Bisection

* Get past islands of incompatibility
  * Typical bisections struggle with regions of failing builds and won't refine the location of the specific problem
  * Ideally detect non-monotonic success -> failure transitions & adaptively swap to bifurcation
    * Restrict the scope of search by finding the newest good & oldest bad commits that can be verified

## Test Invariants to Validate

* Consistency: if a test passses on commit A it will always pass on commit A
* Isolation: if a test fails on commit B it won't prevent a valid commit from passing

## Test Script Requirements

Just like `git-bisect` your exit code drives everything

* exit `0` for good
* exit `125` for untestable
* exit `1`-`127` for bad
