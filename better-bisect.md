# Golden Section Search

Normal `git-bisect`  uses bisection/binary search to iteratively find the first bad commit/last good commit in a repo. This is the optimal sequential solution for a "sorted" commit history in which all bad commits within range are on one side and all good commits are on the other.

If, instead, there is an untestable region of commits that `git-bifurcate` must treat as one set of changes

<!-- Does golden section search actually work better for finding an untestable region? -->
<!-- Maybe just `git-bisect` and find last strictly good & again for first strictly bad -->