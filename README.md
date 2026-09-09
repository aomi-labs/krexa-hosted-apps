# Aomi Krexa Apps

This platform owns its app build workflow, compilation runners, releases and
GitHub deployment history. Aomi Manager stages source candidates and coordinates
requests; Aomi backend hosts load the selected release.

See [the deployment workflow and setup contract](DEPLOYMENT.md) for ownership,
sequence, credentials, customization, workspace support and recovery behavior.
See [contributing an app](CONTRIBUTING.md) for the source-repository requirements.

The platform descriptor is [platform.json](platform.json). Do not hand-edit
staged app directories: use the Aomi Build deployment flow.
