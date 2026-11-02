# Releasing VoDLint

Configure a PyPI Trusted Publisher before publishing the first release. For a new project, add a pending publisher at https://pypi.org/manage/account/publishing/ with project `vodlint`, owner `afshinyarinia`, repository `vodlint`, workflow `release.yml`, and environment `pypi`. For an existing project, an owner must add the same publisher in its publishing settings. A pending publisher does not reserve the name.

The GitHub environment `pypi` can be configured with deployment protection rules by a repository administrator. The workflow requires no stored PyPI API token. See https://docs.pypi.org/trusted-publishers/ for setup and prerequisites.

After the release preparation is committed and CI passes, create a GitHub release from a tag `v<version>` matching `pyproject.toml`, using the prepared release notes. Publishing the GitHub release triggers `.github/workflows/release.yml`. Its build job checks the tag and main-branch ancestry, runs tests, builds, checks, and installs the wheel; the separate OIDC job publishes the checked artifacts to PyPI. Check the workflow result and install the published version in a fresh environment.

PyPI release files cannot be replaced with the same version. If publication fails after a partial upload, inspect PyPI before retrying and follow its recovery guidance; do not overwrite a release.
