#!/usr/bin/env bash
# Rewrite the rolling `latest` release title/notes and move the git tag to
# GITHUB_SHA so the Releases page matches the zips just uploaded.
set -euo pipefail

if [[ -z "${GITHUB_SHA:-}" || -z "${GITHUB_REPOSITORY:-}" ]]; then
  echo "GITHUB_SHA and GITHUB_REPOSITORY are required" >&2
  exit 1
fi

SHORT_SHA="${GITHUB_SHA:0:7}"
SUBJECT="$(git log -1 --format=%s "${GITHUB_SHA}" | tr -d '\r')"
TIME_UTC="$(date -u +"%Y-%m-%d %H:%M UTC")"
SERVER_URL="${GITHUB_SERVER_URL:-https://github.com}"
RUN_URL="${SERVER_URL}/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}"
COMMIT_URL="${SERVER_URL}/${GITHUB_REPOSITORY}/commit/${GITHUB_SHA}"
NOTES_FILE="${GITHUB_WORKSPACE:-.}/latest-release-notes.md"

{
  printf '%s\n' "最新 \`main\` 构建，随每次合入覆盖更新。以本页提交哈希核对是否为最新包。"
  printf '%s\n' ""
  printf '%s\n' "- **提交**: [\`${SHORT_SHA}\`](${COMMIT_URL}) \`${GITHUB_SHA}\`"
  printf '%s\n' "- **说明**: ${SUBJECT}"
  printf '%s\n' "- **打包时间**: ${TIME_UTC}"
  printf '%s\n' "- **构建**: [Actions run ${GITHUB_RUN_ID}](${RUN_URL})"
  printf '%s\n' ""
  printf '%s\n' "Windows 为 .NET 8 单文件 exe，macOS 为 Swift \`.app\`。"
  printf '%s\n' "从浏览器下载的 macOS 包若提示「已损坏」，请双击 zip 内的「首次打开.command」，或执行 \`xattr -cr CursorTokenTray.app\`。"
  printf '%s\n' "正式版请打 \`v*\` 标签。"
} > "${NOTES_FILE}"

gh release edit latest \
  --title "Latest (${SHORT_SHA}, ${TIME_UTC})" \
  --notes-file "${NOTES_FILE}" \
  --prerelease

# GitHub ignores target_commitish when the tag already exists, so the Releases
# page would keep showing the original tag commit. Force-move the tag.
if ! gh api -X PATCH "repos/${GITHUB_REPOSITORY}/git/refs/tags/latest" \
  -f sha="${GITHUB_SHA}" \
  -F force=true >/dev/null; then
  gh api -X POST "repos/${GITHUB_REPOSITORY}/git/refs" \
    -f ref="refs/tags/latest" \
    -f sha="${GITHUB_SHA}" >/dev/null
fi

echo "Updated latest release to ${SHORT_SHA} (${TIME_UTC})"
