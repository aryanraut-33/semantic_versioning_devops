# Release policy

## Version rules

Use stable `MAJOR.MINOR.PATCH` versions without leading zeroes. Prerelease and build suffixes are outside this project's scope. The API contract is in `API_CONTRACT.md`.

`release.json` declares the highest change type across all changes since the previous successful release. A person reviews this declaration; the validator cannot infer whether code actually contains a breaking change. AI-assisted classification remains future scope.

| Declaration | Meaning | Example after 1.2.3 |
|---|---|---|
| patch | Backward-compatible bug fix | 1.2.4 |
| minor | Backward-compatible functionality | 1.3.0 |
| major | Incompatible API change | 2.0.0 |
| initial | First release only, with no release tags | 1.0.0 |

The project requires the exact next increment. Each candidate needs one `## [VERSION]` section in `CHANGELOG.md` containing at least one nonempty `- ` bullet. Retain previous entries. The script verifies presence, not the accuracy of the prose.

## Successful release baseline

Reserve Git tags named `vMAJOR.MINOR.PATCH` for successfully deployed releases. The highest numeric release tag is the baseline, and it must be an ancestor of the selected commit. Other tags are ignored unless they begin with `v`; malformed tags in that reserved namespace fail validation. Versions cannot be reused, skipped, or decreased.

This is a single forward release sequence: no parallel maintenance branches. Rolling back deployment later will not decrease the version baseline or delete release history.

The release workflow creates a successful release tag only after deployment verification, then publishes its GitHub Release. Do not manually create demonstration release tags in the real repository: tests use simulated tag lists. A tag is trusted evidence under this project's convention, not independent proof that deployment occurred.

## Authorization and commit selection

The `Release` workflow starts automatically when the `CI` workflow completes successfully for a push to `main` in this repository. Pull-request CI, failed/cancelled CI, and manually dispatched CI do not proceed to automatic deployment. The trigger uses `workflow_run`; its job condition checks the CI conclusion, source event, branch, workflow path, and source repository. Manual Release dispatches from `main` remain available for demonstrations and recovery.

The `RELEASE_OPERATOR` repository variable contains one GitHub login, without `@`. Both the original Release actor and the actor requesting a Release rerun must match it. Automatic releases also require the original CI actor (the user responsible for the push/merge) and CI rerun actor to match it. An unset variable fails closed. Automation removes the manual Release button click; it does not remove authorization or infer the change type.

For automatic releases, the workflow checks out the completed CI run's `head_sha`, not the default branch SHA exposed as `GITHUB_SHA` by `workflow_run`. Manual releases use the SHA selected at dispatch. The workflow fetches full history and tags, validates metadata, and repeats pytest for that exact commit. A later push to `main` does not change the selected source. The Mac deployment runner checks out the validated commit, revalidates metadata and authorization, repeats tests, builds one image using Docker Desktop, tests a temporary container, and deploys that image ID. Live HTTP checks verify the version, commit, and calculator behavior before publication. Automatic release notes include a link to the triggering CI run.

Update `VERSION`, `release.json`, and `CHANGELOG.md` in each release candidate before merging. A successful CI run with an already-published version still triggers an automatic release attempt, which fails validation without replacing the live application. Invalid increments and missing changelog entries also fail. There is no automatic version bump or silent duplicate-version skip. This makes version-policy failures visible in the demo.

The updated workflow and validator must first be merged into the default branch (`main`) for automatic triggering to be enabled. CI and Release appear as separate Actions runs. A successful main push CI starts Release without waiting for a manual request; keep Docker Desktop and the Mac runner available. Complete each release before merging the next demo version. Concurrent runs are serialized, but GitHub's concurrency group is not a FIFO release queue and can replace pending runs.

Release runs share a concurrency group, and a file lock in the runner user's state directory prevents simultaneous replacement scripts. The deployment binds to Mac loopback port 5004 and retains the previous stopped container and image. Handled verification failures attempt restoration and still fail the release. Hard interruption requires manual inspection. Publishing uses a hosted job with write permission and requires deployment evidence from the same run attempt. See `SPRINT_5.md` for partial-publication recovery; deployment and GitHub publication are not an atomic transaction.

Repository administrators and contributors who can modify trusted workflow code or configuration remain part of the trust boundary. This is an educational policy gate, not protection against a malicious repository administrator. GitHub permissions govern who can request a workflow run; this application policy further limits which requests proceed.

The local validator is a preview of working-tree metadata using locally available tags. It does not enforce GitHub authorization and is not approval to deploy. The reported HEAD identifies the checkout; uncommitted local edits may differ from that commit. The hosted workflow uses a fresh checkout.

## References

- [Semantic Versioning specification](https://semver.org/)
- [GitHub Actions contexts, including actor and triggering_actor](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts)
- [GitHub workflow_run trigger and source commit behavior](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_run)
