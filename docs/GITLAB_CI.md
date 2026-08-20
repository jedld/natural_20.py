# GitLab CI

The GitLab remote (`zariel.local`, project `jedld/natural20.py`) runs
[`.gitlab-ci.yml`](../.gitlab-ci.yml). That file **replaces Auto DevOps**.

Jobs match GitHub Actions:

| Job | What it runs |
|---|---|
| `python:engine` | `pytest tests --ignore=tests/webapp` |
| `python:webapp` | `pytest n20-webapp/tests/webapp` |
| `js:webapp` | `npx jest` in `n20-webapp/` |

## Why Auto DevOps failed

With no `.gitlab-ci.yml`, GitLab used **Auto DevOps**. The Build job tags the image as:

```text
$CI_REGISTRY_IMAGE/$CI_COMMIT_REF_SLUG:$CI_COMMIT_SHA
```

When **Container Registry is disabled**, `CI_REGISTRY_IMAGE` is empty, so Docker
receives `/master:<sha>` and exits with `invalid reference format`.

Auto DevOps also skipped git submodules (`Skipping Git submodules setup`), which
this repo needs (`n20-webapp`, `user_levels`). The root `Dockerfile` is also
pre-split (it still copies `webapp/` and a root `package.json`).

## Submodules (GitLab mirrors, not GitHub)

`.gitmodules` still points at GitHub (`git@github.com:...`), but **GitLab CI
does not fetch submodules at all** (`GIT_SUBMODULE_STRATEGY: none`). The
`n20-webapp` and `user_levels` repos are private on GitHub, so the pipeline
instead clones **GitLab mirrors** of both repos:

| Mirror project | Cloned into |
|---|---|
| `jedld/n20-webapp` | `n20-webapp/` |
| `jedld/n20-campaigns` | `user_levels/` |

The mirrors live on the same self-hosted GitLab. After updating a local
checkout of either submodule, push it with:

```bash
cd n20-webapp && git push gitlab master
cd ../user_levels && git push gitlab master
```

### Required CI/CD variables (project `jedld/natural20.py`)

| Key | Value |
|---|---|
| `N20_WEBAPP_GIT_URL` | `https://oauth2:<project-access-token>@zariel.local:8090/jedld/n20-webapp.git` |
| `N20_CAMPAIGNS_GIT_URL` | `https://oauth2:<project-access-token>@zariel.local:8090/jedld/n20-campaigns.git` |

Create a **project access token** (Settings → Access Tokens) for the `jedld`
user with the `read_repository` scope, then set both variables (mark them
**Masked**). Do not hardcode tokens in `.gitlab-ci.yml`.

`n20-campaigns` tracks some campaign assets (e.g. audio) with Git LFS; jobs
pull LFS objects after cloning when `git-lfs` is available in the image.

## Optional: Container Registry / image builds

To build and push images with Auto DevOps (or a custom `docker build` job):

1. **GitLab admin** (self-hosted): enable the registry in `gitlab.rb`
   (`registry_external_url`, `gitlab_rails['registry_enabled'] = true`) and
   reconfigure. See [GitLab Container Registry](https://docs.gitlab.com/administration/packages/container_registry/).
2. **Project:** Settings → General → Visibility → **Container Registry** on.
3. Confirm a pipeline job prints a non-empty `CI_REGISTRY_IMAGE`
   (e.g. `registry.zariel.local/jedld/natural20.py`).

Until that image name is set, do not re-enable Auto DevOps. After registry is
on, update the root `Dockerfile` for the `n20-webapp/` layout before adding a
build job.

## Pushing to GitLab

```bash
git push gitlab master
```
