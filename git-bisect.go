package main

import (
	"fmt"
	"time"

	"github.com/go-git/go-git/v6"
	. "github.com/go-git/go-git/v6/_examples"
	"github.com/go-git/go-git/v6/plumbing/object"
)

// Example of how to:
// - Clone a repository into memory
// - Get the HEAD reference
// - Using the HEAD reference, obtain the commit this reference is pointing to
// - Using the commit, obtain its history and print it
func main() {
	directory := "./go-siva"

	// Opens an already existing repository.
	r, err := git.PlainOpen(directory)
	CheckIfError(err)

	w, err := r.Worktree()
	CheckIfError(err)

	// ... retrieves the branch pointed by HEAD
	ref, err := r.Head()
	CheckIfError(err)

	// try to get tree @ HEAD
	hCommit, err := object.GetCommit(r.Storer, ref.Hash())
	CheckIfError(err)

	// Make sure we end where we started
	defer w.Checkout(&git.CheckoutOptions{
		Hash: hCommit.Hash,
		Force: true,
	})

	// Gets the HEAD history from HEAD, just like this command:
	Info("git log")

	// ... retrieves the commit history
	since := time.Date(2019, 1, 1, 0, 0, 0, 0, time.UTC)
	until := time.Date(2019, 7, 30, 0, 0, 0, 0, time.UTC)
	cIter, err := r.Log(&git.LogOptions{From: ref.Hash(), Since: &since, Until: &until})
	CheckIfError(err)

	// grab the latest commit in that range
	commit, err := cIter.Next()
	CheckIfError(err)
	// fmt.Println(commit)

	// try to get tree @ commit
	// cTree, err := commit.Tree()
	// CheckIfError(err)
	// fmt.Println(cTree)

	// get the patch
	patch, err := hCommit.Patch(commit)
	CheckIfError(err)
	// fmt.Println(patch)

	for _, filePatch := range patch.FilePatches() {
		from, to := filePatch.Files()
		if from != nil && to != nil {
			fmt.Println(from.Path(), to.Path())
		}
	}


	baseCommit, err := hCommit.Parent(0)
	CheckIfError(err)

	// ... checking out to commit
	Info("git checkout %s", baseCommit)
	err = w.Checkout(&git.CheckoutOptions{
		Hash: baseCommit.Hash,
	})
	CheckIfError(err)

	// ... retrieving the commit being pointed by HEAD, it shows that the
	// repository is pointing to the giving commit in detached mode
	Info("git show-ref --head HEAD")
	ref, err = r.Head()
	CheckIfError(err)
	fmt.Println(ref.Hash())

	toReset, _ := patch.FilePatches()[0].Files()

	// Can't apply patch; instead, we will checkout a subset
	Info("git reset")
	w.Reset(&git.ResetOptions{
		Commit: commit.Hash,
		Files: []string{toReset.Path()},
	})

	// Check that we made a tweak
	Info("git status --porcelain")
	status, err := w.Status()
	CheckIfError(err)

	fmt.Println(status)
}