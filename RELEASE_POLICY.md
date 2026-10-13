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

The `Release` workflow (named `Release validation` in Sprint 4) accepts manual dispatches from `main`. The `RELEASE_OPERATOR` repository variable contains one GitHub login, without `@`. Both the original actor and the actor requesting a rerun must match it. An unset variable fails closed.

The workflow checks out the full commit SHA selected when the run was dispatched, fetches full history and tags, validates metadata, and repeats pytest for that commit. A later push to `main` does not change the selected source. The Mac deployment runner revalidates metadata and authorization, repeats tests, builds one image using Docker Desktop, tests a temporary container, and deploys that image ID. Live HTTP checks verify the version, commit, and calculator behavior before publication.

Release runs share a concurrency group, and a file lock in the runner user's state directory prevents simultaneous replacement scripts. The deployment binds to Mac loopback port 5004 and retains the previous stopped container and image. Handled verification failures attempt restoration and still fail the release. Hard interruption requires manual inspection. Publishing uses a hosted job with write permission and requires deployment evidence from the same run attempt. See `SPRINT_5.md` for partial-publication recovery; deployment and GitHub publication are not an atomic transaction.

Repository administrators and contributors who can modify trusted workflow code or configuration remain part of the trust boundary. This is an educational policy gate, not protection against a malicious repository administrator. GitHub permissions govern who can request a workflow run; this application policy further limits which requests proceed.

The local validator is a preview of working-tree metadata using locally available tags. It does not enforce GitHub authorization and is not approval to deploy. The reported HEAD identifies the checkout; uncommitted local edits may differ from that commit. The hosted workflow uses a fresh checkout.

## References

- [Semantic Versioning specification](https://semver.org/)
- [GitHub Actions contexts, including actor and triggering_actor](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts)
