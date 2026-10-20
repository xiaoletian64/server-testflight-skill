---
name: server-testflight
description: Coordinate iOS cloud builds, server-side signing and API uploads to TestFlight from a Linux server, without a personal Mac. Use for release setup, resumable publishing, beta review and tester access.
---

# Server TestFlight

Use a Linux coordinator and a hosted macOS/Xcode runner. A personal Mac is unnecessary; Xcode compilation still requires macOS. This is a personal, independent project, with no Apple or GitHub affiliation.

## Configure once

Read [the server contract](references/server-contract.md) when installing or changing a pipeline. Keep the local JSON config, credentials, signed artifacts and state outside Git. The repository contains a generic coordinator; project-specific signing, upload and review adapters live on the server and must satisfy the documented contract. Do not claim a new installation is functional until those adapters have been exercised.

Use the existing cloud provider and signing assets when authorized. Verify the Apple App record and bundle identifier before any mutation. A new App record may require App Store Connect setup; do not promise API support for operations the account lacks.

Run the coordinator on the server, through SSH or the server's job runner:

```sh
python3 scripts/release.py --config /etc/testflight/project.json \
  --version 1.0.0 --build-number 3 --check
```

Preflight checks configuration shape, GitHub authentication and workflow visibility only. It does not validate signing certificates, build the app or upload anything.

## Release

With the user's authorization and a verified intended source revision, remove `--check`. Use an unused, ascending build number. Default behavior builds, signs, uploads, and reads Apple processing status. Pass `--submit-review` only when external TestFlight review is intended. Pass `--enable-public-link` only when invitations are intended; the finish adapter must require Apple's approval for this exact build before enabling access.

A version/number identifies one immutable server state directory. Repeat the same command after interruption; it resumes the recorded cloud run and signed IPA rather than allocating a new build. If dispatch was attempted but no run can be identified, inspect the cloud run list before changing state. No automatic retry may create duplicate uploads or switch the intended source commit.

Report these states separately: cloud build success, byte upload completion, Apple processing VALID, beta review pending/approved, and actual tester availability. Internal testing requires an eligible App Store Connect user and this App's internal group/build association; knowing an email is not proof of access. An external public link requires the approved build in the external group. Never submit App Store review when only TestFlight was requested.

## Publish or share the skill

Export only this skill package and generic examples into a fresh repository with no private history. Review the entire staged tree for keys, emails, IPs, profile/team/app IDs, proxy subscriptions, logs, artifacts and machine paths. Keep workflow runners and permissions explicit; signing secrets stay on the server. Validate the skill and run the offline coordinator tests before publishing. Do not copy another project's private source or signing files into the public package.
