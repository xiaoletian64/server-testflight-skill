# Server contract

Requirements: Python 3.9+, Linux `fcntl`, GitHub CLI (`gh`) authenticated on the server, repository actions read/write access, a cloud macOS runner with Flutter/Xcode for the app, and server signing/upload/review adapters. GitHub Actions macOS minutes may incur charges. Apple Developer membership and an existing App record are required. Runner labels, SDK requirements and Apple APIs evolve; verify official requirements when configuring a new release.

The workflow must accept `build_name`, `build_number`, `platform` and `release_id`; use:

```yaml
run-name: ${{ inputs.release_id || 'Manual build' }}
```

Add optional string input `release_id`. Include a platform choice with `ios`, `android`, `both`. iOS must run on a configured macOS/Xcode image, execute analysis/tests, build unsigned device output, and upload one unsigned IPA with a version/number-specific artifact name. Do not expose a write-capable GitHub token or Apple signing keys to build jobs. The coordinator verifies run success and commit SHA before signing. If the configured ref changes between lookup and dispatch, it fails to find the expected run rather than signing another commit; inspect and restart deliberately.

Example private configuration (replace values; never commit the real file):

```json
{
  "repository": "OWNER/APP_REPOSITORY",
  "workflow": "ios.yml",
  "ref": "main",
  "bundle_id": "org.example.app",
  "minimum_ios": "15.0",
  "state_directory": "/var/lib/testflight/releases",
  "artifact_name": "ios-unsigned-{version}-{number}",
  "artifact_file": "ios-unsigned.ipa",
  "direct_network": false,
  "timeout_seconds": 10800,
  "sign_command": ["/usr/local/lib/testflight/sign", "{unsigned}", "{signed}"],
  "upload_command": ["/usr/local/lib/testflight/upload", "{signed}", "--state", "{work}/upload.json"],
  "finish_command": ["/usr/local/lib/testflight/finish", "--work", "{work}", "--version", "{version}", "--build-number", "{number}"]
}
```

Commands are argv arrays, never shell interpolation. Placeholder substitution is limited to known release paths/version/number. The config is executable trust input: only server administrators may edit it. `direct_network` removes inherited proxy environment variables only from this process and children; it never changes host proxy settings. Use it only if direct connectivity was verified.

Adapter requirements:

- **Sign:** validate profile/team/bundle and expiry; sign all nested frameworks/binaries correctly; embed the profile. Preserve original unsigned artifact; keep certificate/private key on the server. Tools such as zsign must be installed and validated separately.
- **Upload:** verify the signed bundle, marketing version and build number; use Apple's public buildUploads REST API, keep chunk/commit resume state, verify returned checksums, and never attach the Apple JWT to a presigned upload host. Transport success is not Apple processing success. For IPA commit, `uploaded: true` is used; do not invent optional checksum types rejected by the endpoint.
- **Finish:** resolve upload to the exact Apple build, verify app/bundle/version/number and VALID processing, and read the beta state. It may fill authorized descriptions/review contacts from server-only files. `--submit-review` submits beta review only, idempotently. `--enable-public-link` must reject non-approved builds and bind the approved build to the correct external group. Pending review is a normal result; return it without pretending a link is usable. Never call App Store release/review endpoints.

Keep state directories mode 0700, credentials/config mode 0600, and bounded waits. An interrupted dispatch can have an unknown outcome: the persisted dispatch record intentionally prevents automatic redispatch. The coordinator only resumes existing upload artifacts after their SHA-256 matches. It does not automatically allocate new build numbers or retry failed cloud builds.

Run long jobs using your server's existing supervisor. A simple manual invocation is:

```sh
nohup python3 /opt/server-testflight/scripts/release.py \
  --config /etc/testflight/project.json --version 1.0.0 --build-number 3 \
  --submit-review > /var/log/testflight-release.log 2>&1 < /dev/null &
```

Official references: [GitHub workflow dispatch](https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event), [Apple build uploads](https://developer.apple.com/documentation/appstoreconnectapi/build-uploads), [TestFlight overview](https://developer.apple.com/testflight/).
